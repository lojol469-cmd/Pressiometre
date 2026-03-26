"""Fenêtre principale PyQt6 — PressiomètreIA v2"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QProgressDialog, QLabel, QPushButton,
    QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui  import QAction, QIcon, QFont, QPalette, QColor

from frontend.api_client import ApiClient, ApiError
from api.models import (
    ParsedFile, CleanedEssai, PressiometricParams,
    ProfileData, SectionData, PointCloud3D,
    CleanRequest, CalcRequest, ProfileRequest, SectionRequest, Cloud3DRequest,
)

from frontend.widgets.data_tab       import DataTab
from frontend.widgets.analysis_tab   import AnalysisTab
from frontend.widgets.profile_tab    import ProfileTab
from frontend.widgets.section_tab    import SectionTab
from frontend.widgets.cloud3d_tab    import Cloud3DTab
from frontend.widgets.subsurface_tab import SubsurfaceTab
from frontend.widgets.report_tab     import ReportTab
from frontend.widgets.ai_tab         import AITab
from frontend.icon_factory import get_app_icon, make_logo_banner
from frontend.theme import (
    THEMES, build_qss, get_palette,
    load_saved_theme, save_theme,
    ThemePickerDialog,
)


# ─── LEGAXY COMPAT: DARK_QSS utilisé par sous-widgets (ref externe) ──────────
# Conserve une référence pour compatibilité. Remplacé dynamiquement par le thème.
DARK_QSS = """
/* ── Base ── */
QMainWindow, QWidget {
  background: #0b0f1a;
  color: #e2e8f0;
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 10pt;
}

/* ── Tabs ── */
QTabWidget::pane {
  border: 1px solid #1e3352;
  background: #0b0f1a;
}
QTabBar::tab {
  background: #111827;
  color: #64748b;
  padding: 9px 22px;
  border-radius: 6px 6px 0 0;
  border: 1px solid #1e3352;
  border-bottom: none;
  margin-right: 2px;
  font-weight: 500;
}
QTabBar::tab:selected {
  background: #0b0f1a;
  color: #38bdf8;
  border-color: #2d5a8a;
  border-bottom: 3px solid #38bdf8;
  font-weight: 700;
  padding-bottom: 7px;
}
QTabBar::tab:hover:!selected {
  background: #1a2236;
  color: #cbd5e1;
  border-color: #2d4160;
}

/* ── Toolbar ── */
QToolBar {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #111827, stop:1 #0b0f1a);
  border-bottom: 1px solid #1e3352;
  spacing: 4px;
  padding: 3px 8px;
}
QToolBar QToolButton {
  background: transparent;
  color: #94a3b8;
  border: none;
  border-radius: 4px;
  padding: 5px 10px;
}
QToolBar QToolButton:hover {
  background: #1a2a3f;
  color: #38bdf8;
}

/* ── StatusBar ── */
QStatusBar {
  background: #050810;
  color: #64748b;
  border-top: 1px solid #1e3352;
  font-size: 9pt;
}

/* ── TreeWidget (sidebar) ── */
QTreeWidget {
  background: #080c14;
  alternate-background-color: #0d1220;
  color: #cbd5e1;
  border: none;
  outline: none;
  padding: 4px 2px;
}
QTreeWidget::item {
  padding: 5px 4px;
  border-radius: 4px;
}
QTreeWidget::item:selected {
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #1e3a5f, stop:1 #0f2a45);
  color: #38bdf8;
}
QTreeWidget::item:hover:!selected {
  background: #1a2a3f;
}

/* ── Tables ── */
QTableWidget {
  background: #080c14;
  color: #cbd5e1;
  gridline-color: #1a2236;
  border: 1px solid #1e3352;
  border-radius: 4px;
  selection-background-color: #1e3a5f;
}
QTableWidget::item:selected {
  background: #1e3a5f;
  color: #e2e8f0;
}
QHeaderView::section {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #1a2a3f, stop:1 #111827);
  color: #38bdf8;
  font-weight: 700;
  padding: 6px 8px;
  border: none;
  border-right: 1px solid #1e3352;
  border-bottom: 2px solid #38bdf8;
}

/* ── Buttons (default: bleu) ── */
QPushButton {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #1e3a5f, stop:1 #162d4a);
  color: #7dd3fc;
  border: 1px solid #2d5a8a;
  border-radius: 5px;
  padding: 6px 16px;
  font-weight: 600;
}
QPushButton:hover {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #2d5a8a, stop:1 #1e3a5f);
  color: #e0f2fe;
  border-color: #38bdf8;
}
QPushButton:pressed {
  background: #0f2a45;
  color: #bae6fd;
  border-color: #0ea5e9;
}
QPushButton:disabled {
  background: #111827;
  color: #334155;
  border-color: #1e293b;
}

/* Bouton vert "Analyser" */
QPushButton[role="success"] {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #14532d, stop:1 #0f3d22);
  color: #4ade80;
  border: 1px solid #166534;
}
QPushButton[role="success"]:hover {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #166534, stop:1 #14532d);
  color: #86efac;
  border-color: #4ade80;
}

/* Bouton ambre "Rapport" */
QPushButton[role="warn"] {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #422006, stop:1 #2d1504);
  color: #fbbf24;
  border: 1px solid #78350f;
}
QPushButton[role="warn"]:hover {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #78350f, stop:1 #422006);
  color: #fde68a;
  border-color: #fbbf24;
}

/* ── Input fields ── */
QLineEdit, QTextEdit, QPlainTextEdit {
  background: #080c14;
  color: #e2e8f0;
  border: 1px solid #1e3352;
  border-radius: 5px;
  padding: 5px 8px;
  selection-background-color: #1e3a5f;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
  border-color: #38bdf8;
}

/* ── ComboBox ── */
QComboBox {
  background: #111827;
  color: #cbd5e1;
  border: 1px solid #2d4160;
  border-radius: 5px;
  padding: 4px 8px;
  min-width: 80px;
}
QComboBox:hover { border-color: #38bdf8; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
  background: #111827;
  color: #cbd5e1;
  border: 1px solid #2d4160;
  selection-background-color: #1e3a5f;
  outline: none;
}

/* ── GroupBox ── */
QGroupBox {
  border: 1px solid #1e3352;
  border-radius: 6px;
  margin-top: 14px;
  padding-top: 12px;
  background: #080c14;
}
QGroupBox::title {
  subcontrol-origin: margin;
  subcontrol-position: top left;
  left: 10px;
  padding: 0 6px;
  background: #0b0f1a;
  font-weight: 700;
}

/* ── Labels ── */
QLabel { color: #cbd5e1; }

/* ── Scrollbars ── */
QScrollBar:vertical {
  background: #080c14;
  width: 8px;
  margin: 0;
  border-radius: 4px;
}
QScrollBar::handle:vertical {
  background: #2d4160;
  border-radius: 4px;
  min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #38bdf8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
  background: #080c14;
  height: 8px;
  border-radius: 4px;
}
QScrollBar::handle:horizontal {
  background: #2d4160;
  border-radius: 4px;
}
QScrollBar::handle:horizontal:hover { background: #38bdf8; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── ListWidget ── */
QListWidget {
  background: #080c14;
  color: #cbd5e1;
  border: 1px solid #1e3352;
  border-radius: 4px;
  outline: none;
}
QListWidget::item { padding: 3px 6px; }
QListWidget::item:selected { background: #1e3a5f; color: #e2e8f0; }
QListWidget::item:hover:!selected { background: #1a2236; }

/* ── Splitter ── */
QSplitter::handle { background: #1e3352; width: 2px; height: 2px; }
QSplitter::handle:hover { background: #38bdf8; }

/* ── Progress ── */
QProgressDialog {
  background: #0b0f1a;
  color: #e2e8f0;
  border: 1px solid #38bdf8;
  border-radius: 8px;
}
QProgressBar {
  background: #111827;
  color: #38bdf8;
  border: 1px solid #1e3352;
  border-radius: 4px;
  text-align: center;
  font-size: 9pt;
}
QProgressBar::chunk {
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #0ea5e9, stop:1 #38bdf8);
  border-radius: 4px;
}

/* ── Tooltips ── */
QToolTip {
  background: #1e3a5f;
  color: #e2e8f0;
  border: 1px solid #38bdf8;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 9pt;
}

/* ── MessageBox ── */
QMessageBox { background: #0b0f1a; color: #e2e8f0; }

/* ── Slider ── */
QSlider::groove:horizontal {
  height: 4px; background: #1e3352; border-radius: 2px;
}
QSlider::handle:horizontal {
  width: 14px; height: 14px; background: #38bdf8;
  border-radius: 7px; margin: -5px 0;
}
QSlider::sub-page:horizontal { background: #38bdf8; border-radius: 2px; }

/* ── SpinBox ── */
QSpinBox, QDoubleSpinBox {
  background: #080c14;
  color: #e2e8f0;
  border: 1px solid #1e3352;
  border-radius: 4px;
  padding: 3px 6px;
}

/* ── CheckBox ── */
QCheckBox { color: #cbd5e1; spacing: 6px; }
QCheckBox::indicator {
  width: 14px; height: 14px;
  border: 1px solid #2d4160;
  border-radius: 3px;
  background: #111827;
}
QCheckBox::indicator:checked {
  background: #38bdf8;
  border-color: #38bdf8;
}
"""


# ─── Worker Thread ────────────────────────────────────────────────────────────
class WorkerThread(QThread):
    """Exécute une tâche (fonction) dans un thread séparé pour ne pas bloquer l'UI."""
    done    = pyqtSignal(object)
    error   = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn     = fn
        self._args   = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.done.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ─── Fenêtre principale ───────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PressiomètreIA v2 — NF P 94-110")
        self.setWindowIcon(get_app_icon())
        self.resize(1400, 900)

        self.client: ApiClient = ApiClient()

        # État applicatif
        self.parsed_files:   Dict[str, ParsedFile]          = {}
        self.cleaned_map:    Dict[str, CleanedEssai]        = {}
        self.params_map:     Dict[str, PressiometricParams] = {}
        self.profile:        Optional[ProfileData]          = None
        self.section_data:   Optional[SectionData]          = None
        self.cloud3d_data:   Optional[PointCloud3D]         = None
        self.boreholes:      list                           = []
        self._worker:        Optional[WorkerThread]         = None
        self._current_theme: str                            = load_saved_theme()

        self._build_ui()
        self._build_toolbar()
        self._build_statusbar()
        # Appliquer le thème après la construction UI
        self._apply_theme(self._current_theme, save=False)
        self._start_health_timer()

    # ─── Construction UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Sidebar gauche (arborescence fichiers) ──
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(
            "background:#080c14;"
            "border-right: 2px solid #1e3352;"
        )
        self._sidebar_widget = sidebar
        slay = QVBoxLayout(sidebar)
        slay.setContentsMargins(0, 0, 0, 0)
        slay.setSpacing(0)

        # ── Bannière logo SETRAF GABON (pleine largeur 240 px) ──
        lbl_logo = QLabel()
        lbl_logo.setPixmap(make_logo_banner(240, 72))
        lbl_logo.setFixedSize(240, 72)
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        slay.addWidget(lbl_logo)

        # ── Zone arborescence + boutons (avec marges latérales) ──
        content_w = QWidget()
        clay = QVBoxLayout(content_w)
        clay.setContentsMargins(6, 6, 6, 6)
        clay.setSpacing(6)

        lbl_sidebar = QLabel("  Fichiers / Essais")
        lbl_sidebar.setStyleSheet(
            "color:#38bdf8; font-weight:bold; font-size:12px;"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #1e3a5f22, stop:1 transparent);"
            "border-left: 3px solid #38bdf8;"
            "padding: 4px 8px;"
            "border-radius: 0 4px 4px 0;"
        )
        self._lbl_sidebar = lbl_sidebar
        clay.addWidget(lbl_sidebar)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemClicked.connect(self._on_tree_item_click)
        clay.addWidget(self.tree)

        btn_open = QPushButton("📂  Ouvrir fichier(s)")
        btn_open.clicked.connect(self.open_files)
        clay.addWidget(btn_open)

        btn_analyze_all = QPushButton("⚡  Analyser tout")
        btn_analyze_all.setProperty("role", "success")
        btn_analyze_all.clicked.connect(self.analyze_all)
        clay.addWidget(btn_analyze_all)

        slay.addWidget(content_w)

        splitter.addWidget(sidebar)

        # ── Zone centrale (onglets) ──
        self.tabs = QTabWidget()
        self.tab_data       = DataTab(self)
        self.tab_analysis   = AnalysisTab(self)
        self.tab_profile    = ProfileTab(self)
        self.tab_section    = SectionTab(self)
        self.tab_cloud3d    = Cloud3DTab(self)
        self.tab_subsurface = SubsurfaceTab(self)
        self.tab_report     = ReportTab(self)
        self.tab_ai         = AITab(self)

        # Donner à ReportTab une référence vers AITab pour la conversation
        self.tab_report.set_ai_tab(self.tab_ai)

        self.tabs.addTab(self.tab_data,       "📋 Données")
        self.tabs.addTab(self.tab_analysis,   "📈 Analyse P-V")
        self.tabs.addTab(self.tab_profile,    "🗂 Profil")
        self.tabs.addTab(self.tab_section,    "🪨 Coupe")
        self.tabs.addTab(self.tab_cloud3d,    "🌐 Nuage 3D")
        self.tabs.addTab(self.tab_subsurface, "🗾 Coupes 2D")
        self.tabs.addTab(self.tab_report,     "📄 Rapport PDF")
        self.tabs.addTab(self.tab_ai,         "🤖 IA KIBALI")

        splitter.addWidget(self.tabs)
        splitter.setSizes([240, 1160])
        root_layout.addWidget(splitter)

    def _build_toolbar(self):
        tb = QToolBar("Barre d'outils principale")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        # ── Groupe 1 : Fichiers ───────────────────────────────────────────
        act_open = QAction("📂  Ouvrir", self)
        act_open.setToolTip("Ouvrir fichier(s) Excel pressiométrique(s)")
        act_open.triggered.connect(self.open_files)
        tb.addAction(act_open)

        act_analyze = QAction("⚡  Analyser tout", self)
        act_analyze.setToolTip("Lancer l'analyse complète de tous les essais chargés")
        act_analyze.triggered.connect(self.analyze_all)
        tb.addAction(act_analyze)

        tb.addSeparator()

        # ── Groupe 2 : Thème ─────────────────────────────────────────────
        act_theme = QAction("🎨  Thème", self)
        act_theme.setToolTip("Choisir la palette de couleurs de l'interface")
        act_theme.triggered.connect(self._show_theme_picker)
        tb.addAction(act_theme)

        # ── Séparateur + statut KIBALI (à droite) ────────────────────────
        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().horizontalPolicy(),
            spacer.sizePolicy().verticalPolicy(),
        )
        from PyQt6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self.lbl_kibali = QLabel("  KIBALI: chargement…  ")
        self.lbl_kibali.setStyleSheet("color:#ffd166;")
        tb.addWidget(self.lbl_kibali)

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Prêt — Ouvrez un fichier Excel pressiométrique.")

    # ─── Système de thèmes ────────────────────────────────────────────────────
    def _apply_theme(self, name: str, save: bool = True):
        """Applique un thème à toute l'application et le sauvegarde."""
        self._current_theme = name
        p = get_palette(name)
        qss = build_qss(p)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(qss)
        # Mettre à jour la couleur accent de la sidebar
        if hasattr(self, "_lbl_sidebar"):
            self._lbl_sidebar.setStyleSheet(
                f"color:{p['sidebar_acc']}; font-weight:bold; font-size:12px;"
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"  stop:0 {p['bg4']}44, stop:1 transparent);"
                f"border-left: 3px solid {p['sidebar_acc']};"
                f"padding: 4px 8px; border-radius: 0 4px 4px 0;"
            )
            self._sidebar_widget.setStyleSheet(
                f"background:{p['bg1']}; border-right: 2px solid {p['brd0']};"
            )
        if save:
            save_theme(name)
        self.status.showMessage(f"🎨 Thème appliqué : {name}")

    def _show_theme_picker(self):
        """Ouvre le sélecteur de thème."""
        dlg = ThemePickerDialog(self._current_theme, self)
        dlg.theme_changed.connect(lambda name: self._apply_theme(name))
        dlg.exec()

    # ─── Timer statut KIBALI ─────────────────────────────────────────────────
    def _start_health_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_kibali)
        self._timer.start(3000)

    def _check_kibali(self):
        try:
            info = self.client.kibali_status()
            if info.get("ready"):
                self.lbl_kibali.setText("  KIBALI: ✅ prêt (4-bit NF4)")
                self.lbl_kibali.setStyleSheet("color:#06d6a0;")
                self._timer.stop()
            elif info.get("error"):
                self.lbl_kibali.setText(f"  KIBALI: ❌ {info['error'][:40]}")
                self.lbl_kibali.setStyleSheet("color:#ef476f;")
                self._timer.stop()
        except Exception:
            pass   # API pas encore démarrée

    # ─── Ouverture fichiers ────────────────────────────────────────────────────
    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Ouvrir fichier(s) pressiométrique(s)",
            str(Path.home()),
            "Excel (*.xlsx *.xls);;Tous (*.*)"
        )
        if not paths:
            return
        for p in paths:
            self._load_file(p)

    def _load_file(self, path: str):
        self.status.showMessage(f"Chargement : {Path(path).name}…")
        w = WorkerThread(self.client.parse_file, path)
        w.done.connect(lambda parsed, p=path: self._on_parsed(parsed, p))
        w.error.connect(lambda err: self._show_error(f"Erreur parsing :\n{err}"))
        self._worker = w
        w.start()

    def _on_parsed(self, parsed: ParsedFile, path: str):
        self.parsed_files[parsed.filename] = parsed
        self._refresh_tree()
        self.status.showMessage(f"✅ Chargé : {parsed.filename} — {len(parsed.essais)} essais")
        # Mettre à jour onglet données
        self.tab_data.load_parsed(parsed)

    # ─── Analyse complète ─────────────────────────────────────────────────────
    def analyze_all(self):
        if not self.parsed_files:
            QMessageBox.warning(self, "Aucun fichier", "Ouvrez d'abord un fichier Excel.")
            return
        self.status.showMessage("Analyse en cours…")
        dlg = QProgressDialog("Analyse des essais…", "Annuler", 0, 0, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.show()

        def do_work():
            results = {}
            for fname, parsed in self.parsed_files.items():
                calibrage  = parsed.calibrage or parsed.essais.get("Calibrage") or parsed.essais.get("calibrage")
                etalonnage = parsed.essais.get("Etalonnage 1") or next(
                    (e for k, e in parsed.essais.items() if "talon" in k.lower()), None)

                for sheet, essai in parsed.essais.items():
                    if essai.is_calibrage or essai.is_etalonnage:
                        continue
                    from api.models import CleanRequest, CalcRequest
                    req_c = CleanRequest(essai=essai, calibrage=calibrage, etalonnage=etalonnage)
                    cleaned = self.client.clean_essai(req_c)
                    req_p = CalcRequest(cleaned=cleaned)
                    params = self.client.calculate(req_p)
                    results[sheet] = (cleaned, params)
            return results

        def on_done(results):
            dlg.close()
            for sheet, (cleaned, params) in results.items():
                self.cleaned_map[sheet] = cleaned
                self.params_map[sheet]  = params
            self._refresh_tree()
            self._compute_profile()
            self._compute_section()
            self._compute_cloud3d()
            self.tab_analysis.refresh(self.cleaned_map, self.params_map)
            self.tab_profile.refresh(self.profile)
            self.tab_subsurface.refresh(self.params_map, self.cleaned_map)
            # Injecter les données réelles dans l'IA (RAG)
            self.tab_ai.update_data(self.params_map, self.cleaned_map, self.parsed_files)
            self.tab_report.set_data(
                list(self.parsed_files.values())[0] if self.parsed_files else None,
                list(self.cleaned_map.values()),
                list(self.params_map.values()),
                self.profile, self.boreholes,
            )
            self.status.showMessage(f"✅ {len(results)} essais analysés.")

        w = WorkerThread(do_work)
        w.done.connect(on_done)
        w.error.connect(lambda err: (dlg.close(), self._show_error(f"Erreur analyse :\n{err}")))
        self._worker = w
        w.start()

    def _compute_profile(self):
        params_list = list(self.params_map.values())
        if not params_list:
            return
        req = ProfileRequest(params_list=params_list)
        try:
            self.profile = self.client.build_profile(req)
        except Exception as e:
            self.status.showMessage(f"⚠ Profil non calculé : {e}")

    def _compute_section(self):
        params_list = list(self.params_map.values())
        if not params_list:
            return
        unique_sondages = list(dict.fromkeys(
            p.ref_sondage or (p.sheet_name.split()[0] if p.sheet_name else "SP")
            for p in params_list
        ))
        self.boreholes = [
            {"name": s, "x_m": float(i * 10), "y_m": 0.0}
            for i, s in enumerate(unique_sondages)
        ]
        req = SectionRequest(params_list=params_list, boreholes=self.boreholes)
        try:
            self.section_data = self.client.build_section(req)
            self.tab_section.refresh(self.section_data)
        except Exception as e:
            self.status.showMessage(f"⚠ Coupe géologique non calculée : {e}")

    def _compute_cloud3d(self):
        params_list = list(self.params_map.values())
        if not params_list:
            return
        boreholes = self.boreholes or [{"name": "SP", "x_m": 0.0, "y_m": 0.0}]
        req = Cloud3DRequest(params_list=params_list, boreholes=boreholes)
        try:
            self.cloud3d_data = self.client.build_cloud3d(req)
            self.tab_cloud3d.refresh(self.cloud3d_data, self.cleaned_map, self.params_map)
        except Exception as e:
            self.status.showMessage(f"⚠ Nuage 3D non calculé : {e}")

    # ─── Arborescence ─────────────────────────────────────────────────────────
    def _refresh_tree(self):
        self.tree.clear()
        for fname, parsed in self.parsed_files.items():
            root = QTreeWidgetItem(self.tree, [fname])
            root.setData(0, Qt.ItemDataRole.UserRole, ("file", fname))
            for sheet, essai in parsed.essais.items():
                icon = "📐" if essai.is_calibrage else ("🔧" if essai.is_etalonnage else "📊")
                item = QTreeWidgetItem(root, [f"{icon} {sheet}"])
                item.setData(0, Qt.ItemDataRole.UserRole, ("essai", sheet))
                if sheet in self.params_map:
                    p = self.params_map[sheet]
                    item.setToolTip(0, f"Em={p.Em_MPa} MPa  Pl={p.Pl_MPa} MPa  Qualité={p.qualite}")
            root.setExpanded(True)

    # ─── Clic arborescence ────────────────────────────────────────────────────
    def _on_tree_item_click(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return
        kind, name = data
        if kind == "essai":
            if name in self.cleaned_map:
                self.tab_analysis.show_essai(name)
                self.tabs.setCurrentWidget(self.tab_analysis)
                # Synchroniser l'essai actif dans l'onglet IA
                self.tab_ai.set_current_essai(name)
            else:
                # Essai non encore analysé ou calibrage/étalonnage → données brutes
                for parsed in self.parsed_files.values():
                    if name in parsed.essais:
                        self.tab_data.load_parsed(parsed)
                        if hasattr(self.tab_data, 'cmb_sheet'):
                            self.tab_data.cmb_sheet.setCurrentText(name)
                        self.tabs.setCurrentWidget(self.tab_data)
                        self.status.showMessage(
                            f"⚠ '{name}' non encore analysé — cliquez ⚡ Analyser tout"
                        )
                        break

    # ─── Utilitaires ──────────────────────────────────────────────────────────
    def _show_error(self, msg: str):
        QMessageBox.critical(self, "Erreur", msg)
        self.status.showMessage("❌ Erreur — voir détails.")

    def closeEvent(self, event):
        self.client.close()
        event.accept()
