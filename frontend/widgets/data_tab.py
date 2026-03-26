"""Onglet Données brutes — QTableWidget affichant les mesures brutes par feuille."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
    QTableWidget, QTableWidgetItem, QLabel, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui  import QColor

from api.models import ParsedFile


class DataTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parsed: Optional[ParsedFile] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Sélecteur de feuille
        top = QHBoxLayout()
        top.addWidget(QLabel("Feuille :"))
        self.cmb_sheet = QComboBox()
        self.cmb_sheet.currentTextChanged.connect(self._show_sheet)
        top.addWidget(self.cmb_sheet)
        top.addStretch()

        self.lbl_meta = QLabel("—")
        self.lbl_meta.setStyleSheet("color:#aaa; font-size:11px;")
        top.addWidget(self.lbl_meta)
        layout.addLayout(top)

        # Métadonnées essai
        self.tbl_meta = QTableWidget()
        self.tbl_meta.setMaximumHeight(130)
        self.tbl_meta.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tbl_meta)

        # Données brutes
        lbl = QLabel("Données brutes (DONNEES BRUTES):")
        lbl.setStyleSheet("font-weight:bold; color:#00b4d8;")
        layout.addWidget(lbl)

        self.tbl_data = QTableWidget()
        self.tbl_data.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tbl_data)

    def load_parsed(self, parsed: ParsedFile):
        self._parsed = parsed
        self.cmb_sheet.clear()
        for sheet_name in parsed.essais:
            self.cmb_sheet.addItem(sheet_name)

    def _show_sheet(self, sheet_name: str):
        if not self._parsed or sheet_name not in self._parsed.essais:
            return
        essai = self._parsed.essais[sheet_name]
        meta  = essai.meta

        # Tableau méta
        meta_pairs = [
            ("Projet",         meta.projet or "—"),
            ("Localisation",   meta.localisation or "—"),
            ("Sondage",        meta.ref_sondage or "—"),
            ("Profondeur",     f"{meta.profondeur_m} m" if meta.profondeur_m else "—"),
            ("Technique",      meta.technique or "—"),
            ("P. diff. (bar)", f"{meta.pression_diff_bar:.2f}"),
            ("Étalonnage",     meta.ref_etalonnage or "—"),
            ("Calibrage",      meta.ref_calibrage or "—"),
        ]
        self.tbl_meta.setRowCount(1)
        self.tbl_meta.setColumnCount(len(meta_pairs))
        self.tbl_meta.setHorizontalHeaderLabels([k for k, _ in meta_pairs])
        for col, (_, val) in enumerate(meta_pairs):
            item = QTableWidgetItem(str(val))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tbl_meta.setItem(0, col, item)

        # Tableau données brutes
        mesures = essai.mesures
        if not mesures:
            self.tbl_data.clear()
            self.tbl_data.setRowCount(0)
            self.tbl_data.setColumnCount(0)
            return

        cols = ["Palier", "V30 (cm³)", "P60 (MPa)", "V60 (cm³)"]
        self.tbl_data.setColumnCount(len(cols))
        self.tbl_data.setHorizontalHeaderLabels(cols)
        self.tbl_data.setRowCount(len(mesures))

        for row, m in enumerate(mesures):
            vals = [
                str(m.palier),
                f"{m.V30_cm3:.1f}" if m.V30_cm3 is not None else "—",
                f"{m.P60_MPa:.4f}" if m.P60_MPa is not None else "—",
                f"{m.V60_cm3:.1f}" if m.V60_cm3 is not None else "—",
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tbl_data.setItem(row, col, item)

        # Mettre en surbrillance les valeurs sentinelles éventuelles
        self.lbl_meta.setText(
            f"Type: {'🔧 Calibrage' if essai.is_calibrage else '📡 Étalonnage' if essai.is_etalonnage else '📊 Essai'}"
            f"  |  {len(mesures)} paliers"
        )
