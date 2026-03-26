"""
Onglet Rapport PDF.
Formulaire de configuration, bouton génération, prévisualisation et téléchargement.
"""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QCheckBox, QPushButton, QLabel, QFileDialog,
    QTextEdit, QProgressBar, QMessageBox, QSplitter,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

from api.models import (
    ParsedFile, CleanedEssai, PressiometricParams, ProfileData
)


class PdfWorker(QThread):
    done  = pyqtSignal(bytes)
    error = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn, self._a, self._kw = fn, args, kwargs

    def run(self):
        try:
            self.done.emit(self._fn(*self._a, **self._kw))
        except Exception as exc:
            self.error.emit(str(exc))


class ReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parsed:     Optional[ParsedFile]          = None
        self._cleaned:    List[CleanedEssai]            = []
        self._params:     List[PressiometricParams]     = []
        self._profile:    Optional[ProfileData]         = None
        self._boreholes:  list                          = []
        self._pdf_bytes:  Optional[bytes]               = None
        self._full_bytes: Optional[bytes]               = None
        self._worker:     Optional[PdfWorker]           = None
        self._ai_tab                                    = None   # set after build
        # Maps keyed by sheet_name for quick lookup
        self._cleaned_map: dict = {}
        self._params_map:  dict = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Panneau gauche : configuration ──
        left = QWidget()
        left.setMaximumWidth(320)
        llay = QVBoxLayout(left)

        grp = QGroupBox("Configuration du rapport")
        grp.setStyleSheet("QGroupBox{color:#00b4d8; font-weight:bold;}")
        form = QFormLayout(grp)

        self.edt_title    = QLineEdit("")
        self.edt_title.setPlaceholderText("Auto-généré si vide")
        self.edt_engineer = QLineEdit("")
        self.edt_location = QLineEdit("Port-Gentil, En face du Stade PERENCO, Gabon")
        self.edt_report_ref = QLineEdit("")
        self.edt_report_ref.setPlaceholderText("Auto-généré si vide")
        self.chk_raw      = QCheckBox("Inclure données corrigées")
        self.chk_raw.setChecked(True)
        self.chk_curves   = QCheckBox("Inclure courbes P-V")
        self.chk_curves.setChecked(True)
        self.chk_web      = QCheckBox("Enrichissement normatif web (NF P 94-110, EC7…)")
        self.chk_web.setChecked(False)

        form.addRow("Titre :",        self.edt_title)
        form.addRow("Ingénieur :",    self.edt_engineer)
        form.addRow("Localisation :", self.edt_location)
        form.addRow("Réf. rapport :", self.edt_report_ref)
        form.addRow("",               self.chk_raw)
        form.addRow("",               self.chk_curves)
        form.addRow("",               self.chk_web)

        llay.addWidget(grp)

        grp_ai = QGroupBox("Synthèse IA (optionnel)")
        grp_ai.setStyleSheet("QGroupBox{color:#ffd166; font-weight:bold;}")
        ai_lay = QVBoxLayout(grp_ai)
        self.edt_ai = QTextEdit()
        self.edt_ai.setPlaceholderText("Collez ici la synthèse KIBALI à inclure dans le PDF…")
        self.edt_ai.setMaximumHeight(120)
        ai_lay.addWidget(self.edt_ai)
        llay.addWidget(grp_ai)

        # ── Rapport standard ──────────────────────────────────────────
        self.btn_generate = QPushButton("⚙ Générer rapport standard")
        self.btn_generate.setMinimumHeight(38)
        self.btn_generate.clicked.connect(self._generate)
        llay.addWidget(self.btn_generate)

        self.btn_save = QPushButton("💾 Enregistrer rapport standard…")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save)
        llay.addWidget(self.btn_save)

        # ── Rapport complet (~30 pages) ───────────────────────────────
        from PyQt6.QtWidgets import QFrame
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#1e3352;")
        llay.addWidget(sep)

        self.btn_full = QPushButton("📋 Rapport COMPLET (~30 pages)")
        self.btn_full.setMinimumHeight(42)
        self.btn_full.setToolTip(
            "Génère un rapport exhaustif : données brutes+corrigées, "
            "anomalies/erreurs, paramètres, statistiques, "
            "conversation KIBALI complète et conclusions."
        )
        self.btn_full.setProperty("role", "warn")
        self.btn_full.clicked.connect(self._generate_full)
        llay.addWidget(self.btn_full)

        self.btn_save_full = QPushButton("💾 Enregistrer rapport complet…")
        self.btn_save_full.setEnabled(False)
        self.btn_save_full.clicked.connect(self._save_full)
        llay.addWidget(self.btn_save_full)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        llay.addWidget(self.progress)

        self.lbl_status = QLabel("Configurez puis cliquez 'Générer'.")
        self.lbl_status.setStyleSheet("color:#888; font-size:10px;")
        llay.addWidget(self.lbl_status)

        llay.addStretch()
        splitter.addWidget(left)

        # ── Panneau droit : prévisualisation ──
        right = QWidget()
        rlay  = QVBoxLayout(right)
        rlay.setContentsMargins(4, 0, 4, 0)
        lbl_prev = QLabel("Prévisualisation du PDF")
        lbl_prev.setStyleSheet("font-weight:bold; color:#00b4d8;")
        rlay.addWidget(lbl_prev)

        if HAS_WEBENGINE:
            self.preview = QWebEngineView()
            self.preview.setStyleSheet("background:#111;")
            rlay.addWidget(self.preview)
        else:
            self.preview = QLabel(
                "⚠ PyQt6.QtWebEngineWidgets non disponible.\n"
                "La prévisualisation est désactivée.\n"
                "Le PDF sera généré et sauvegardable normalement."
            )
            self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview.setStyleSheet("color:#ffd166; font-size:13px;")
            rlay.addWidget(self.preview)

        splitter.addWidget(right)
        splitter.setSizes([300, 900])
        layout.addWidget(splitter)

    # ─── Données ──────────────────────────────────────────────────────────────
    def set_data(self, parsed, cleaned, params, profile, boreholes):
        self._parsed    = parsed
        self._cleaned   = cleaned or []
        self._params    = params  or []
        self._profile   = profile
        self._boreholes = boreholes or []
        # Construire les maps keyed by sheet_name
        self._cleaned_map = {c.sheet_name: c for c in self._cleaned}
        self._params_map  = {p.sheet_name: p for p in self._params}
        self.lbl_status.setText(
            f"✅ {len(self._cleaned)} essais prêts | profil: {'oui' if profile else 'non'}"
        )

    def set_ai_tab(self, ai_tab) -> None:
        """Référence vers l'onglet IA pour récupérer la conversation KIBALI."""
        self._ai_tab = ai_tab

    # ─── Génération ───────────────────────────────────────────────────────────
    def _generate(self):
        if not self._parsed or not self._cleaned:
            QMessageBox.warning(self, "Données manquantes",
                                "Chargez et analysez d'abord des fichiers.")
            return

        from frontend.api_client import ApiClient
        client = ApiClient()

        self.btn_generate.setEnabled(False)
        self.progress.setVisible(True)
        self.lbl_status.setText("Génération PDF en cours…")

        def do_gen():
            return client.generate_report(
                parsed=self._parsed,  # type: ignore[arg-type]
                cleaned_list=self._cleaned,
                params_list=self._params,
                profile=self._profile,
                boreholes=self._boreholes,
                project_title=self.edt_title.text(),
                engineer=self.edt_engineer.text(),
                include_raw=self.chk_raw.isChecked(),
                include_curves=self.chk_curves.isChecked(),
                ai_summary=self.edt_ai.toPlainText(),
                location=self.edt_location.text(),
                report_ref=self.edt_report_ref.text(),
                use_web_norms=self.chk_web.isChecked(),
            )

        w = PdfWorker(do_gen)
        w.done.connect(self._on_done)
        w.error.connect(self._on_error)
        self._worker = w
        w.start()

    def _on_done(self, pdf_bytes: bytes):
        self.progress.setVisible(False)
        self.btn_generate.setEnabled(True)
        self.btn_save.setEnabled(True)
        self._pdf_bytes = pdf_bytes
        self.lbl_status.setText(f"✅ PDF généré ({len(pdf_bytes)//1024} Ko)")

        if HAS_WEBENGINE:
            # Écrire dans un temp file et charger dans WebEngine
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(pdf_bytes)
            tmp.close()
            from PyQt6.QtCore import QUrl
            self.preview.setUrl(QUrl.fromLocalFile(tmp.name))  # type: ignore[attr-defined]

    def _on_error(self, err: str):
        self.progress.setVisible(False)
        self.btn_generate.setEnabled(True)
        self.lbl_status.setText(f"❌ Erreur : {err[:80]}")
        QMessageBox.critical(self, "Erreur génération PDF", err)

    # ─── Sauvegarde rapport standard ──────────────────────────────────────────
    def _save(self):
        if not self._pdf_bytes:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le rapport PDF",
            str(Path.home() / "rapport_pressiometrique.pdf"),
            "PDF (*.pdf)"
        )
        if path:
            Path(path).write_bytes(self._pdf_bytes)
            self.lbl_status.setText(f"✅ Enregistré : {path}")

    # ─── Rapport complet ──────────────────────────────────────────────────────
    def _generate_full(self):
        if not self._cleaned_map or not self._params_map:
            QMessageBox.warning(self, "Données manquantes",
                                "Chargez et analysez d'abord des fichiers.")
            return

        from api.report_full import build_full_report
        from frontend.main_window import MainWindow

        # Récupérer la conversation depuis l'onglet IA
        conversation: list = []
        if self._ai_tab is not None and hasattr(self._ai_tab, "_conversation"):
            conversation = list(self._ai_tab._conversation)

        # Récupérer parsed_files depuis le parent MainWindow
        parsed_files: dict = {}
        main = self.window()
        parsed_files = getattr(main, "parsed_files", {})

        meta = {
            "title":    self.edt_title.text() or None,
            "engineer": self.edt_engineer.text(),
            "location": self.edt_location.text(),
            "ref":      self.edt_report_ref.text() or None,
        }

        self.btn_full.setEnabled(False)
        self.btn_generate.setEnabled(False)
        self.progress.setVisible(True)
        self.lbl_status.setText("Rapport complet en cours de génération…")

        def do_gen():
            return build_full_report(
                parsed_files=parsed_files,
                cleaned_map=self._cleaned_map,
                params_map=self._params_map,
                conversation=conversation,
                meta=meta,
            )

        w = PdfWorker(do_gen)
        w.done.connect(self._on_full_done)
        w.error.connect(self._on_error)
        self._worker = w
        w.start()

    def _on_full_done(self, pdf_bytes: bytes):
        self.progress.setVisible(False)
        self.btn_full.setEnabled(True)
        self.btn_generate.setEnabled(True)
        self.btn_save_full.setEnabled(True)
        self._full_bytes = pdf_bytes
        size_ko = len(pdf_bytes) // 1024
        self.lbl_status.setText(f"✅ Rapport complet généré ({size_ko} Ko)")

        if HAS_WEBENGINE:
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(pdf_bytes)
            tmp.close()
            from PyQt6.QtCore import QUrl
            self.preview.setUrl(QUrl.fromLocalFile(tmp.name))  # type: ignore[attr-defined]

    def _save_full(self):
        if not self._full_bytes:
            return
        import datetime
        default = Path.home() / f"rapport_complet_SETRAF_{datetime.date.today():%Y%m%d}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le rapport complet",
            str(default), "PDF (*.pdf)"
        )
        if path:
            Path(path).write_bytes(self._full_bytes)
            self.lbl_status.setText(f"✅ Rapport complet enregistré : {path}")
