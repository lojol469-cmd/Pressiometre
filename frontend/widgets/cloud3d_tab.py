"""
Onglet Nuage de points 3D — matplotlib Axes3D (fiable PyQt6)
Scatter Em / Pl / Pl* représentés dans l'espace (X, Y=-profondeur, Z=valeur)
La vue pyqtgraph.opengl est abandonnée (bugs OpenGL PyQt6 sur Windows).
"""
from __future__ import annotations
from typing import Optional, cast

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from mpl_toolkits.mplot3d.axes3d import Axes3D as _Axes3D

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QFileDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt

from api.models import PointCloud3D

_LAYER_CFG = {
    "Em_MPa":      ("turbo",    "Em (MPa)",  0, 100),
    "Pl_MPa":      ("RdYlGn_r", "Pl (MPa)",  0, 5),
    "Pl_star_MPa": ("plasma",   "Pl* (MPa)", 0, 4),
}

_BG   = "#0b0f1a"
_PANE = "#111827"
_EDGE = "#1e3352"
_TICK = "#64748b"


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


class Cloud3DTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cloud: Optional[PointCloud3D] = None
        self._build_ui()
        self._draw_placeholder()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(6)

        top = QHBoxLayout()
        lbl = QLabel("Reconstruction 3D — Nuage de points IDW")
        lbl.setStyleSheet("font-weight:bold; color:#38bdf8; font-size:13px;")
        top.addWidget(lbl)
        top.addStretch()

        top.addWidget(QLabel("Couche :"))
        self.cmb = QComboBox()
        self.cmb.addItems(list(_LAYER_CFG.keys()))
        self.cmb.currentTextChanged.connect(self._on_layer_changed)
        top.addWidget(self.cmb)

        btn_reset = QPushButton("Reinitialiser vue")
        btn_reset.setFixedWidth(140)
        btn_reset.clicked.connect(self._reset_view)
        top.addWidget(btn_reset)

        btn_export = QPushButton("Exporter PNG")
        btn_export.setFixedWidth(120)
        btn_export.clicked.connect(self._export_png)
        top.addWidget(btn_export)

        layout.addLayout(top)

        self.canvas = _Canvas3D()
        layout.addWidget(self.canvas, stretch=1)

        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)
        self.mpl_toolbar.setStyleSheet(
            "background:#111827; border:none;"
        )
        layout.addWidget(self.mpl_toolbar)

        self.lbl_info = QLabel(
            "Aucun nuage — lancez Analyser tout pour generer la reconstruction 3D."
        )
        self.lbl_info.setStyleSheet("color:#64748b; font-size:10px; padding:2px 4px;")
        layout.addWidget(self.lbl_info)

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
        cbar.set_label("Valeur normalisee", color=_TICK, size=8)
        cbar.ax.tick_params(colors=_TICK, labelsize=7)
        self.canvas.draw()

    def refresh(self, cloud: Optional[PointCloud3D]):
        self._cloud = cloud
        self._render(self.cmb.currentText())

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

        raw = {
            "Em_MPa":      [p.get("Em") for p in cloud.points],
            "Pl_MPa":      [p.get("Pl") for p in cloud.points],
            "Pl_star_MPa": [p.get("Pl") for p in cloud.points],
        }
        vals = np.array([v if v is not None else np.nan for v in raw[layer]], dtype=float)

        if len(xs) == 0 or np.all(np.isnan(vals)):
            self._draw_placeholder()
            self.lbl_info.setText("Donnees insuffisantes pour afficher le nuage 3D.")
            return

        cmap_name, unit, vmin_def, vmax_def = _LAYER_CFG[layer]
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

        ax.scatter(xs, ys, np.zeros_like(zs),
                   c=vals, cmap=cmap_name, vmin=v_min, vmax=v_max,
                   s=18, alpha=0.30, edgecolors="none")  # type: ignore

        ax.set_xlabel("Easting (m)",  color=_TICK, labelpad=8, fontsize=8)
        ax.set_ylabel("Northing (m)", color=_TICK, labelpad=8, fontsize=8)
        ax.set_zlabel("Prof. (m)",    color=_TICK, labelpad=8, fontsize=8)
        title_lyr = layer.replace("_MPa", "").replace("_star", "*")
        ax.set_title(f"Nuage 3D — {title_lyr}  [{unit}]",
                     color="#38bdf8", pad=10, fontsize=11, fontweight="bold")

        cbar = self.canvas.fig.colorbar(sc, ax=ax, shrink=0.45, pad=0.08, aspect=25)
        cbar.set_label(unit, color=_TICK, size=8)
        cbar.ax.tick_params(colors=_TICK, labelsize=7)

        self.canvas.draw()

        valid = int(np.sum(~np.isnan(vals)))
        self.lbl_info.setText(
            f"Couche : {layer}  |  {valid} points  |  "
            f"Min={v_min:.3f}  Max={v_max:.3f}  Moy={float(np.nanmean(vals)):.3f}  {unit}"
        )

    def _reset_view(self):
        axes = self.canvas.fig.axes
        if axes:
            cast(_Axes3D, axes[0]).view_init(elev=22, azim=225)
            self.canvas.draw()

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter nuage 3D", "nuage_3d.png",
            "Images PNG (*.png);;Tous (*.*)"
        )
        if path:
            self.canvas.fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_BG)
