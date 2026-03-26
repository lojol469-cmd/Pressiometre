"""
Onglet Coupes 2D Géotechniques — 10 vues analytiques du sous-sol.
Coupes explicatives avec légendes, interpolation et classification Ménard.
"""
from __future__ import annotations
from typing import Dict, Optional, List
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
import matplotlib.cm as cm
from matplotlib.colors import Normalize

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFileDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt

from api.models import PressiometricParams, CleanedEssai

_BG   = "#0b0f1a"
_TICK = "#94a3b8"
_GRID = "#1e2a3a"
_PAL  = ["#38bdf8","#06d6a0","#ffd166","#ef476f","#9b5de5",
         "#f15bb5","#00bbf9","#fee440","#00f5d4","#e63946"]


def _style_ax(ax, title: str, xlabel: str, ylabel: str, max_depth: float,
              invert_y: bool = True):
    ax.set_facecolor(_BG)
    ax.tick_params(colors=_TICK, labelsize=7)
    ax.xaxis.label.set_color(_TICK)
    ax.yaxis.label.set_color(_TICK)
    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_title(title, color="#e2e8f0", fontsize=9, fontweight="bold", pad=6)
    if invert_y:
        ax.set_ylim(max_depth + 1, -0.5)
    ax.grid(True, color=_GRID, lw=0.4, alpha=0.6)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2d3a50")


class SubsurfaceTab(QWidget):
    """10 coupes 2D explicatives du sous-sol pressiométrique."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._params_map: Dict[str, PressiometricParams] = {}
        self._cleaned_map: Dict[str, CleanedEssai] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barre de contrôles
        top = QHBoxLayout()
        lbl = QLabel("Coupes 2D géotechniques — 10 vues analytiques du sous-sol")
        lbl.setStyleSheet("font-weight:bold; color:#38bdf8; font-size:13px;")
        top.addWidget(lbl)
        top.addStretch()
        btn_export = QPushButton("Exporter PNG")
        btn_export.setFixedWidth(120)
        btn_export.clicked.connect(self._export_png)
        top.addWidget(btn_export)
        layout.addLayout(top)

        # Canvas matplotlib dans un scroll area
        self.canvas = FigureCanvas(Figure(figsize=(16, 30), facecolor=_BG))
        self.canvas.setStyleSheet(f"background:{_BG};")
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setWidget(self.canvas)
        scroll.setStyleSheet("background:#0b0f1a; border:none;")
        layout.addWidget(scroll, stretch=1)

        # Placeholder
        self._draw_placeholder()

    def _draw_placeholder(self):
        fig = self.canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor(_BG)
        ax.text(0.5, 0.5,
                "Analysez les essais pour afficher les 10 coupes 2D.",
                ha="center", va="center", color="#64748b", fontsize=13,
                transform=ax.transAxes)
        ax.axis("off")
        self.canvas.draw()

    def refresh(self, params_map: Dict[str, PressiometricParams],
                cleaned_map: Dict[str, CleanedEssai]):
        self._params_map = params_map
        self._cleaned_map = cleaned_map
        self._draw()

    # ─── Dessin des 10 coupes ────────────────────────────────────────────────
    def _draw(self):
        fig = self.canvas.figure
        fig.clear()
        params = list(self._params_map.values())

        if not params:
            self._draw_placeholder()
            return

        # Regrouper par sondage
        by_sond: Dict[str, List[PressiometricParams]] = defaultdict(list)
        for p in params:
            key = p.ref_sondage or (p.sheet_name.split()[0] if p.sheet_name else "SP")
            by_sond[key].append(p)
        for k in by_sond:
            by_sond[k].sort(key=lambda x: x.depth_m or 0)
        sondages = sorted(by_sond.keys())
        sond_col = {s: _PAL[i % len(_PAL)] for i, s in enumerate(sondages)}

        all_depths = [p.depth_m for p in params if p.depth_m is not None]
        max_depth  = max(all_depths) if all_depths else 30.0

        # ── 5 lignes × 2 colonnes ──────────────────────────────────────────
        gs = fig.add_gridspec(5, 2, hspace=0.60, wspace=0.38,
                              left=0.08, right=0.96, top=0.97, bottom=0.03)
        axes = [fig.add_subplot(gs[r, c]) for r in range(5) for c in range(2)]

        # ── Coupe 1 : Em vs profondeur ───────────────────────────────────────
        ax = axes[0]
        _style_ax(ax, "① Module Em (MPa) vs Profondeur", "Em (MPa)", "Profondeur (m)", max_depth)
        legend_h: list = []
        for sond in sondages:
            pts = by_sond[sond]
            d   = [p.depth_m for p in pts if p.depth_m is not None]
            em  = [p.Em_MPa or 0 for p in pts if p.depth_m is not None]
            c   = sond_col[sond]
            ax.fill_betweenx(d, em, alpha=0.18, color=c)
            ax.plot(em, d, "o-", color=c, lw=1.8, ms=5)
            legend_h.append(mpatches.Patch(color=c, label=sond))
        ax.axvline(0, color="#334", lw=0.8)
        ax.legend(handles=legend_h, fontsize=6, facecolor="#111827",
                  labelcolor="white", loc="lower right", ncol=2)
        # Annoter la plage NC/SC
        em_vals = [p.Em_MPa for p in params if p.Em_MPa]
        if em_vals:
            xmax = max(em_vals) * 1.1
            ax.set_xlim(-xmax * 0.05, xmax)

        # ── Coupe 2 : Pl vs profondeur ───────────────────────────────────────
        ax = axes[1]
        _style_ax(ax, "② Pression Limite Pl (MPa) vs Profondeur", "Pl (MPa)", "Profondeur (m)", max_depth)
        for sond in sondages:
            pts = by_sond[sond]
            d   = [p.depth_m for p in pts if p.depth_m is not None]
            pl  = [p.Pl_MPa or 0 for p in pts if p.depth_m is not None]
            c   = sond_col[sond]
            ax.fill_betweenx(d, pl, alpha=0.18, color=c)
            ax.plot(pl, d, "s-", color=c, lw=1.8, ms=5, label=sond)
            if d:
                ax.text((pl[-1] or 0) + 0.03, d[-1], sond,
                        color=c, fontsize=6, va="center")
        ax.axvline(0, color="#334", lw=0.8)
        # Zones de résistance
        ax.axvspan(0, 0.3, alpha=0.05, color="#4a9e8b",  label="Tourbe < 0.3 MPa")
        ax.axvspan(0.3, 1.0, alpha=0.05, color="#5b9e6e", label="Argile 0.3–1 MPa")
        ax.axvspan(1.0, 2.0, alpha=0.05, color="#d4b483", label="Sable 1–2 MPa")
        ax.axvspan(2.0, 8.0, alpha=0.05, color="#8b6b32", label="Dense > 2 MPa")

        # ── Coupe 3 : Pf vs profondeur ───────────────────────────────────────
        ax = axes[2]
        _style_ax(ax, "③ Pression de Fluage Pf (MPa) vs Profondeur", "Pf (MPa)", "Profondeur (m)", max_depth)
        for sond in sondages:
            pts = by_sond[sond]
            d   = [p.depth_m for p in pts if p.depth_m is not None]
            pf  = [p.Pf_MPa or 0 for p in pts if p.depth_m is not None]
            c   = sond_col[sond]
            ax.fill_betweenx(d, pf, alpha=0.20, color=c)
            ax.plot(pf, d, "^-", color=c, lw=1.5, ms=4, label=sond)
        ax.axvline(0, color="#334", lw=0.8)
        ax.legend(fontsize=6, facecolor="#111827", labelcolor="white", loc="lower right")

        # ── Coupe 4 : Rapport Em/Pl ──────────────────────────────────────────
        ax = axes[3]
        _style_ax(ax, "④ Rapport Em/Pl — Consolidation (NF P 94-110)", "Em / Pl", "Profondeur (m)", max_depth)
        ax.axvspan(-1, 7,  alpha=0.08, color="#ef476f",  label="< 7 remanié / perturbé")
        ax.axvspan(7,  12, alpha=0.08, color="#06d6a0",  label="7–12 consolidé normal")
        ax.axvspan(12, 60, alpha=0.05, color="#ffd166",  label="> 12 surconsolidé")
        ax.axvline(7,  color="#ef476f", lw=1, ls="--", alpha=0.7)
        ax.axvline(12, color="#06d6a0", lw=1, ls="--", alpha=0.7)
        for sond in sondages:
            pts = by_sond[sond]
            d  = [p.depth_m for p in pts if p.depth_m is not None and p.ratio_Em_Pl is not None]
            rt = [p.ratio_Em_Pl for p in pts if p.depth_m is not None and p.ratio_Em_Pl is not None]
            if d:
                ax.plot(rt, d, "D-", color=sond_col[sond], lw=1.5, ms=5, label=sond)
        ratio_all = [p.ratio_Em_Pl for p in params if p.ratio_Em_Pl]
        ax.set_xlim(0, max(ratio_all) * 1.1 if ratio_all else 20)
        ax.legend(fontsize=6, facecolor="#111827", labelcolor="white", loc="lower right", ncol=2)

        # ── Coupe 5 : Classification géotechnique ────────────────────────────
        ax = axes[4]
        _style_ax(ax, "⑤ Classification géotechnique Ménard", "Sondage", "Profondeur (m)", max_depth)
        ax.set_xlim(-0.5, len(sondages) - 0.5)
        ax.set_xticks(range(len(sondages)))
        ax.set_xticklabels(sondages, rotation=30, ha="right", fontsize=7, color=_TICK)
        for xi, sond in enumerate(sondages):
            pts = [p for p in by_sond[sond] if p.depth_m is not None]
            for i, p in enumerate(pts):
                d0: float = float(p.depth_m)  # type: ignore[arg-type]
                d1: float = float(pts[i+1].depth_m) if i+1 < len(pts) else d0 + 2.0  # type: ignore[arg-type]
                ax.barh(d0, 0.8, left=xi - 0.4, height=d1 - d0,
                        color=p.sol_color or "#888", alpha=0.85, align="edge",
                        edgecolor="#1a1a2a")
                if (d1 - d0) > 1.5:
                    ax.text(xi, d0 + (d1 - d0) / 2,
                            (p.sol_type or "?")[:16],
                            ha="center", va="center", color="white", fontsize=5)
        unique_sols = {}
        for p in params:
            if p.sol_type not in unique_sols:
                unique_sols[p.sol_type] = p.sol_color
        sol_patches = [mpatches.Patch(color=c or "#888", label=(t or "?")[:24])
                       for t, c in list(unique_sols.items())[:8]]
        ax.legend(handles=sol_patches, fontsize=5.5, facecolor="#111827",
                  labelcolor="white", loc="lower right", ncol=1)

        # ── Coupe 6 : NC / SC par profondeur ─────────────────────────────────
        ax = axes[5]
        _style_ax(ax, "⑥ Zones NC / SC par sondage (Ménard)", "Sondage", "Profondeur (m)", max_depth)
        ax.set_xlim(-0.5, len(sondages) - 0.5)
        ax.set_xticks(range(len(sondages)))
        ax.set_xticklabels(sondages, rotation=30, ha="right", fontsize=7, color=_TICK)
        for xi, sond in enumerate(sondages):
            pts = [p for p in by_sond[sond] if p.depth_m is not None]
            for i, p in enumerate(pts):
                d0: float = float(p.depth_m)  # type: ignore[arg-type]
                d1: float = float(pts[i+1].depth_m) if i+1 < len(pts) else d0 + 2.0  # type: ignore[arg-type]
                c  = "#5b8dee" if p.nc_status == "NC" else "#ef8c3f"
                ax.barh(d0, 0.8, left=xi - 0.4, height=d1 - d0,
                        color=c, alpha=0.85, align="edge", edgecolor="#1a1a2a")
                ax.text(xi, d0 + (d1 - d0) / 2, p.nc_status or "?",
                        ha="center", va="center", color="white", fontsize=7, fontweight="bold")
        ax.legend(handles=[
            mpatches.Patch(color="#5b8dee", label="NC — Normalement Consolidé"),
            mpatches.Patch(color="#ef8c3f", label="SC — Surconsolidé"),
        ], fontsize=7, facecolor="#111827", labelcolor="white", loc="upper right")

        # ── Coupe 7 : Qualité A→D par profondeur ─────────────────────────────
        ax = axes[6]
        _style_ax(ax, "⑦ Qualité des essais (A=excellent → D=médiocre)", "Sondage", "Profondeur (m)", max_depth)
        ax.set_xlim(-0.5, len(sondages) - 0.5)
        ax.set_xticks(range(len(sondages)))
        ax.set_xticklabels(sondages, rotation=30, ha="right", fontsize=7, color=_TICK)
        QUAL_C = {"A": "#06d6a0", "B": "#ffd166", "C": "#ef8c3f", "D": "#ef476f", "?": "#555"}
        for xi, sond in enumerate(sondages):
            pts = [p for p in by_sond[sond] if p.depth_m is not None]
            for i, p in enumerate(pts):
                d0: float = float(p.depth_m)  # type: ignore[arg-type]
                d1: float = float(pts[i+1].depth_m) if i+1 < len(pts) else d0 + 2.0  # type: ignore[arg-type]
                c = QUAL_C.get(p.qualite or "?", "#555")
                ax.barh(d0, 0.8, left=xi - 0.4, height=d1 - d0,
                        color=c, alpha=0.9, align="edge", edgecolor="#1a1a2a")
                ax.text(xi, d0 + (d1 - d0) / 2, p.qualite or "?",
                        ha="center", va="center", color="black", fontsize=9, fontweight="bold")
        ax.legend(handles=[
            mpatches.Patch(color=v, label=f"Qualité {k} : {desc}")
            for k, v, desc in [("A","#06d6a0","Excellent"),("B","#ffd166","Bon"),
                                ("C","#ef8c3f","Acceptable"),("D","#ef476f","Médiocre")]
        ], fontsize=6.5, facecolor="#111827", labelcolor="white", loc="lower right")

        # ── Coupe 8 : Em normalisé (raideur relative) ─────────────────────────
        ax = axes[7]
        _style_ax(ax, "⑧ Raideur relative Em / Em_max — Rigidité du sol", "Em normalisé", "Profondeur (m)", max_depth)
        em_max = max((p.Em_MPa or 0 for p in params), default=1) or 1
        for sond in sondages:
            pts = [p for p in by_sond[sond] if p.depth_m is not None and p.Em_MPa is not None]
            d   = [p.depth_m for p in pts]
            emn = [(p.Em_MPa or 0) / em_max for p in pts]
            c   = sond_col[sond]
            ax.barh(d, emn, height=1.5, color=c, alpha=0.65, label=sond, align="center")
        # Zones indicatives
        ax.axvspan(0, 0.25, alpha=0.07, color="#ef476f",  label="Sol mou < 25%")
        ax.axvspan(0.25, 0.6, alpha=0.05, color="#ffd166", label="Sol moyen 25–60%")
        ax.axvspan(0.6, 1.0, alpha=0.05, color="#06d6a0",  label="Sol raide > 60%")
        ax.axvline(1.0, color="#fff", lw=0.5, ls="--", alpha=0.3)
        ax.set_xlim(0, 1.05)
        ax.legend(fontsize=6, facecolor="#111827", labelcolor="white", loc="lower right", ncol=2)

        # ── Coupe 9 : Coupe 2D interpolée Em ─────────────────────────────────
        ax = axes[8]
        ax.set_facecolor(_BG)
        ax.tick_params(colors=_TICK, labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2d3a50")
        ax.set_title("⑨ Coupe 2D interpolée — Module Em (MPa)",
                     color="#e2e8f0", fontsize=9, fontweight="bold", pad=6)

        self._draw_interp_coupe(fig, ax, params, by_sond, sondages, max_depth,
                                layer="Em", cmap="RdYlGn_r", unit="Em (MPa)")

        # ── Coupe 10 : Coupe 2D interpolée Pl ────────────────────────────────
        ax = axes[9]
        ax.set_facecolor(_BG)
        ax.tick_params(colors=_TICK, labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2d3a50")
        ax.set_title("⑩ Coupe 2D interpolée — Pression Limite Pl (MPa)",
                     color="#e2e8f0", fontsize=9, fontweight="bold", pad=6)

        self._draw_interp_coupe(fig, ax, params, by_sond, sondages, max_depth,
                                layer="Pl", cmap="plasma", unit="Pl (MPa)")

        self.canvas.figure.set_size_inches(16, 30)
        self.canvas.draw()

    # ─── Coupe 2D interpolée helper ──────────────────────────────────────────
    def _draw_interp_coupe(self, fig, ax, params, by_sond, sondages, max_depth,
                           layer: str, cmap: str, unit: str):
        from scipy.interpolate import griddata

        if len(sondages) < 2:
            ax.text(0.5, 0.5,
                    "Un seul sondage chargé.\nChargez plusieurs sondages\npour la coupe interpolée.",
                    ha="center", va="center", color="#64748b", fontsize=9,
                    transform=ax.transAxes)
            return

        sond_x = {s: float(i * 10) for i, s in enumerate(sondages)}
        xs, ds, vals = [], [], []
        for p in params:
            if p.depth_m is None:
                continue
            val = p.Em_MPa if layer == "Em" else p.Pl_MPa
            if val is None:
                continue
            sond_key = p.ref_sondage or (p.sheet_name.split()[0] if p.sheet_name else "SP")
            xs.append(sond_x.get(sond_key, 0.0))
            ds.append(p.depth_m)
            vals.append(val)

        if len(xs) < 4:
            ax.text(0.5, 0.5, "Données insuffisantes\n(< 4 points)",
                    ha="center", va="center", color="#64748b", fontsize=9,
                    transform=ax.transAxes)
            return

        x_max = (len(sondages) - 1) * 10
        xi = np.linspace(0, x_max, 120)
        di = np.linspace(0, max_depth, 120)
        xg, dg = np.meshgrid(xi, di)

        try:
            grid = griddata((xs, ds), vals, (xg, dg), method="linear")
            grid_nn = griddata((xs, ds), vals, (xg, dg), method="nearest")
            mask = np.isnan(grid)
            grid[mask] = grid_nn[mask]

            levels = 15
            cf = ax.contourf(xg, dg, grid, levels=levels, cmap=cmap)
            ax.contour(xg, dg, grid, levels=8, colors="#ffffff25", linewidths=0.4)

            cb = fig.colorbar(cf, ax=ax, shrink=0.85, pad=0.02)
            cb.set_label(unit, color=_TICK, size=7)
            cb.ax.tick_params(colors=_TICK, labelsize=6)

            # Ligne de chaque sondage + label
            for sond, sx in sond_x.items():
                ax.axvline(sx, color="#ffffff60", lw=1.0, ls="--")
                ax.text(sx, -0.3, sond, ha="center", color="#38bdf8",
                        fontsize=7, fontweight="bold")

            # Points de mesure réels
            sc = ax.scatter(xs, ds, c=vals, cmap=cmap,
                            s=35, edgecolors="white", linewidths=0.6,
                            zorder=5, vmin=min(vals), vmax=max(vals))

            # Annotations valeurs sur les points
            for xi_pt, di_pt, vi_pt in zip(xs, ds, vals):
                ax.annotate(f"{vi_pt:.1f}", (xi_pt, di_pt),
                            textcoords="offset points", xytext=(5, 3),
                            color="white", fontsize=5, alpha=0.8)

            ax.set_xlabel("Distance horizontale (m)", color=_TICK, fontsize=8)
            ax.set_ylabel("Profondeur (m)", color=_TICK, fontsize=8)
            ax.set_ylim(max_depth + 0.5, -0.5)
            ax.set_xlim(-1, x_max + 1)
            ax.grid(True, color=_GRID, lw=0.3, alpha=0.4)

        except Exception as e:
            ax.text(0.5, 0.5, f"Interpolation\nnon disponible\n({e})",
                    ha="center", va="center", color="#888", fontsize=8,
                    transform=ax.transAxes)

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter coupes 2D", "coupes_2d_geotechniques.png",
            "Images PNG (*.png);;Tous (*.*)"
        )
        if path:
            self.canvas.figure.savefig(
                path, dpi=150, bbox_inches="tight", facecolor=_BG
            )
