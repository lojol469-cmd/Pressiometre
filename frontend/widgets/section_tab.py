"""
Onglet Coupe géologique schématique 2D.
Affiche les colonnes de sondage et les lignes de corrélation entre couches.
"""
from __future__ import annotations
from typing import Optional

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
)
from PyQt6.QtCore import Qt

from api.models import SectionData


class SectionTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._section: Optional[SectionData] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top = QHBoxLayout()
        lbl = QLabel("Coupe géologique schématique (entre sondages)")
        lbl.setStyleSheet("font-weight:bold; color:#00b4d8; font-size:13px;")
        top.addWidget(lbl)
        top.addStretch()
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Graphique coupe
        fig = Figure(facecolor="#12151e")
        self.canvas = FigureCanvas(fig)
        self.canvas.setStyleSheet("background:#12151e;")
        splitter.addWidget(self.canvas)

        # Tableau des points de coupe
        grp = QGroupBox("Points de coupe (interpolés)")
        grp.setStyleSheet("QGroupBox{color:#00b4d8; font-weight:bold;}")
        gtab = QVBoxLayout(grp)
        self.tbl = QTableWidget()
        self.tbl.setMaximumHeight(180)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        gtab.addWidget(self.tbl)
        splitter.addWidget(grp)

        splitter.setSizes([500, 180])
        layout.addWidget(splitter)

    def refresh(self, section: Optional[SectionData]):
        self._section = section
        self._draw(section)
        self._fill_table(section)

    def _draw(self, section: Optional[SectionData]):
        self.canvas.figure.clear()
        ax = self.canvas.figure.add_subplot(111)
        ax.set_facecolor("#12151e")
        ax.tick_params(colors="white", labelsize=7)
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")

        if not section or not section.points:
            ax.text(0.5, 0.5, "Aucune coupe disponible.\nVérifiez que plusieurs sondages sont chargés.",
                    ha="center", va="center", color="#aaa", fontsize=11, transform=ax.transAxes)
            self.canvas.draw()
            return

        # Regrouper par sondage
        from collections import defaultdict
        by_sond = defaultdict(list)
        for pt in section.points:
            by_sond[pt.sondage].append(pt)

        # Dessiner colonnes sondage
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
                    ax.text(pt.x_m, -(pt.depth_m + thick/2),
                            (pt.sol_type or "?")[:14],
                            ha="center", va="center", color="white", fontsize=5)
            # Étiquette sondage en haut
            if pts_sorted:
                ax.text(pts_sorted[0].x_m, 0.3, sond,
                        ha="center", color="#00b4d8", fontsize=8, fontweight="bold")

        # Lignes de corrélation
        sond_names = sorted(by_sond.keys())
        if len(sond_names) >= 2:
            for i in range(len(sond_names)-1):
                s1_pts = sorted(by_sond[sond_names[i]],   key=lambda x: x.depth_m)
                s2_pts = sorted(by_sond[sond_names[i+1]], key=lambda x: x.depth_m)
                for p1 in s1_pts:
                    for p2 in s2_pts:
                        if p1.sol_type == p2.sol_type:
                            ax.plot([p1.x_m+0.8, p2.x_m-0.8], [-p1.depth_m, -p2.depth_m],
                                    color="#ffffff33", lw=0.8, ls="--")

        all_depths = [pt.depth_m for pt in section.points]
        max_d = max(all_depths) + 3 if all_depths else 10
        all_x = [pt.x_m for pt in section.points]
        ax.set_ylim(-max_d, 1)
        ax.set_xlim(min(all_x)-3, max(all_x)+3)
        ax.set_xlabel("Distance horizontale (m)", color="white")
        ax.set_ylabel("Profondeur (m)", color="white")

        # Légende sols
        sol_types = list({pt.sol_type: pt.sol_color for pt in section.points}.items())
        patches = [mpatches.Patch(color=c or "#888", label=(t or "?")[:25])
                   for t, c in sol_types[:10]]
        ax.legend(handles=patches, fontsize=6, facecolor="#1a1a2a",
                  labelcolor="white", loc="lower right", ncol=2)
        ax.set_title("Coupe géologique schématique", color="white", fontsize=11)
        self.canvas.figure.tight_layout()
        self.canvas.draw()

    def _fill_table(self, section: Optional[SectionData]):
        self.tbl.clear()
        if not section or not section.points:
            self.tbl.setRowCount(0)
            return
        cols = ["Sondage", "X (m)", "Prof. (m)", "Em (MPa)", "Pl (MPa)", "Sol", "Qualité"]
        self.tbl.setColumnCount(len(cols))
        self.tbl.setHorizontalHeaderLabels(cols)
        pts = sorted(section.points, key=lambda x: (x.sondage, x.depth_m))
        self.tbl.setRowCount(len(pts))
        for row, pt in enumerate(pts):
            vals = [
                pt.sondage or "?",
                f"{pt.x_m:.1f}",
                f"{pt.depth_m:.1f}",
                f"{pt.Em_MPa:.1f}" if pt.Em_MPa else "—",
                f"{pt.Pl_MPa:.3f}" if pt.Pl_MPa else "—",
                (pt.sol_type or "?")[:20],
                "—",
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tbl.setItem(row, col, item)
