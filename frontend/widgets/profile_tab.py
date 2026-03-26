"""
Onglet Profil géotechnique.
Barres horizontales Em / Pl vs profondeur + colonne lithologique colorée.
"""
from __future__ import annotations
from typing import Optional

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt

from api.models import ProfileData


class ProfileTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile: Optional[ProfileData] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top = QHBoxLayout()
        self.lbl_title = QLabel("Profil géotechnique — Ménard NF P 94-110")
        self.lbl_title.setStyleSheet("font-weight:bold; color:#00b4d8; font-size:13px;")
        top.addWidget(self.lbl_title)
        top.addStretch()
        btn_refresh = QPushButton("↻ Rafraîchir")
        btn_refresh.clicked.connect(lambda: self.refresh(self._profile))
        top.addWidget(btn_refresh)
        layout.addLayout(top)

        fig = Figure(facecolor="#12151e")
        self.canvas = FigureCanvas(fig)
        self.canvas.setStyleSheet("background:#12151e;")
        layout.addWidget(self.canvas)

    def refresh(self, profile: Optional[ProfileData]):
        self._profile = profile
        self.canvas.figure.clear()
        if not profile or not profile.depths:
            ax = self.canvas.figure.add_subplot(111)
            ax.set_facecolor("#12151e")
            ax.text(0.5, 0.5, "Aucun profil disponible.\nAnalysez d'abord les essais.",
                    ha="center", va="center", color="#aaa", fontsize=12,
                    transform=ax.transAxes)
            self.canvas.draw()
            return

        depths   = profile.depths
        em_vals  = [e or 0 for e in profile.Em_MPa]
        pl_vals  = [p or 0 for p in profile.Pl_MPa]
        colors_l = profile.sol_colors or ["#888"] * len(depths)
        sol_types = profile.sol_types or ["?"] * len(depths)

        fig = self.canvas.figure
        gs  = fig.add_gridspec(1, 3, wspace=0.3, left=0.10, right=0.96,
                                top=0.92, bottom=0.07)
        ax_em   = fig.add_subplot(gs[0, 0])
        ax_pl   = fig.add_subplot(gs[0, 1], sharey=ax_em)
        ax_lith = fig.add_subplot(gs[0, 2], sharey=ax_em)

        for ax in (ax_em, ax_pl, ax_lith):
            ax.set_facecolor("#12151e")
            ax.tick_params(colors="white", labelsize=7)
            ax.xaxis.label.set_color("white")
            for spine in ax.spines.values():
                spine.set_edgecolor("#333")
            ax.invert_yaxis()
            ax.grid(True, axis="x", color="#2a2a3a", lw=0.4)

        # Épaisseurs fictives (on dessine des barres centrées sur la profondeur)
        heights = []
        for i in range(len(depths)):
            if i + 1 < len(depths):
                heights.append(depths[i+1] - depths[i])
            else:
                heights.append(2.0)

        # Em
        ax_em.barh(depths, em_vals, height=[h*0.85 for h in heights],
                   color="#06d6a0", alpha=0.85, align="edge")
        ax_em.set_xlabel("Em (MPa)", color="white", fontsize=8)
        ax_em.set_ylabel("Profondeur (m)", color="white", fontsize=8)
        ax_em.set_title("Module Em", color="white", fontsize=9)

        # Pl
        ax_pl.barh(depths, pl_vals, height=[h*0.85 for h in heights],
                   color="#ef476f", alpha=0.85, align="edge")
        ax_pl.set_xlabel("Pl (MPa)", color="white", fontsize=8)
        ax_pl.set_title("Pression limite Pl", color="white", fontsize=9)
        ax_pl.yaxis.set_tick_params(labelleft=False)

        # Lithologie
        for i, (d, h, col, st) in enumerate(zip(depths, heights, colors_l, sol_types)):
            ax_lith.barh(d, 1, height=h*0.9, color=col, alpha=0.85, align="edge")
            ax_lith.text(0.5, d + h*0.45, st[:18], ha="center", va="center",
                         color="white", fontsize=5)
        ax_lith.set_xlim(0, 1)
        ax_lith.set_xticks([])
        ax_lith.set_title("Lithologie", color="white", fontsize=9)
        ax_lith.yaxis.set_tick_params(labelleft=False)

        sond = profile.sondage or ""
        fig.suptitle(f"Profil géotechnique — Sondage {sond}", color="white", fontsize=11)
        self.canvas.draw()
