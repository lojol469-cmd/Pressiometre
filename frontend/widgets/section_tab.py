"""
Onglet Coupes géotechniques 2D — PressiomètreIA v2
11 coupes :
  Coupe 1  — schématique lithologique (colonnes + corrélations)
  Coupe 2  — interpolée Em (MPa)
  Coupe 3  — interpolée Pl (MPa)
  Coupe 4  — interpolée Pf (MPa)
  Coupe 5  — ratio Em/Pl (rigidité relative)
  Coupe 6  — classification NC/SC
  Coupe 7  — qualité des essais (A/B/C/D)
  Coupe 8  — isolignes Em (contours + triangulation Delaunay)
  Coupe 9  — isolignes Pl (contours + triangulation Delaunay)
  Coupe 10 — isolignes Pf (contours + triangulation Delaunay)
  Coupe 11 — triangulation 3 paramètres superposée (Em/Pf/Pl)
Chaque coupe est exportable individuellement en PDF.
"""
from __future__ import annotations
from typing import Optional, Dict, List
import io
import datetime

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.tri as mtri
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from scipy.interpolate import griddata

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QComboBox, QFileDialog, QMessageBox, QScrollArea,
)
from PyQt6.QtCore import Qt

from api.models import SectionData


# ─── Constantes visuelles ────────────────────────────────────────────────────
BG      = "#12151e"
AX_BG   = "#1a1d2b"
WHITE   = "white"
CYAN    = "#00b4d8"
GOLD    = "#f4a426"
ORANGE  = "#e76f51"

CMAPS = {
    "Em":    "RdYlGn",
    "Pl":    "plasma",
    "Pf":    "viridis",
    "ratio": "coolwarm",
}

QUALITE_COLORS = {"A": "#2ec4b6", "B": "#f4a426", "C": "#e76f51", "D": "#e63946", "?": "#888"}
NC_COLORS      = {"NC": "#e76f51", "SC": "#2ec4b6", "remanie": "#f4a426"}

PLOT_TITLES = {
    0:  "① Coupe lithologique schématique",
    1:  "② Coupe 2D interpolée — Module Em (MPa)",
    2:  "③ Coupe 2D interpolée — Pression Limite Pl (MPa)",
    3:  "④ Coupe 2D interpolée — Pression de Fluage Pf (MPa)",
    4:  "⑤ Coupe 2D — Rapport Em/Pl (Rigidité relative)",
    5:  "⑥ Coupe 2D — Classification NC / SC",
    6:  "⑦ Coupe 2D — Qualité des essais (A=excellent → D=médiocre)",
    7:  "⑧ Isolignes Em (MPa) — Triangulation Delaunay",
    8:  "⑨ Isolignes Pl (MPa) — Triangulation Delaunay",
    9:  "⑩ Isolignes Pf (MPa) — Triangulation Delaunay",
    10: "⑪ Triangulation multi-paramètres (Em / Pf / Pl)",
}

PDF_FILENAMES = {
    0:  "coupe_01_lithologique",
    1:  "coupe_02_Em_interpole",
    2:  "coupe_03_Pl_interpole",
    3:  "coupe_04_Pf_interpole",
    4:  "coupe_05_ratio_EmPl",
    5:  "coupe_06_NC_SC",
    6:  "coupe_07_qualite",
    7:  "coupe_08_isolignes_Em",
    8:  "coupe_09_isolignes_Pl",
    9:  "coupe_10_isolignes_Pf",
    10: "coupe_11_triangulation",
}


def _style_ax(ax):
    ax.set_facecolor(AX_BG)
    ax.tick_params(colors=WHITE, labelsize=7)
    ax.xaxis.label.set_color(WHITE)
    ax.yaxis.label.set_color(WHITE)
    ax.title.set_color(WHITE)
    for spine in ax.spines.values():
        spine.set_edgecolor("#444")


def _common_labels(ax):
    ax.set_xlabel("Distance horizontale (m)", color=WHITE, fontsize=8)
    ax.set_ylabel("Profondeur (m)", color=WHITE, fontsize=8)


def _boreholes_vlines(ax, boreholes):
    y_top = ax.get_ylim()[1]
    for bh in boreholes:
        ax.axvline(bh["x_m"], color="#ffffff44", lw=0.8, ls="--")
        ax.text(bh["x_m"], y_top, bh["name"], ha="center", color=CYAN,
                fontsize=7, fontweight="bold", clip_on=False)


class MplCanvas(FigureCanvas):
    def __init__(self, w=13, h=6):
        self.fig = Figure(figsize=(w, h), facecolor=BG, tight_layout=True)
        super().__init__(self.fig)
        self.setStyleSheet(f"background:{BG};")


# ─── Fonctions de dessin ─────────────────────────────────────────────────────

def _draw_lithologique(fig, section: SectionData):
    from collections import defaultdict
    ax = fig.add_subplot(111)
    _style_ax(ax)

    by_sond = defaultdict(list)
    for pt in section.points:
        by_sond[pt.sondage].append(pt)

    for sond, pts in by_sond.items():
        pts_sorted = sorted(pts, key=lambda x: x.depth_m)
        for i, pt in enumerate(pts_sorted):
            thick = pts_sorted[i+1].depth_m - pt.depth_m if i+1 < len(pts_sorted) else 2.0
            rect = mpatches.FancyBboxPatch(
                (pt.x_m - 0.8, -pt.depth_m), 1.6, -thick,
                boxstyle="square,pad=0",
                facecolor=pt.sol_color or "#888",
                edgecolor="#555", alpha=0.85
            )
            ax.add_patch(rect)
            if thick > 1.0:
                ax.text(pt.x_m, -(pt.depth_m + thick / 2),
                        (pt.sol_type or "?")[:14],
                        ha="center", va="center", color=WHITE, fontsize=5)
        if pts_sorted:
            ax.text(pts_sorted[0].x_m, 0.5, sond,
                    ha="center", color=CYAN, fontsize=8, fontweight="bold")

    sond_names = sorted(by_sond.keys())
    for i in range(len(sond_names) - 1):
        s1 = sorted(by_sond[sond_names[i]],   key=lambda x: x.depth_m)
        s2 = sorted(by_sond[sond_names[i+1]], key=lambda x: x.depth_m)
        for p1 in s1:
            for p2 in s2:
                if p1.sol_type == p2.sol_type:
                    ax.plot([p1.x_m + 0.8, p2.x_m - 0.8],
                            [-p1.depth_m, -p2.depth_m],
                            color="#ffffff33", lw=0.8, ls="--")

    all_d = [pt.depth_m for pt in section.points]
    all_x = [pt.x_m for pt in section.points]
    ax.set_ylim(-(max(all_d) + 3), 1.5)
    ax.set_xlim(min(all_x) - 3, max(all_x) + 3)
    _common_labels(ax)
    ax.set_title(PLOT_TITLES[0], color=WHITE, fontsize=10)

    sol_items = {pt.sol_type: pt.sol_color for pt in section.points}
    patches = [mpatches.Patch(color=c or "#888", label=(t or "?")[:25])
               for t, c in list(sol_items.items())[:10]]
    ax.legend(handles=patches, fontsize=6, facecolor="#1a1a2a",
              labelcolor=WHITE, loc="lower right", ncol=2)


def _draw_interpole(fig, section: SectionData, param: str, cmap_name: str, title: str):
    ax = fig.add_subplot(111)
    _style_ax(ax)

    xs = np.array([pt.x_m for pt in section.points])
    ys = np.array([-pt.depth_m for pt in section.points])
    if param == "Em":
        vals = np.array([pt.Em_MPa or np.nan for pt in section.points])
    elif param == "Pl":
        vals = np.array([pt.Pl_MPa or np.nan for pt in section.points])
    elif param == "Pf":
        vals = np.array([pt.Pf_MPa or np.nan for pt in section.points])
    else:
        vals = np.array([
            (pt.Em_MPa / pt.Pl_MPa) if (pt.Em_MPa and pt.Pl_MPa and pt.Pl_MPa > 0) else np.nan
            for pt in section.points
        ])

    mask = ~np.isnan(vals)
    if mask.sum() < 3:
        ax.text(0.5, 0.5, "Données insuffisantes", ha="center", va="center",
                color="#aaa", fontsize=11, transform=ax.transAxes)
        ax.set_title(title, color=WHITE, fontsize=10)
        return

    xs_v, ys_v, vals_v = xs[mask], ys[mask], vals[mask]
    xi = np.linspace(xs_v.min(), xs_v.max(), 200)
    yi = np.linspace(ys_v.min(), ys_v.max(), 200)
    Xi, Yi = np.meshgrid(xi, yi)
    Zi = griddata((xs_v, ys_v), vals_v, (Xi, Yi), method="linear")

    cf = ax.contourf(Xi, Yi, Zi, levels=20, cmap=cmap_name, alpha=0.85)
    cbar = fig.colorbar(cf, ax=ax, fraction=0.03, pad=0.01)
    cbar.ax.tick_params(colors=WHITE, labelsize=7)
    lbl = {"Em": "Em (MPa)", "Pl": "Pl (MPa)", "Pf": "Pf (MPa)", "ratio": "Em/Pl"}[param]
    cbar.set_label(lbl, color=WHITE, fontsize=8)

    ax.scatter(xs_v, ys_v, c=vals_v, cmap=cmap_name,
               edgecolors="white", s=18, zorder=5, linewidths=0.5)
    for x_, y_, v_ in zip(xs_v, ys_v, vals_v):
        ax.text(x_, y_ + 0.15, f"{v_:.1f}", ha="center", color=WHITE, fontsize=5, zorder=6)

    ax.set_xlim(xs.min() - 1, xs.max() + 1)
    ax.set_ylim(ys.min() - 1, 0.5)
    _boreholes_vlines(ax, section.boreholes)
    _common_labels(ax)
    ax.set_title(title, color=WHITE, fontsize=10)


def _draw_nc_sc(fig, section: SectionData):
    ax = fig.add_subplot(111)
    _style_ax(ax)

    for pt in section.points:
        nc = "?"
        if pt.Em_MPa and pt.Pl_MPa and pt.Pl_MPa > 0:
            r = pt.Em_MPa / pt.Pl_MPa
            nc = "NC" if r < 5 else ("SC" if r > 12 else "remanie")
        col = NC_COLORS.get(nc, "#888")
        ax.scatter(pt.x_m, -pt.depth_m, color=col, s=60, zorder=5,
                   edgecolors="white", lw=0.5)
        ax.text(pt.x_m + 0.2, -pt.depth_m, nc, color=col, fontsize=6)

    xs = [pt.x_m for pt in section.points]
    ys = [-pt.depth_m for pt in section.points]
    ax.set_xlim(min(xs) - 2, max(xs) + 2)
    ax.set_ylim(min(ys) - 1, 1)
    _boreholes_vlines(ax, section.boreholes)
    _common_labels(ax)
    ax.set_title(PLOT_TITLES[5], color=WHITE, fontsize=10)
    patches = [mpatches.Patch(color=v, label=k) for k, v in NC_COLORS.items()]
    ax.legend(handles=patches, fontsize=7, facecolor="#1a1a2a", labelcolor=WHITE)


def _draw_qualite(fig, section: SectionData):
    ax = fig.add_subplot(111)
    _style_ax(ax)

    for pt in section.points:
        q = pt.qualite or "?"
        col = QUALITE_COLORS.get(q, "#888")
        ax.scatter(pt.x_m, -pt.depth_m, color=col, s=80, zorder=5,
                   edgecolors="white", lw=0.5, marker="s")
        ax.text(pt.x_m + 0.15, -pt.depth_m, q, color=col, fontsize=7, fontweight="bold")

    xs = [pt.x_m for pt in section.points]
    ys = [-pt.depth_m for pt in section.points]
    ax.set_xlim(min(xs) - 2, max(xs) + 2)
    ax.set_ylim(min(ys) - 1, 1)
    _boreholes_vlines(ax, section.boreholes)
    _common_labels(ax)
    ax.set_title(PLOT_TITLES[6], color=WHITE, fontsize=10)
    patches = [mpatches.Patch(color=v, label=f"Qualité {k}")
               for k, v in QUALITE_COLORS.items() if k != "?"]
    ax.legend(handles=patches, fontsize=7, facecolor="#1a1a2a", labelcolor=WHITE)


def _draw_isolignes(fig, section: SectionData, param: str, title: str, cmap_name: str):
    ax = fig.add_subplot(111)
    _style_ax(ax)

    xs = np.array([pt.x_m for pt in section.points], dtype=float)
    ys = np.array([-pt.depth_m for pt in section.points], dtype=float)
    if param == "Em":
        vals = np.array([pt.Em_MPa or np.nan for pt in section.points])
    elif param == "Pl":
        vals = np.array([pt.Pl_MPa or np.nan for pt in section.points])
    else:
        vals = np.array([pt.Pf_MPa or np.nan for pt in section.points])

    mask = ~np.isnan(vals)
    if mask.sum() < 3:
        ax.text(0.5, 0.5, "Données insuffisantes", ha="center", va="center",
                color="#aaa", fontsize=11, transform=ax.transAxes)
        ax.set_title(title, color=WHITE, fontsize=10)
        return

    xs_v, ys_v, vals_v = xs[mask], ys[mask], vals[mask]
    triang = mtri.Triangulation(xs_v, ys_v)
    cf = ax.tricontourf(triang, vals_v, levels=15, cmap=cmap_name, alpha=0.80)
    ax.tricontour(triang, vals_v, levels=8, colors="white", linewidths=0.5, alpha=0.6)
    ax.triplot(triang, color="#ffffff22", lw=0.5, zorder=2)

    cbar = fig.colorbar(cf, ax=ax, fraction=0.03, pad=0.01)
    cbar.ax.tick_params(colors=WHITE, labelsize=7)
    cbar.set_label(f"{param} (MPa)", color=WHITE, fontsize=8)

    ax.scatter(xs_v, ys_v, c=vals_v, cmap=cmap_name,
               edgecolors="white", s=20, zorder=5, lw=0.5)
    for x_, y_, v_ in zip(xs_v, ys_v, vals_v):
        ax.text(x_, y_ + 0.15, f"{v_:.1f}", ha="center", color=WHITE, fontsize=5, zorder=6)

    for bh in section.boreholes:
        ax.axvline(bh["x_m"], color="#ffffff44", lw=0.8, ls="--")
        ax.text(bh["x_m"], 0.3, bh["name"], ha="center", color=CYAN,
                fontsize=7, fontweight="bold")

    ax.set_xlim(xs_v.min() - 1, xs_v.max() + 1)
    ax.set_ylim(ys_v.min() - 1, 0.5)
    _common_labels(ax)
    ax.set_title(title, color=WHITE, fontsize=10)


def _draw_triangulation_multi(fig, section: SectionData):
    ax = fig.add_subplot(111)
    _style_ax(ax)

    xs = np.array([pt.x_m for pt in section.points], dtype=float)
    ys = np.array([-pt.depth_m for pt in section.points], dtype=float)

    configs = [
        ("Em",  [pt.Em_MPa or np.nan for pt in section.points], "#e63946", "Em (MPa)"),
        ("Pf",  [pt.Pf_MPa or np.nan for pt in section.points], "#2ec4b6", "Pf (MPa)"),
        ("Pl",  [pt.Pl_MPa or np.nan for pt in section.points], "#f4a426", "Pl (MPa)"),
    ]
    handles = []
    for param, raw_vals, color, lbl in configs:
        vals = np.array(raw_vals)
        mask = ~np.isnan(vals)
        if mask.sum() < 3:
            continue
        xs_v, ys_v, vals_v = xs[mask], ys[mask], vals[mask]
        try:
            triang = mtri.Triangulation(xs_v, ys_v)
            ax.triplot(triang, color=color, lw=0.8, alpha=0.7, zorder=3)
            ax.tricontour(triang, vals_v, levels=5, colors=[color], linewidths=1.0, alpha=0.5)
        except Exception:
            pass
        ax.scatter(xs_v, ys_v, color=color, s=25, zorder=6, edgecolors="white", lw=0.4)
        handles.append(mpatches.Patch(color=color, label=lbl))

    for bh in section.boreholes:
        ax.axvline(bh["x_m"], color="#ffffff44", lw=0.8, ls="--")
        ax.text(bh["x_m"], 0.3, bh["name"], ha="center", color=CYAN,
                fontsize=7, fontweight="bold")

    all_d = [pt.depth_m for pt in section.points]
    ax.set_xlim(xs.min() - 1, xs.max() + 1)
    ax.set_ylim(-(max(all_d) + 2), 0.5)
    _common_labels(ax)
    ax.set_title(PLOT_TITLES[10], color=WHITE, fontsize=10)
    if handles:
        ax.legend(handles=handles, fontsize=7, facecolor="#1a1a2a", labelcolor=WHITE)


# ─── Table de dispatch ────────────────────────────────────────────────────────
def _get_draw_fn(idx: int):
    return {
        0:  lambda fig, s: _draw_lithologique(fig, s),
        1:  lambda fig, s: _draw_interpole(fig, s, "Em",    CMAPS["Em"],    PLOT_TITLES[1]),
        2:  lambda fig, s: _draw_interpole(fig, s, "Pl",    CMAPS["Pl"],    PLOT_TITLES[2]),
        3:  lambda fig, s: _draw_interpole(fig, s, "Pf",    CMAPS["Pf"],    PLOT_TITLES[3]),
        4:  lambda fig, s: _draw_interpole(fig, s, "ratio", CMAPS["ratio"], PLOT_TITLES[4]),
        5:  lambda fig, s: _draw_nc_sc(fig, s),
        6:  lambda fig, s: _draw_qualite(fig, s),
        7:  lambda fig, s: _draw_isolignes(fig, s, "Em", PLOT_TITLES[7], CMAPS["Em"]),
        8:  lambda fig, s: _draw_isolignes(fig, s, "Pl", PLOT_TITLES[8], CMAPS["Pl"]),
        9:  lambda fig, s: _draw_isolignes(fig, s, "Pf", PLOT_TITLES[9], CMAPS["Pf"]),
        10: lambda fig, s: _draw_triangulation_multi(fig, s),
    }[idx]


def _render_to_pdf_bytes(section: SectionData, idx: int) -> bytes:
    import matplotlib.pyplot as _plt
    fig = _plt.figure(figsize=(14, 7), facecolor=BG)
    _get_draw_fn(idx)(fig, section)
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", facecolor=BG, bbox_inches="tight", dpi=150)
    _plt.close(fig)
    buf.seek(0)
    return buf.read()


# ─── Widget principal ─────────────────────────────────────────────────────────
class SectionTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._section: Optional[SectionData] = None
        self._current_idx: int = 0
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Barre du haut ──
        top = QHBoxLayout()
        lbl = QLabel("Coupes géotechniques 2D")
        lbl.setStyleSheet(f"font-weight:bold; color:{CYAN}; font-size:13px;")
        top.addWidget(lbl)
        top.addStretch()

        top.addWidget(QLabel("Coupe :"))
        self.cmb_coupe = QComboBox()
        self.cmb_coupe.setMinimumWidth(340)
        for i, t in PLOT_TITLES.items():
            self.cmb_coupe.addItem(t, i)
        self.cmb_coupe.currentIndexChanged.connect(self._on_coupe_changed)
        top.addWidget(self.cmb_coupe)

        self.btn_export = QPushButton("⬇ Exporter PDF")
        self.btn_export.setStyleSheet(
            f"background:{GOLD}; color:#12151e; font-weight:bold;"
            " padding:4px 12px; border-radius:4px;")
        self.btn_export.clicked.connect(self._export_pdf)
        top.addWidget(self.btn_export)

        self.btn_export_all = QPushButton("⬇ Toutes (11 PDF)")
        self.btn_export_all.setStyleSheet(
            f"background:{ORANGE}; color:white; font-weight:bold;"
            " padding:4px 12px; border-radius:4px;")
        self.btn_export_all.clicked.connect(self._export_all_pdf)
        top.addWidget(self.btn_export_all)

        layout.addLayout(top)

        # ── Canvas principal ──
        self.canvas = MplCanvas(13, 6)
        layout.addWidget(self.canvas, stretch=8)

        # ── Tableau ──
        grp = QGroupBox("Points de coupe")
        grp.setStyleSheet(f"QGroupBox{{color:{CYAN}; font-weight:bold;}}")
        gtab = QVBoxLayout(grp)
        self.tbl = QTableWidget()
        self.tbl.setMaximumHeight(160)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.setStyleSheet(
            "QTableWidget{background:#1a1d2b; color:white; gridline-color:#333;}")
        gtab.addWidget(self.tbl)
        layout.addWidget(grp, stretch=2)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_coupe_changed(self, _idx: int):
        self._current_idx = self.cmb_coupe.currentData()
        self._draw(self._section)

    def refresh(self, section: Optional[SectionData]):
        self._section = section
        self._draw(section)
        self._fill_table(section)

    def _draw(self, section: Optional[SectionData]):
        self.canvas.fig.clear()
        if not section or not section.points:
            ax = self.canvas.fig.add_subplot(111)
            _style_ax(ax)
            ax.text(0.5, 0.5,
                    "Aucune coupe disponible.\nVérifiez que plusieurs sondages sont chargés.",
                    ha="center", va="center", color="#aaa", fontsize=11,
                    transform=ax.transAxes)
            self.canvas.draw()
            return

        _get_draw_fn(self._current_idx)(self.canvas.fig, section)
        try:
            self.canvas.fig.tight_layout()
        except Exception:
            pass
        self.canvas.draw()

    # ── Export PDF ────────────────────────────────────────────────────────────

    def _export_pdf(self):
        if not self._section or not self._section.points:
            QMessageBox.warning(self, "Export PDF", "Aucune coupe à exporter.")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{PDF_FILENAMES[self._current_idx]}_{ts}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer la coupe en PDF", default_name, "PDF (*.pdf)")
        if not path:
            return
        try:
            data = _render_to_pdf_bytes(self._section, self._current_idx)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Export PDF", f"Coupe exportée :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur export PDF", str(e))

    def _export_all_pdf(self):
        if not self._section or not self._section.points:
            QMessageBox.warning(self, "Export PDF", "Aucune coupe à exporter.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Dossier de destination")
        if not folder:
            return
        import os
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        errors = []
        for idx in range(11):
            try:
                data = _render_to_pdf_bytes(self._section, idx)
                fname = os.path.join(folder, f"{PDF_FILENAMES[idx]}_{ts}.pdf")
                with open(fname, "wb") as f:
                    f.write(data)
            except Exception as e:
                errors.append(f"Coupe {idx+1}: {e}")
        if errors:
            QMessageBox.warning(self, "Export partiel",
                                f"{11 - len(errors)}/11 coupes exportées.\nErreurs :\n"
                                + "\n".join(errors))
        else:
            QMessageBox.information(self, "Export complet",
                                    f"11 coupes exportées dans :\n{folder}")

    # ── Tableau ───────────────────────────────────────────────────────────────

    def _fill_table(self, section: Optional[SectionData]):
        self.tbl.clear()
        if not section or not section.points:
            self.tbl.setRowCount(0)
            return
        cols = ["Sondage", "X (m)", "Prof. (m)", "Em (MPa)", "Pf (MPa)",
                "Pl (MPa)", "Sol", "Qualité", "NC/SC"]
        self.tbl.setColumnCount(len(cols))
        self.tbl.setHorizontalHeaderLabels(cols)
        pts = sorted(section.points, key=lambda x: (x.sondage, x.depth_m))
        self.tbl.setRowCount(len(pts))
        for row, pt in enumerate(pts):
            nc = "?"
            if pt.Em_MPa and pt.Pl_MPa and pt.Pl_MPa > 0:
                r = pt.Em_MPa / pt.Pl_MPa
                nc = "NC" if r < 5 else ("SC" if r > 12 else "rem.")
            vals = [
                pt.sondage or "?",
                f"{pt.x_m:.1f}",
                f"{pt.depth_m:.1f}",
                f"{pt.Em_MPa:.1f}" if pt.Em_MPa else "—",
                f"{pt.Pf_MPa:.3f}" if pt.Pf_MPa else "—",
                f"{pt.Pl_MPa:.3f}" if pt.Pl_MPa else "—",
                (pt.sol_type or "?")[:20],
                pt.qualite or "?",
                nc,
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tbl.setItem(row, col, item)
