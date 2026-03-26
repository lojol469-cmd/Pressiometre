"""
Onglet Nuage de points 3D — PressiomètreIA v2
─────────────────────────────────────────────
Fonctionnalités :
  • Nuage 3D matplotlib (Axes3D) par couche Em / Pl / Pf
  • Export PLY  : nuage complet coloré (couleur sol ou valeur paramètre)
  • Export HTML : nuage Plotly interactif 3D avec hover + colorbar
  • Export SVG  : coupe de synthèse 2D du sous-sol avec courbes intégrées
  • Mini-coupes verticales : courbes P-V pressiométriques de chaque sondage
"""
from __future__ import annotations
from typing import Optional, Dict, List, cast
import io, os, struct, tempfile, datetime, webbrowser

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.backends.backend_svg import FigureCanvasSVG
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from mpl_toolkits.mplot3d.axes3d import Axes3D as _Axes3D

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QFileDialog, QSizePolicy,
    QScrollArea, QMessageBox, QTabWidget, QSplitter,
)
from PyQt6.QtCore import Qt

from api.models import PointCloud3D, CleanedEssai, PressiometricParams


# ─── Constantes visuelles ─────────────────────────────────────────────────────
_LAYER_CFG = {
    "Em_MPa":  ("turbo",    "Em (MPa)",  0, 100),
    "Pf_MPa":  ("viridis",  "Pf (MPa)",  0, 3),
    "Pl_MPa":  ("RdYlGn_r", "Pl (MPa)",  0, 5),
}

_BG   = "#0b0f1a"
_PANE = "#111827"
_EDGE = "#1e3352"
_TICK = "#64748b"
_CYAN = "#38bdf8"
_GOLD = "#f4a426"
_ORG  = "#e76f51"


# ─── Canvas 3D matplotlib ─────────────────────────────────────────────────────
class _Canvas3D(FigureCanvas):
    def __init__(self):
        self.fig = Figure(figsize=(9, 6.5), facecolor=_BG, tight_layout=True)
        super().__init__(self.fig)
        self.setStyleSheet(f"background:{_BG};")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def fresh_ax(self):
        self.fig.clear()
        ax = cast(_Axes3D, self.fig.add_subplot(111, projection="3d"))
        ax.set_facecolor(_BG)
        for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):  # type: ignore[attr-defined]
            pane.fill = True
            pane.set_facecolor(_PANE)
            pane.set_edgecolor(_EDGE)
        ax.tick_params(axis="x", colors=_TICK, labelsize=7)
        ax.tick_params(axis="y", colors=_TICK, labelsize=7)
        ax.tick_params(axis="z", colors=_TICK, labelsize=7)  # type: ignore[arg-type]
        ax.xaxis.line.set_color(_EDGE)  # type: ignore[attr-defined]
        ax.yaxis.line.set_color(_EDGE)  # type: ignore[attr-defined]
        ax.zaxis.line.set_color(_EDGE)
        ax.grid(True, alpha=0.15, linewidth=0.4)
        ax.view_init(elev=22, azim=225)
        return ax


# ─── Canvas 2D mini-coupes ────────────────────────────────────────────────────
class _Canvas2D(FigureCanvas):
    def __init__(self, w=12, h=5):
        self.fig = Figure(figsize=(w, h), facecolor=_BG, tight_layout=True)
        super().__init__(self.fig)
        self.setStyleSheet(f"background:{_BG};")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


# ─── Helpers PLY ──────────────────────────────────────────────────────────────
def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _val_to_rgb_cmap(val: float, vmin: float, vmax: float, cmap_name: str) -> tuple[int, int, int]:
    cmap = plt.get_cmap(cmap_name)
    t = np.clip((val - vmin) / max(vmax - vmin, 1e-9), 0, 1)
    r, g, b, _ = cmap(float(t))
    return int(r * 255), int(g * 255), int(b * 255)


def build_ply_bytes(cloud: PointCloud3D, color_mode: str = "sol") -> bytes:
    """
    Construit un fichier PLY ASCII du nuage de points complet.
    color_mode : "sol"  → couleur du type de sol
                 "Em"   → gradient turbo sur Em
                 "Pl"   → gradient RdYlGn sur Pl
                 "Pf"   → gradient viridis sur Pf
    """
    pts = cloud.points
    n = len(pts)
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {n}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "property float em_mpa",
        "property float pf_mpa",
        "property float pl_mpa",
        "end_header",
    ]

    if color_mode in ("Em", "Pl", "Pf"):
        key_map = {"Em": "Em", "Pl": "Pl", "Pf": "Pf"}
        key = key_map[color_mode]
        cmap_map = {"Em": "turbo", "Pl": "RdYlGn_r", "Pf": "viridis"}
        cmap_n = cmap_map[color_mode]
        raw_vals = [p.get(key) or 0.0 for p in pts]
        vmin, vmax = min(raw_vals), max(raw_vals)

    for p in pts:
        x, y, z = float(p.get("x", 0)), float(p.get("y", 0)), float(p.get("z", 0))
        em = float(p.get("Em") or 0.0)
        pf = float(p.get("Pf") or p.get("pf") or 0.0)
        pl = float(p.get("Pl") or 0.0)
        if color_mode == "sol":
            r, g, b = _hex_to_rgb(p.get("sol_color") or "#888888")
        else:
            val_key = {"Em": em, "Pl": pl, "Pf": pf}[color_mode]
            r, g, b = _val_to_rgb_cmap(val_key, vmin, vmax, cmap_n)
        lines.append(f"{x:.4f} {y:.4f} {z:.4f} {r} {g} {b} {em:.4f} {pf:.4f} {pl:.4f}")

    return "\n".join(lines).encode("utf-8")


# ─── Export Plotly HTML ────────────────────────────────────────────────────────
def build_plotly_html(cloud: PointCloud3D) -> str:
    """
    Génère un fichier HTML autonome avec un nuage Plotly 3D interactif.
    Utilise plotly si installé, sinon génère un HTML d'erreur.
    """
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return ("<html><body style='background:#0b0f1a;color:white;font-family:sans-serif;"
                "padding:40px'><h2>Plotly non installé</h2>"
                "<p>Installez plotly : <code>pip install plotly</code></p></body></html>")

    pts = cloud.points
    xs = [p.get("x", 0) for p in pts]
    ys = [p.get("y", 0) for p in pts]
    zs = [p.get("z", 0) for p in pts]
    em_vals = [p.get("Em") or 0 for p in pts]
    pl_vals = [p.get("Pl") or 0 for p in pts]
    pf_vals = [p.get("Pf") or p.get("pf") or 0 for p in pts]
    sonds   = [p.get("sondage", "?") for p in pts]
    sols    = [p.get("sol_type", "?") for p in pts]
    colors  = [p.get("sol_color", "#888") for p in pts]
    depths  = [abs(p.get("z", 0)) for p in pts]

    hover = [
        f"<b>{s}</b><br>Prof: {d:.1f} m<br>Sol: {sol}<br>"
        f"Em: {em:.2f} MPa<br>Pf: {pf:.3f} MPa<br>Pl: {pl:.3f} MPa"
        for s, d, sol, em, pf, pl in zip(sonds, depths, sols, em_vals, pf_vals, pl_vals)
    ]

    trace_sol = go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="markers",
        marker=dict(size=6, color=colors, opacity=0.85,
                    line=dict(width=0.5, color="rgba(255,255,255,0.3)")),
        text=hover, hoverinfo="text",
        name="Sol (couleur litho)"
    )
    trace_em = go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="markers",
        marker=dict(size=7, color=em_vals, colorscale="Turbo", opacity=0.85,
                    colorbar=dict(title="Em (MPa)", x=1.02, thickness=14,
                                  tickfont=dict(color="white"), titlefont=dict(color="white")),
                    line=dict(width=0.3, color="rgba(255,255,255,0.2)")),
        text=hover, hoverinfo="text",
        name="Em (MPa)", visible=False
    )
    trace_pl = go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="markers",
        marker=dict(size=7, color=pl_vals, colorscale="RdYlGn", reversescale=True,
                    opacity=0.85,
                    colorbar=dict(title="Pl (MPa)", x=1.02, thickness=14,
                                  tickfont=dict(color="white"), titlefont=dict(color="white")),
                    line=dict(width=0.3, color="rgba(255,255,255,0.2)")),
        text=hover, hoverinfo="text",
        name="Pl (MPa)", visible=False
    )
    trace_pf = go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="markers",
        marker=dict(size=7, color=pf_vals, colorscale="Viridis", opacity=0.85,
                    colorbar=dict(title="Pf (MPa)", x=1.02, thickness=14,
                                  tickfont=dict(color="white"), titlefont=dict(color="white")),
                    line=dict(width=0.3, color="rgba(255,255,255,0.2)")),
        text=hover, hoverinfo="text",
        name="Pf (MPa)", visible=False
    )

    # Puit vertical par sondage
    bh_traces = []
    for bh in cloud.boreholes:
        bx, by = bh.get("x_m", 0), bh.get("y_m", 0)
        zmin = cloud.bounds.get("zmin", -30)
        bh_traces.append(go.Scatter3d(
            x=[bx, bx], y=[by, by], z=[zmin, 0],
            mode="lines+text",
            line=dict(color="#38bdf8", width=3),
            text=["", bh.get("name", "?")],
            textfont=dict(color="#38bdf8", size=11),
            textposition="top center",
            showlegend=False
        ))

    fig = go.Figure(data=[trace_sol, trace_em, trace_pl, trace_pf] + bh_traces)

    fig.update_layout(
        title=dict(text="Nuage de points 3D — Sous-sol pressiométrique",
                   font=dict(color="white", size=16)),
        paper_bgcolor="#0b0f1a",
        scene=dict(
            bgcolor="#111827",
            xaxis=dict(title="Easting (m)", color="#64748b", gridcolor="#1e3352"),
            yaxis=dict(title="Northing (m)", color="#64748b", gridcolor="#1e3352"),
            zaxis=dict(title="Profondeur (m)", color="#64748b", gridcolor="#1e3352"),
        ),
        legend=dict(bgcolor="#111827", font=dict(color="white"), x=0, y=1),
        updatemenus=[dict(
            type="buttons", direction="right",
            x=0.5, xanchor="center", y=1.08,
            bgcolor="#1e3352", font=dict(color="white"),
            buttons=[
                dict(label="Lithologie", method="update",
                     args=[{"visible": [True, False, False, False] + [True]*len(bh_traces)}]),
                dict(label="Em (MPa)", method="update",
                     args=[{"visible": [False, True, False, False] + [True]*len(bh_traces)}]),
                dict(label="Pl (MPa)", method="update",
                     args=[{"visible": [False, False, True, False] + [True]*len(bh_traces)}]),
                dict(label="Pf (MPa)", method="update",
                     args=[{"visible": [False, False, False, True] + [True]*len(bh_traces)}]),
            ]
        )]
    )

    return pio.to_html(fig, full_html=True, include_plotlyjs="cdn",
                       config={"displayModeBar": True, "scrollZoom": True})


# ─── Export SVG sous-sol ──────────────────────────────────────────────────────
def build_svg_bytes(cloud: PointCloud3D,
                    cleaned_map: Dict[str, CleanedEssai],
                    params_map: Dict[str, PressiometricParams]) -> bytes:
    """
    SVG de synthèse : coupe stratigraphique + légendes Em/Pl/Pf.
    """
    n_bh = len(cloud.boreholes) or 1
    fig_w = max(12, n_bh * 2.5)
    fig = Figure(figsize=(fig_w, 8), facecolor=_BG)
    canvas_svg = FigureCanvasSVG(fig)

    ax = fig.add_subplot(111)
    ax.set_facecolor(_PANE)
    ax.tick_params(colors=_TICK)
    for sp in ax.spines.values():
        sp.set_edgecolor(_EDGE)

    from collections import defaultdict
    by_sond: Dict[str, list] = defaultdict(list)
    sond_x: Dict[str, float] = {}
    for bh in cloud.boreholes:
        sond_x[bh["name"]] = bh.get("x_m", 0)

    for pt in cloud.points:
        by_sond[pt.get("sondage", "SP")].append(pt)

    legend_items: Dict[str, str] = {}
    for sond, pts in by_sond.items():
        x0 = sond_x.get(sond, 0)
        pts_sorted = sorted(pts, key=lambda p: abs(p.get("z", 0)))
        for i, pt in enumerate(pts_sorted):
            z_top = -abs(pt.get("z", 0))
            thick = abs(pts_sorted[i+1].get("z", 0)) - abs(pt.get("z", 0)) if i+1 < len(pts_sorted) else 2.0
            color = pt.get("sol_color") or "#888"
            rect = mpatches.FancyBboxPatch(
                (x0 - 0.7, z_top), 1.4, -thick,
                boxstyle="square,pad=0", facecolor=color, edgecolor="#444", alpha=0.85
            )
            ax.add_patch(rect)
            em = pt.get("Em") or 0
            pl = pt.get("Pl") or 0
            pf = pt.get("Pf") or pt.get("pf") or 0
            ax.text(x0, z_top - thick / 2,
                    f"Em:{em:.0f}\nPf:{pf:.2f}\nPl:{pl:.2f}",
                    ha="center", va="center", color="white", fontsize=5.5,
                    fontfamily="monospace")
            legend_items[pt.get("sol_type", "?")] = color
        ax.text(x0, 0.4, sond, ha="center", color=_CYAN, fontsize=8, fontweight="bold")

    all_z = [pt.get("z", 0) for pt in cloud.points]
    all_x = [sond_x.get(pt.get("sondage", "SP"), 0) for pt in cloud.points]
    ax.set_xlim(min(all_x) - 3, max(all_x) + 3)
    ax.set_ylim(min(all_z) - 2, 2)
    ax.set_xlabel("Easting (m)", color=_TICK, fontsize=9)
    ax.set_ylabel("Profondeur (m)", color=_TICK, fontsize=9)
    ax.xaxis.label.set_color(_TICK)
    ax.yaxis.label.set_color(_TICK)
    ax.set_title("Coupe synthétique du sous-sol — Em / Pf / Pl", color="white", fontsize=11)

    patches = [mpatches.Patch(color=c, label=t[:28]) for t, c in list(legend_items.items())[:10]]
    ax.legend(handles=patches, fontsize=6.5, facecolor=_PANE, labelcolor="white",
              loc="lower right", ncol=2)

    fig.tight_layout()
    buf = io.BytesIO()
    canvas_svg.print_svg(buf)
    return buf.getvalue().encode("utf-8") if isinstance(buf.getvalue(), str) else buf.getvalue()


# ─── Mini-coupes pression/volume ──────────────────────────────────────────────
def draw_mini_pv_curves(fig: Figure,
                        cleaned_map: Dict[str, CleanedEssai],
                        params_map:  Dict[str, PressiometricParams]):
    """
    Dessine les courbes P-V (pression vs volume moyen) de chaque essai
    en format vertical (P en ordonnée, V en abscisse) dans une grille.
    Zones élastique / plastique / rupture colorées.
    """
    fig.clear()
    fig.patch.set_facecolor(_BG)

    sheets = [s for s in cleaned_map if cleaned_map[s].points]
    if not sheets:
        ax = fig.add_subplot(111)
        ax.set_facecolor(_PANE)
        ax.text(0.5, 0.5, "Aucune courbe P-V disponible",
                ha="center", va="center", color="#aaa", fontsize=11, transform=ax.transAxes)
        return

    n = len(sheets)
    ncols = min(4, n)
    nrows = (n + ncols - 1) // ncols
    gs = gridspec.GridSpec(nrows, ncols, figure=fig, hspace=0.6, wspace=0.45)

    for idx, sheet in enumerate(sheets):
        cleaned = cleaned_map[sheet]
        params  = params_map.get(sheet)
        ax = fig.add_subplot(gs[idx // ncols, idx % ncols])
        ax.set_facecolor(_PANE)
        ax.tick_params(colors=_TICK, labelsize=6)
        for sp in ax.spines.values():
            sp.set_edgecolor(_EDGE)

        pts = [p for p in cleaned.points if not p.anomalie]
        if len(pts) < 2:
            ax.text(0.5, 0.5, "N/A", ha="center", va="center",
                    color="#aaa", transform=ax.transAxes, fontsize=9)
            ax.set_title(sheet[:18], color=_TICK, fontsize=7)
            continue

        p_arr  = np.array([pt.P60_corr_MPa for pt in pts])
        v60    = np.array([(pt.V60_smooth_cm3 or pt.V60_corr_cm3 or 0) for pt in pts])
        v30    = np.array([(pt.V30_smooth_cm3 or pt.V30_corr_cm3 or 0) for pt in pts])
        vm     = (v60 + v30) / 2.0
        creep  = v60 - v30

        # Courbe principale P-V (verticale : P en Y, Vm en X)
        ax.plot(vm, p_arr, color=_CYAN, lw=1.5, zorder=4, label="P-V")
        ax.scatter(vm, p_arr, color=_CYAN, s=10, zorder=5)

        # Zone élastique (entre Pf et Pl)
        if params and params.Pf_MPa and params.Pl_MPa:
            pf_v = params.Pf_MPa
            pl_v = params.Pl_MPa
            # Fond zone elasto-plastique
            ax.axhspan(pf_v, pl_v, color="#2ec4b622", zorder=1)
            ax.axhline(pf_v, color="#2ec4b6", lw=0.8, ls="--", zorder=3)
            ax.axhline(pl_v, color=_GOLD,    lw=0.8, ls="--", zorder=3)
            ax.text(vm.max() * 0.98, pf_v, f"Pf={pf_v:.2f}", color="#2ec4b6",
                    fontsize=5, va="bottom", ha="right")
            ax.text(vm.max() * 0.98, pl_v, f"Pl={pl_v:.2f}", color=_GOLD,
                    fontsize=5, va="top", ha="right")
        elif params and params.Pl_MPa:
            ax.axhline(params.Pl_MPa, color=_GOLD, lw=0.8, ls="--", zorder=3)

        # Courbe de fluage (creep) en surimpression — axe secondaire
        if creep.max() > 0:
            ax2 = ax.twiny()
            ax2.plot(creep, p_arr, color=_ORG, lw=0.9, ls=":", alpha=0.7, zorder=2)
            ax2.tick_params(colors=_ORG, labelsize=5)
            ax2.set_xlabel("Creep (cm³)", color=_ORG, fontsize=5, labelpad=2)
            for sp in ax2.spines.values():
                sp.set_edgecolor(_EDGE)

        depth_str = f"z={cleaned.depth_m:.1f}m" if cleaned.depth_m else ""
        sond_str  = (params.ref_sondage or "") if params else ""
        qual_str  = (params.qualite or "?") if params else "?"
        em_str    = f"Em={params.Em_MPa:.0f}" if (params and params.Em_MPa) else ""
        ax.set_title(f"{sond_str} {depth_str} | Q:{qual_str} {em_str}",
                     color=_CYAN, fontsize=6, pad=3)
        ax.set_xlabel("Vm (cm³)", color=_TICK, fontsize=6, labelpad=2)
        ax.set_ylabel("P (MPa)", color=_TICK, fontsize=6, labelpad=2)
        ax.xaxis.label.set_color(_TICK)
        ax.yaxis.label.set_color(_TICK)

    fig.suptitle("Courbes pressiométriques P-V — tous essais", color="white",
                 fontsize=10, y=1.01)


# ─── Widget principal ─────────────────────────────────────────────────────────
class Cloud3DTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cloud:       Optional[PointCloud3D]                  = None
        self._cleaned_map: Dict[str, CleanedEssai]                 = {}
        self._params_map:  Dict[str, PressiometricParams]          = {}
        self._build_ui()
        self._draw_placeholder()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(4)

        # ── Barre du haut ──────────────────────────────────────────────────
        top = QHBoxLayout()
        lbl = QLabel("Nuage de points 3D — Reconstruction du sous-sol")
        lbl.setStyleSheet(f"font-weight:bold; color:{_CYAN}; font-size:13px;")
        top.addWidget(lbl)
        top.addStretch()

        top.addWidget(QLabel("Couche :"))
        self.cmb = QComboBox()
        self.cmb.addItems(list(_LAYER_CFG.keys()))
        self.cmb.currentTextChanged.connect(self._on_layer_changed)
        top.addWidget(self.cmb)

        btn_reset = QPushButton("↺ Vue")
        btn_reset.setFixedWidth(60)
        btn_reset.clicked.connect(self._reset_view)
        top.addWidget(btn_reset)

        # Export buttons
        for label, slot, color in [
            ("⬇ PNG",        self._export_png,     "#334155"),
            ("⬇ PLY (sol)",  self._export_ply_sol,  "#1e4d6b"),
            ("⬇ PLY (Em)",   self._export_ply_em,   "#1e6b4d"),
            ("⬇ HTML Plotly",self._export_plotly,   _GOLD),
            ("⬇ SVG coupe",  self._export_svg,      _ORG),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"background:{color}; color:white; padding:3px 8px;"
                " border-radius:3px; font-size:11px;")
            btn.clicked.connect(slot)
            top.addWidget(btn)

        root.addLayout(top)

        # ── Onglets internes : 3D / Mini-coupes ───────────────────────────
        self.inner_tabs = QTabWidget()
        self.inner_tabs.setStyleSheet(
            f"QTabWidget::pane{{background:{_PANE}; border:1px solid {_EDGE};}}"
            f"QTabBar::tab{{background:{_PANE}; color:{_TICK}; padding:5px 14px;}}"
            f"QTabBar::tab:selected{{color:white; background:{_EDGE};}}"
        )
        root.addWidget(self.inner_tabs, stretch=1)

        # Tab 1 : Nuage 3D matplotlib
        tab3d = QWidget()
        lay3d = QVBoxLayout(tab3d)
        lay3d.setContentsMargins(0, 0, 0, 0)
        self.canvas = _Canvas3D()
        lay3d.addWidget(self.canvas, stretch=1)
        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)
        self.mpl_toolbar.setStyleSheet(f"background:{_PANE}; border:none;")
        lay3d.addWidget(self.mpl_toolbar)
        self.lbl_info = QLabel("Aucun nuage — lancez Analyser tout pour générer la reconstruction 3D.")
        self.lbl_info.setStyleSheet(f"color:{_TICK}; font-size:10px; padding:2px 4px;")
        lay3d.addWidget(self.lbl_info)
        self.inner_tabs.addTab(tab3d, "🌐 3D Matplotlib")

        # Tab 2 : Mini-coupes P-V
        tab_pv = QWidget()
        lay_pv = QVBoxLayout(tab_pv)
        lay_pv.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{_BG}; border:none;")
        self.canvas_pv = _Canvas2D(14, 6)
        scroll.setWidget(self.canvas_pv)
        lay_pv.addWidget(scroll)
        self.inner_tabs.addTab(tab_pv, "📈 Courbes P-V")

    # ── Données ───────────────────────────────────────────────────────────────

    def refresh(self, cloud: Optional[PointCloud3D],
                cleaned_map: Optional[Dict[str, CleanedEssai]] = None,
                params_map:  Optional[Dict[str, PressiometricParams]] = None):
        self._cloud       = cloud
        self._cleaned_map = cleaned_map or {}
        self._params_map  = params_map  or {}
        self._render(self.cmb.currentText())
        self._render_pv_curves()

    # ── Rendu 3D matplotlib ───────────────────────────────────────────────────

    def _draw_placeholder(self):
        ax = self.canvas.fresh_ax()
        rng = np.random.default_rng(42)
        n   = 80
        x   = rng.uniform(-60, 60, n)
        y   = rng.uniform(-60, 60, n)
        z   = rng.uniform(-25, 0,  n)
        c   = rng.uniform(0,   1,  n)
        sc = ax.scatter(x, y, z, c=c, cmap="turbo",
                        s=55, alpha=0.65, edgecolors="none", depthshade=True)  # type: ignore
        for xi, yi, zi in zip(x[::4], y[::4], z[::4]):
            ax.plot([xi, xi], [yi, yi], [zi, 0], color="#ffffff12", lw=0.6)
        ax.set_xlabel("Easting (m)",  color=_TICK, labelpad=8, fontsize=8)
        ax.set_ylabel("Northing (m)", color=_TICK, labelpad=8, fontsize=8)
        ax.set_zlabel("Prof. (m)",    color=_TICK, labelpad=8, fontsize=8)
        ax.set_title("DEMONSTRATION — Chargez et analysez vos essais",
                     color="#fbbf24", pad=10, fontsize=10)
        cbar = self.canvas.fig.colorbar(sc, ax=ax, shrink=0.45, pad=0.08, aspect=25)
        cbar.set_label("Valeur normalisée", color=_TICK, size=8)
        cbar.ax.tick_params(colors=_TICK, labelsize=7)
        self.canvas.draw()

    def _on_layer_changed(self, layer: str):
        self._render(layer)

    def _render(self, layer: str):
        if not self._cloud:
            self._draw_placeholder()
            return

        cloud = self._cloud
        xs = np.asarray([p["x"] for p in cloud.points], dtype=float)
        ys = np.asarray([p["y"] for p in cloud.points], dtype=float)
        zs = np.asarray([p["z"] for p in cloud.points], dtype=float)

        key_map = {"Em_MPa": "Em", "Pf_MPa": "Pf", "Pl_MPa": "Pl"}
        raw_key = key_map.get(layer, "Em")
        raw_vals = [p.get(raw_key) for p in cloud.points]
        vals = np.array([v if v is not None else np.nan for v in raw_vals], dtype=float)

        if len(xs) == 0 or np.all(np.isnan(vals)):
            self._draw_placeholder()
            self.lbl_info.setText("Données insuffisantes pour afficher le nuage 3D.")
            return

        cmap_name, unit, _, _ = _LAYER_CFG[layer]
        v_min = float(np.nanmin(vals))
        v_max = float(np.nanmax(vals))
        if v_min == v_max:
            v_max = v_min + 1e-3

        ax = self.canvas.fresh_ax()

        sc = ax.scatter(xs, ys, zs,
                        c=vals, cmap=cmap_name,
                        vmin=v_min, vmax=v_max,
                        s=90, alpha=0.88,
                        edgecolors="#ffffff22", linewidths=0.5,
                        depthshade=True, zorder=5)  # type: ignore

        for xi, yi, zi in zip(xs, ys, zs):
            ax.plot([xi, xi], [yi, yi], [zi, 0],
                    color="#ffffff14", lw=0.7, linestyle="--")

        # Ombre au sol
        ax.scatter(xs, ys, np.zeros_like(zs),
                   c=vals, cmap=cmap_name, vmin=v_min, vmax=v_max,
                   s=18, alpha=0.30, edgecolors="none")  # type: ignore

        # Puits de sondage
        for bh in cloud.boreholes:
            bx, by = float(bh.get("x_m", 0)), float(bh.get("y_m", 0))
            ax.plot([bx, bx], [by, by], [float(cloud.bounds.get("zmin", -30)), 0],
                    color="#38bdf8", lw=2, zorder=10)
            ax.text(bx, by, 0.5, bh.get("name", "?"),
                    color="#38bdf8", fontsize=8, fontweight="bold")

        ax.set_xlabel("Easting (m)",  color=_TICK, labelpad=8, fontsize=8)
        ax.set_ylabel("Northing (m)", color=_TICK, labelpad=8, fontsize=8)
        ax.set_zlabel("Prof. (m)",    color=_TICK, labelpad=8, fontsize=8)
        title_lyr = layer.replace("_MPa", "")
        ax.set_title(f"Nuage 3D complet — {title_lyr}  [{unit}]",
                     color=_CYAN, pad=10, fontsize=11, fontweight="bold")

        cbar = self.canvas.fig.colorbar(sc, ax=ax, shrink=0.45, pad=0.08, aspect=25)
        cbar.set_label(unit, color=_TICK, size=8)
        cbar.ax.tick_params(colors=_TICK, labelsize=7)
        self.canvas.draw()

        valid = int(np.sum(~np.isnan(vals)))
        self.lbl_info.setText(
            f"Couche : {layer}  |  {valid} points  |  "
            f"Min={v_min:.3f}  Max={v_max:.3f}  Moy={float(np.nanmean(vals)):.3f}  {unit}"
        )

    def _render_pv_curves(self):
        draw_mini_pv_curves(self.canvas_pv.fig, self._cleaned_map, self._params_map)
        try:
            self.canvas_pv.fig.tight_layout()
        except Exception:
            pass
        self.canvas_pv.draw()

    # ── Vue / Zoom ────────────────────────────────────────────────────────────

    def _reset_view(self):
        axes = self.canvas.fig.axes
        if axes:
            cast(_Axes3D, axes[0]).view_init(elev=22, azim=225)
            self.canvas.draw()

    # ── Exports ───────────────────────────────────────────────────────────────

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter nuage 3D PNG", "nuage_3d.png", "PNG (*.png)")
        if path:
            self.canvas.fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_BG)

    def _export_ply(self, color_mode: str):
        if not self._cloud or not self._cloud.points:
            QMessageBox.warning(self, "Export PLY", "Aucun nuage disponible.")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer nuage PLY",
            f"nuage_{color_mode}_{ts}.ply", "Point Cloud PLY (*.ply)")
        if not path:
            return
        try:
            data = build_ply_bytes(self._cloud, color_mode)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Export PLY", f"Nuage exporté :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur PLY", str(e))

    def _export_ply_sol(self):  self._export_ply("sol")
    def _export_ply_em(self):   self._export_ply("Em")

    def _export_plotly(self):
        if not self._cloud or not self._cloud.points:
            QMessageBox.warning(self, "Export Plotly", "Aucun nuage disponible.")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter Plotly 3D HTML",
            f"nuage_plotly_{ts}.html", "HTML (*.html)")
        if not path:
            return
        try:
            html = build_plotly_html(self._cloud)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            webbrowser.open(f"file:///{path.replace(os.sep, '/')}")
            QMessageBox.information(self, "Export Plotly",
                                    f"Fichier ouvert dans le navigateur :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur Plotly", str(e))

    def _export_svg(self):
        if not self._cloud or not self._cloud.points:
            QMessageBox.warning(self, "Export SVG", "Aucun nuage disponible.")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter coupe SVG",
            f"coupe_subsol_{ts}.svg", "SVG (*.svg)")
        if not path:
            return
        try:
            data = build_svg_bytes(self._cloud, self._cleaned_map, self._params_map)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Export SVG", f"Coupe SVG exportée :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur SVG", str(e))
