"""
Onglet Analyse P-V.
Affiche la courbe Pression-Volume, les paramètres Ménard calculés,
les anomalies et les corrections appliquées pour l'essai sélectionné.
"""
from __future__ import annotations
from typing import Dict, Optional

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QComboBox, QLabel, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QGroupBox, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui  import QColor

from api.models import CleanedEssai, PressiometricParams
from frontend.widgets.svg_results import SvgResultsWidget


class MplCanvas(FigureCanvas):
    def __init__(self, width=8, height=5):
        self.fig = Figure(figsize=(width, height), facecolor="#12151e")
        super().__init__(self.fig)
        self.setStyleSheet("background:#12151e;")
        self.fig.set_tight_layout(True)  # type: ignore[attr-defined]


class AnalysisTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cleaned_map: Dict[str, CleanedEssai]        = {}
        self._params_map:  Dict[str, PressiometricParams] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # Sélecteur essai
        top = QHBoxLayout()
        top.addWidget(QLabel("Essai :"))
        self.cmb = QComboBox()
        self.cmb.setMinimumWidth(200)
        self.cmb.currentTextChanged.connect(self.show_essai)
        top.addWidget(self.cmb)
        top.addStretch()
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Graphique ──
        self.canvas = MplCanvas(9, 6)
        splitter.addWidget(self.canvas)

        # ── Panneau droit ──
        right = QWidget()
        right.setMinimumWidth(400)
        right.setMaximumWidth(460)
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(4, 0, 4, 0)

        # Jauges SVG animées
        self.svg_widget = SvgResultsWidget()
        self.svg_widget.setMinimumHeight(300)
        rlay.addWidget(self.svg_widget)

        grp_params = QGroupBox("Paramètres Ménard")
        grp_params.setStyleSheet("QGroupBox{color:#00b4d8;font-weight:bold;}")
        p_lay = QVBoxLayout(grp_params)
        self.tbl_params = QTableWidget(0, 2)
        self.tbl_params.setHorizontalHeaderLabels(["Paramètre", "Valeur"])
        self.tbl_params.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_params.setMaximumHeight(260)
        p_lay.addWidget(self.tbl_params)
        rlay.addWidget(grp_params)

        grp_anom = QGroupBox("Anomalies / Incohérences")
        grp_anom.setStyleSheet("QGroupBox{color:#ef476f;font-weight:bold;}")
        a_lay = QVBoxLayout(grp_anom)
        self.list_anom = QListWidget()
        self.list_anom.setMaximumHeight(180)
        a_lay.addWidget(self.list_anom)
        rlay.addWidget(grp_anom)

        grp_notes = QGroupBox("Notes de calcul")
        grp_notes.setStyleSheet("QGroupBox{color:#ffd166;font-weight:bold;}")
        n_lay = QVBoxLayout(grp_notes)
        self.list_notes = QListWidget()
        n_lay.addWidget(self.list_notes)
        rlay.addWidget(grp_notes)

        splitter.addWidget(right)
        splitter.setSizes([700, 460])
        layout.addWidget(splitter)

    # ─── Rafraîchissement après analyse ──────────────────────────────────────
    def refresh(self, cleaned_map: Dict[str, CleanedEssai],
                params_map: Dict[str, PressiometricParams]):
        self._cleaned_map = cleaned_map
        self._params_map  = params_map
        current = self.cmb.currentText()
        self.cmb.clear()
        for k in sorted(cleaned_map.keys()):
            self.cmb.addItem(k)
        if current in cleaned_map:
            self.cmb.setCurrentText(current)

    def show_essai(self, sheet_name: str):
        if not sheet_name or sheet_name not in self._cleaned_map:
            return
        cleaned = self._cleaned_map[sheet_name]
        params  = self._params_map.get(sheet_name)
        self._draw_curve(cleaned, params)
        self._fill_params(params)
        self._fill_anomalies(cleaned, params)
        self.svg_widget.update_params(params)

    # ─── Courbe P-V ──────────────────────────────────────────────────────────
    def _draw_curve(self, cleaned: CleanedEssai, params: Optional[PressiometricParams]):
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        ax.set_facecolor("#12151e")
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_edgecolor("#444")

        pts_ok   = [p for p in cleaned.points if not p.anomalie]
        pts_anom = [p for p in cleaned.points if p.anomalie]

        if not pts_ok and not pts_anom:
            ax.text(0.5, 0.5,
                    "Aucune donnée disponible\npour cet essai.",
                    ha="center", va="center", color="#94a3b8", fontsize=12,
                    transform=ax.transAxes)
            ax.axis("off")
            self.canvas.draw()
            return

        if pts_ok:
            p_raw  = [pt.P60_raw_MPa for pt in pts_ok]
            v_raw  = [pt.V60_raw_cm3 or 0 for pt in pts_ok]
            p_corr = [pt.P60_corr_MPa for pt in pts_ok]
            vm     = [pt.Vm_corr_cm3  or 0 for pt in pts_ok]
            v60_c  = [pt.V60_smooth_cm3 or pt.V60_corr_cm3 or 0 for pt in pts_ok]

            ax.plot(v_raw, p_raw, "o--", color="#555", lw=1,  ms=3, alpha=0.5, label="Brut V60")
            ax.plot(vm,    p_corr, "o-", color="#00b4d8", lw=2,  ms=5, label="Vm corrigé")
            ax.plot(v60_c, p_corr, "s-", color="#90e0ef", lw=1.2, ms=3, alpha=0.75, label="V60 corrigé")
        else:
            # Tous les points sont des anomalies — afficher un avertissement
            ax.text(0.5, 0.92,
                    "⚠ Aucun point valide — tous marqués anomalie",
                    ha="center", va="top", color="#ffd166", fontsize=9,
                    transform=ax.transAxes)

        if pts_anom:
            va = [pt.Vm_corr_cm3 or 0 for pt in pts_anom]
            pa = [pt.P60_corr_MPa for pt in pts_anom]
            ax.scatter(va, pa, marker="X", s=100, color="#ef476f", zorder=5, label="Anomalie")

        if params:
            if params.Pf_MPa:
                ax.axhline(params.Pf_MPa, ls="--", color="#ffd166", lw=1.2,
                           label=f"Pf = {params.Pf_MPa:.3f} MPa")
            if params.Pl_MPa:
                ax.axhline(params.Pl_MPa, ls=":",  color="#ef476f", lw=1.5,
                           label=f"Pl = {params.Pl_MPa:.3f} MPa")
            if params.P_elastic_min_MPa is not None and params.Pf_MPa:
                ax.axhspan(params.P_elastic_min_MPa, params.Pf_MPa,
                           alpha=0.08, color="#00b4d8")

        ax.set_xlabel("Volume V (cm³)", color="white")
        ax.set_ylabel("Pression P (MPa)", color="white")
        depth = f"{cleaned.depth_m} m" if cleaned.depth_m else "?"
        ax.set_title(f"{cleaned.sheet_name} — prof. {depth}", color="white", fontsize=10)
        ax.legend(fontsize=7, facecolor="#1a1a2a", labelcolor="white")
        ax.grid(True, color="#2a2a3a", lw=0.4)
        self.canvas.draw()

    # ─── Tableau paramètres ───────────────────────────────────────────────────
    def _fill_params(self, params: Optional[PressiometricParams]):
        self.tbl_params.setRowCount(0)
        if not params:
            return
        rows = [
            ("Profondeur (m)",    str(params.depth_m) if params.depth_m else "—"),
            ("Em (MPa)",          f"{params.Em_MPa:.2f}" if params.Em_MPa else "—"),
            ("Pf (MPa)",          f"{params.Pf_MPa:.3f}" if params.Pf_MPa else "—"),
            ("Pl (MPa)",          f"{params.Pl_MPa:.3f}" if params.Pl_MPa else "—"),
            ("Pl* (MPa)",         f"{params.Pl_star_MPa:.3f}" if params.Pl_star_MPa else "—"),
            ("Em/Pl",             f"{params.ratio_Em_Pl:.1f}" if params.ratio_Em_Pl else "—"),
            ("Type de sol",       params.sol_type),
            ("NC / SC",           params.nc_status),
            ("Qualité essai",     params.qualite or "?"),
            ("Cohérence",         "✅ OK" if params.is_coherent else "⚠ Incohérent"),
        ]
        self.tbl_params.setRowCount(len(rows))
        QUAL_COLORS = {"A": "#06d6a0", "B": "#ffd166", "C": "#ef8c3f", "D": "#ef476f"}
        for row, (k, v) in enumerate(rows):
            ki = QTableWidgetItem(k)
            vi = QTableWidgetItem(v)
            ki.setFlags(Qt.ItemFlag.ItemIsEnabled)
            vi.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if k == "Qualité essai":
                vi.setForeground(QColor(QUAL_COLORS.get(params.qualite or "", "#888")))
            self.tbl_params.setItem(row, 0, ki)
            self.tbl_params.setItem(row, 1, vi)

    # ─── Anomalies + notes ────────────────────────────────────────────────────
    def _fill_anomalies(self, cleaned: CleanedEssai, params: Optional[PressiometricParams]):
        self.list_anom.clear()
        self.list_notes.clear()

        for a in (cleaned.anomalies or []):
            icon = "🔴" if a.severity == "error" else "🟡"
            item = QListWidgetItem(f"{icon} Palier {a.palier} — {a.type}: {a.description}")
            clr  = QColor("#ef476f") if a.severity == "error" else QColor("#ffd166")
            item.setForeground(clr)
            self.list_anom.addItem(item)

        if params:
            for chk in (params.coherence_checks or []):
                icon = "✅" if chk.ok else "⚠"
                self.list_anom.addItem(QListWidgetItem(f"{icon} {chk.message}"))
            for note in (params.notes or []):
                self.list_notes.addItem(QListWidgetItem(f"⚬ {note}"))
