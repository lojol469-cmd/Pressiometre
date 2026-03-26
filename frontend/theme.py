"""
frontend/theme.py — Système de thèmes PressiomètreIA (SETRAF GABON)
6 thèmes professionnels avec sélecteur visuel interactif.
Thèmes : Océan Nuit · Forêt Tropicale · Cosmos Violet · Braise Atlas · Nuit Arctique · Classique Lumière
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QWidget, QScrollArea, QFrame,
    QApplication,
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui  import QFont


# ═══════════════════════════════════════════════════════════════════════════════
# CATALOGUE DES PALETTES
# Chaque palette définit TOUS les tokens de couleur utilisés dans le QSS.
# ═══════════════════════════════════════════════════════════════════════════════
THEMES: list[dict] = [
    # ── 1. Océan Nuit (défaut SETRAF) ──────────────────────────────────────
    {
        "name": "Océan Nuit",
        "icon": "🌊",
        "desc": "Bleu marine profond · SETRAF défaut",
        # fonds
        "bg0": "#0b0f1a",  "bg1": "#080c14",  "bg2": "#111827",
        "bg3": "#1a2236",  "bg4": "#1e3a5f",  "bg5": "#0d2040",
        # accents
        "acc1": "#38bdf8",  "acc2": "#fbbf24",  "acc3": "#06d6a0",
        "acc4": "#f97316",  "acc5": "#ef4444",
        # textes
        "txt0": "#e2e8f0",  "txt1": "#cbd5e1",  "txt2": "#94a3b8",  "txt3": "#64748b",
        # bordures
        "brd0": "#1e3352",  "brd1": "#2d5a8a",
        # bouton principal
        "btn0": "#1e3a5f",  "btn1": "#162d4a",  "btn_fg": "#7dd3fc",  "btn_bd": "#2d5a8a",
        # bouton succès (vert)
        "btn_ok0": "#14532d",  "btn_ok1": "#0f3d22",  "btn_ok_fg": "#4ade80",  "btn_ok_bd": "#166534",
        # bouton warn (ambre)
        "btn_wa0": "#422006",  "btn_wa1": "#2d1504",  "btn_wa_fg": "#fbbf24",  "btn_wa_bd": "#78350f",
        # toolbar
        "tb0": "#111827",  "tb1": "#0b0f1a",  "tb_line": "#f97316",
        # onglet sélectionné
        "tab_line": "#38bdf8",
        # sidebar
        "sidebar_acc": "#38bdf8",
    },
    # ── 2. Forêt Tropicale ─────────────────────────────────────────────────
    {
        "name": "Forêt Tropicale",
        "icon": "🌿",
        "desc": "Vert émeraude · Géologie naturelle",
        "bg0": "#030f09",  "bg1": "#020c07",  "bg2": "#0a1a10",
        "bg3": "#112a18",  "bg4": "#0d3d22",  "bg5": "#093318",
        "acc1": "#06d6a0",  "acc2": "#a3e635",  "acc3": "#38bdf8",
        "acc4": "#fb923c",  "acc5": "#ef4444",
        "txt0": "#ecfdf5",  "txt1": "#d1fae5",  "txt2": "#6ee7b7",  "txt3": "#059669",
        "brd0": "#0d3d22",  "brd1": "#14532d",
        "btn0": "#0d3d22",  "btn1": "#093318",  "btn_fg": "#6ee7b7",  "btn_bd": "#14532d",
        "btn_ok0": "#1a5c2a",  "btn_ok1": "#0f3d1c",  "btn_ok_fg": "#6ee7b7",  "btn_ok_bd": "#166534",
        "btn_wa0": "#4a2a06",  "btn_wa1": "#33200a",  "btn_wa_fg": "#a3e635",  "btn_wa_bd": "#6a4410",
        "tb0": "#0a1a10",  "tb1": "#030f09",  "tb_line": "#a3e635",
        "tab_line": "#06d6a0",
        "sidebar_acc": "#06d6a0",
    },
    # ── 3. Cosmos Violet ───────────────────────────────────────────────────
    {
        "name": "Cosmos Violet",
        "icon": "🔮",
        "desc": "Violet galactique · Style IA & tech",
        "bg0": "#0d0a1a",  "bg1": "#080612",  "bg2": "#13102a",
        "bg3": "#1e1840",  "bg4": "#2d1f6e",  "bg5": "#1a1245",
        "acc1": "#a78bfa",  "acc2": "#f472b6",  "acc3": "#38bdf8",
        "acc4": "#fb923c",  "acc5": "#ef4444",
        "txt0": "#f5f3ff",  "txt1": "#e9d5ff",  "txt2": "#c4b5fd",  "txt3": "#7c3aed",
        "brd0": "#2d1f6e",  "brd1": "#5b21b6",
        "btn0": "#2d1f6e",  "btn1": "#1a1245",  "btn_fg": "#c4b5fd",  "btn_bd": "#5b21b6",
        "btn_ok0": "#1a3358",  "btn_ok1": "#111e3a",  "btn_ok_fg": "#a78bfa",  "btn_ok_bd": "#2d4a8a",
        "btn_wa0": "#4a1a40",  "btn_wa1": "#330f2e",  "btn_wa_fg": "#f472b6",  "btn_wa_bd": "#7a1a5e",
        "tb0": "#13102a",  "tb1": "#0d0a1a",  "tb_line": "#f472b6",
        "tab_line": "#a78bfa",
        "sidebar_acc": "#a78bfa",
    },
    # ── 4. Braise Atlas ────────────────────────────────────────────────────
    {
        "name": "Braise Atlas",
        "icon": "🔥",
        "desc": "Orange ambré · Chaleur & énergie",
        "bg0": "#120a03",  "bg1": "#0d0702",  "bg2": "#1c1005",
        "bg3": "#2a1808",  "bg4": "#5c2d0a",  "bg5": "#451f06",
        "acc1": "#fb923c",  "acc2": "#fbbf24",  "acc3": "#06d6a0",
        "acc4": "#38bdf8",  "acc5": "#ef4444",
        "txt0": "#fff7ed",  "txt1": "#fed7aa",  "txt2": "#fdba74",  "txt3": "#c2410c",
        "brd0": "#3c1a05",  "brd1": "#7c2d12",
        "btn0": "#5c2d0a",  "btn1": "#451f06",  "btn_fg": "#fdba74",  "btn_bd": "#7c2d12",
        "btn_ok0": "#14532d",  "btn_ok1": "#0f3d22",  "btn_ok_fg": "#4ade80",  "btn_ok_bd": "#166534",
        "btn_wa0": "#60420a",  "btn_wa1": "#422d07",  "btn_wa_fg": "#fbbf24",  "btn_wa_bd": "#a06a10",
        "tb0": "#1c1005",  "tb1": "#120a03",  "tb_line": "#fbbf24",
        "tab_line": "#fb923c",
        "sidebar_acc": "#fb923c",
    },
    # ── 5. Nuit Arctique ───────────────────────────────────────────────────
    {
        "name": "Nuit Arctique",
        "icon": "❄️",
        "desc": "Gris acier · Minimaliste épuré",
        "bg0": "#08090b",  "bg1": "#050607",  "bg2": "#0f1114",
        "bg3": "#171a1e",  "bg4": "#252b35",  "bg5": "#1a2030",
        "acc1": "#94a3b8",  "acc2": "#e2e8f0",  "acc3": "#22d3ee",
        "acc4": "#fbbf24",  "acc5": "#ef4444",
        "txt0": "#f8fafc",  "txt1": "#e2e8f0",  "txt2": "#94a3b8",  "txt3": "#475569",
        "brd0": "#1e293b",  "brd1": "#334155",
        "btn0": "#252b35",  "btn1": "#1a2030",  "btn_fg": "#94a3b8",  "btn_bd": "#334155",
        "btn_ok0": "#1a3020",  "btn_ok1": "#0f2015",  "btn_ok_fg": "#22d3ee",  "btn_ok_bd": "#1e4030",
        "btn_wa0": "#3a2a0a",  "btn_wa1": "#2a1e06",  "btn_wa_fg": "#fbbf24",  "btn_wa_bd": "#6a4a10",
        "tb0": "#0f1114",  "tb1": "#08090b",  "tb_line": "#475569",
        "tab_line": "#94a3b8",
        "sidebar_acc": "#94a3b8",
    },
    # ── 6. Classique Lumière ───────────────────────────────────────────────
    {
        "name": "Classique Lumière",
        "icon": "☀️",
        "desc": "Blanc professionnel · Mode jour",
        "bg0": "#f0f4f8",  "bg1": "#e2e8f0",  "bg2": "#ffffff",
        "bg3": "#dbeafe",  "bg4": "#bfdbfe",  "bg5": "#eff6ff",
        "acc1": "#2563eb",  "acc2": "#1e40af",  "acc3": "#059669",
        "acc4": "#d97706",  "acc5": "#dc2626",
        "txt0": "#0f172a",  "txt1": "#1e293b",  "txt2": "#475569",  "txt3": "#94a3b8",
        "brd0": "#cbd5e1",  "brd1": "#93c5fd",
        "btn0": "#dbeafe",  "btn1": "#bfdbfe",  "btn_fg": "#1d4ed8",  "btn_bd": "#93c5fd",
        "btn_ok0": "#d1fae5",  "btn_ok1": "#a7f3d0",  "btn_ok_fg": "#059669",  "btn_ok_bd": "#6ee7b7",
        "btn_wa0": "#fef3c7",  "btn_wa1": "#fde68a",  "btn_wa_fg": "#d97706",  "btn_wa_bd": "#fcd34d",
        "tb0": "#e2e8f0",  "tb1": "#f0f4f8",  "tb_line": "#d97706",
        "tab_line": "#2563eb",
        "sidebar_acc": "#2563eb",
    },
]

THEME_MAP: dict[str, dict] = {t["name"]: t for t in THEMES}
DEFAULT_THEME = "Océan Nuit"
_SETTINGS_KEY = "pressiometre/theme"


# ═══════════════════════════════════════════════════════════════════════════════
# PERSISTANCE
# ═══════════════════════════════════════════════════════════════════════════════

def load_saved_theme() -> str:
    return QSettings("SETRAF", "PressiomètreIA").value(_SETTINGS_KEY, DEFAULT_THEME)


def save_theme(name: str) -> None:
    QSettings("SETRAF", "PressiomètreIA").setValue(_SETTINGS_KEY, name)


def get_palette(name: str) -> dict:
    return THEME_MAP.get(name, THEME_MAP[DEFAULT_THEME])


# ═══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATEUR QSS
# ═══════════════════════════════════════════════════════════════════════════════

def build_qss(p: dict) -> str:
    """Génère le QSS complet depuis une palette de thème."""
    return f"""
/* ── Base ── */
QMainWindow, QDialog, QWidget {{
  background: {p['bg0']};
  color: {p['txt0']};
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 10pt;
}}

/* ── Tabs ── */
QTabWidget::pane {{
  border: 1px solid {p['brd0']};
  background: {p['bg0']};
  border-radius: 0 4px 4px 4px;
}}
QTabBar::tab {{
  background: {p['bg2']};
  color: {p['txt3']};
  padding: 9px 22px;
  border-radius: 6px 6px 0 0;
  border: 1px solid {p['brd0']};
  border-bottom: none;
  margin-right: 2px;
  font-weight: 500;
}}
QTabBar::tab:selected {{
  background: {p['bg0']};
  color: {p['acc1']};
  border-color: {p['brd1']};
  border-bottom: 3px solid {p['tab_line']};
  font-weight: 700;
  padding-bottom: 7px;
}}
QTabBar::tab:hover:!selected {{
  background: {p['bg3']};
  color: {p['txt1']};
  border-color: {p['brd0']};
}}

/* ── Toolbar ── */
QToolBar {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 {p['tb0']}, stop:1 {p['tb1']});
  border-bottom: 2px solid {p['tb_line']};
  spacing: 4px;
  padding: 3px 8px;
}}
QToolBar QToolButton {{
  background: transparent;
  color: {p['txt2']};
  border: none;
  border-radius: 5px;
  padding: 5px 10px;
  font-size: 10pt;
  min-width: 32px;
}}
QToolBar QToolButton:hover {{
  background: {p['bg4']};
  color: {p['acc1']};
  border: 1px solid {p['brd0']};
}}
QToolBar QToolButton:pressed {{
  background: {p['bg5']};
  color: {p['acc2']};
}}
QToolBar::separator {{
  background: {p['brd0']};
  width: 1px;
  margin: 4px 6px;
}}

/* ── MenuBar ── */
QMenuBar {{
  background: {p['bg1']};
  color: {p['txt1']};
  border-bottom: 1px solid {p['brd0']};
}}
QMenuBar::item:selected {{ background: {p['bg4']}; color: {p['acc1']}; }}
QMenu {{
  background: {p['bg2']};
  color: {p['txt1']};
  border: 1px solid {p['brd0']};
  border-radius: 4px;
  padding: 4px 0;
}}
QMenu::item {{ padding: 6px 20px; }}
QMenu::item:selected {{ background: {p['bg4']}; color: {p['acc1']}; }}
QMenu::separator {{ height: 1px; background: {p['brd0']}; margin: 3px 0; }}

/* ── StatusBar ── */
QStatusBar {{
  background: {p['bg1']};
  color: {p['txt3']};
  border-top: 1px solid {p['brd0']};
  font-size: 9pt;
}}
QStatusBar::item {{ border: none; }}

/* ── TreeWidget (sidebar) ── */
QTreeWidget {{
  background: {p['bg1']};
  alternate-background-color: {p['bg2']};
  color: {p['txt1']};
  border: none;
  outline: none;
  padding: 4px 2px;
}}
QTreeWidget::item {{
  padding: 5px 4px;
  border-radius: 4px;
}}
QTreeWidget::item:selected {{
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 {p['bg4']}, stop:1 {p['bg3']});
  color: {p['acc1']};
}}
QTreeWidget::item:hover:!selected {{
  background: {p['bg3']};
}}

/* ── Tables ── */
QTableWidget {{
  background: {p['bg1']};
  color: {p['txt1']};
  gridline-color: {p['bg3']};
  border: 1px solid {p['brd0']};
  border-radius: 4px;
  selection-background-color: {p['bg4']};
}}
QTableWidget::item:selected {{
  background: {p['bg4']};
  color: {p['txt0']};
}}
QHeaderView::section {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 {p['bg4']}, stop:1 {p['bg5']});
  color: {p['acc1']};
  font-weight: 700;
  padding: 6px 8px;
  border: none;
  border-right: 1px solid {p['brd0']};
  border-bottom: 2px solid {p['acc1']};
}}

/* ── Buttons ── */
QPushButton {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 {p['btn0']}, stop:1 {p['btn1']});
  color: {p['btn_fg']};
  border: 1px solid {p['btn_bd']};
  border-radius: 5px;
  padding: 6px 16px;
  font-weight: 600;
}}
QPushButton:hover {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 {p['btn_bd']}, stop:1 {p['btn0']});
  color: {p['txt0']};
  border-color: {p['acc1']};
}}
QPushButton:pressed {{
  background: {p['bg4']};
  color: {p['acc2']};
  border-color: {p['acc1']};
}}
QPushButton:disabled {{
  background: {p['bg2']};
  color: {p['txt3']};
  border-color: {p['brd0']};
}}

/* Bouton vert "Analyser" */
QPushButton[role="success"] {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 {p['btn_ok0']}, stop:1 {p['btn_ok1']});
  color: {p['btn_ok_fg']};
  border: 1px solid {p['btn_ok_bd']};
}}
QPushButton[role="success"]:hover {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 {p['btn_ok_bd']}, stop:1 {p['btn_ok0']});
  color: {p['txt0']};
  border-color: {p['acc3']};
}}

/* Bouton ambre "Rapport/Warn" */
QPushButton[role="warn"] {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 {p['btn_wa0']}, stop:1 {p['btn_wa1']});
  color: {p['btn_wa_fg']};
  border: 1px solid {p['btn_wa_bd']};
}}
QPushButton[role="warn"]:hover {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 {p['btn_wa_bd']}, stop:1 {p['btn_wa0']});
  color: {p['txt0']};
  border-color: {p['acc2']};
}}

/* ── Input fields ── */
QLineEdit, QTextEdit, QPlainTextEdit {{
  background: {p['bg1']};
  color: {p['txt0']};
  border: 1px solid {p['brd0']};
  border-radius: 5px;
  padding: 5px 8px;
  selection-background-color: {p['bg4']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
  border-color: {p['acc1']};
  background: {p['bg2']};
}}

/* ── ComboBox ── */
QComboBox {{
  background: {p['bg2']};
  color: {p['txt1']};
  border: 1px solid {p['brd0']};
  border-radius: 5px;
  padding: 4px 8px;
  min-width: 80px;
}}
QComboBox:hover {{ border-color: {p['acc1']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
  background: {p['bg2']};
  color: {p['txt1']};
  border: 1px solid {p['brd0']};
  selection-background-color: {p['bg4']};
  outline: none;
}}

/* ── GroupBox ── */
QGroupBox {{
  border: 1px solid {p['brd0']};
  border-radius: 6px;
  margin-top: 14px;
  padding-top: 12px;
  background: {p['bg1']};
}}
QGroupBox::title {{
  subcontrol-origin: margin;
  subcontrol-position: top left;
  left: 10px;
  padding: 0 6px;
  background: {p['bg0']};
  font-weight: 700;
  color: {p['acc1']};
}}

/* ── Labels ── */
QLabel {{ color: {p['txt1']}; }}

/* ── Scrollbars ── */
QScrollBar:vertical {{
  background: {p['bg1']};
  width: 8px; margin: 0; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
  background: {p['brd1']};
  border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {p['acc1']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
  background: {p['bg1']};
  height: 8px; border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
  background: {p['brd1']};
  border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p['acc1']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── ListWidget ── */
QListWidget {{
  background: {p['bg1']};
  color: {p['txt1']};
  border: 1px solid {p['brd0']};
  border-radius: 4px; outline: none;
}}
QListWidget::item {{ padding: 3px 6px; }}
QListWidget::item:selected {{ background: {p['bg4']}; color: {p['txt0']}; }}
QListWidget::item:hover:!selected {{ background: {p['bg3']}; }}

/* ── Splitter ── */
QSplitter::handle {{ background: {p['brd0']}; width: 2px; height: 2px; }}
QSplitter::handle:hover {{ background: {p['acc1']}; }}

/* ── Progress ── */
QProgressDialog {{
  background: {p['bg0']};
  color: {p['txt0']};
  border: 1px solid {p['acc1']};
  border-radius: 8px;
}}
QProgressBar {{
  background: {p['bg2']};
  color: {p['acc1']};
  border: 1px solid {p['brd0']};
  border-radius: 4px;
  text-align: center; font-size: 9pt;
}}
QProgressBar::chunk {{
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 {p['acc1']}, stop:1 {p['acc2']});
  border-radius: 4px;
}}

/* ── Tooltips ── */
QToolTip {{
  background: {p['bg4']};
  color: {p['txt0']};
  border: 1px solid {p['acc1']};
  padding: 4px 8px; border-radius: 4px; font-size: 9pt;
}}

/* ── MessageBox ── */
QMessageBox {{ background: {p['bg0']}; color: {p['txt0']}; }}
QMessageBox QPushButton {{ min-width: 80px; }}

/* ── Slider ── */
QSlider::groove:horizontal {{
  height: 4px; background: {p['brd0']}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
  width: 14px; height: 14px; background: {p['acc1']};
  border-radius: 7px; margin: -5px 0;
}}
QSlider::sub-page:horizontal {{ background: {p['acc1']}; border-radius: 2px; }}

/* ── SpinBox ── */
QSpinBox, QDoubleSpinBox {{
  background: {p['bg1']};
  color: {p['txt0']};
  border: 1px solid {p['brd0']};
  border-radius: 4px; padding: 3px 6px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {p['acc1']}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
  background: {p['bg3']}; border: none; width: 16px;
}}

/* ── CheckBox ── */
QCheckBox {{ color: {p['txt1']}; spacing: 6px; }}
QCheckBox::indicator {{
  width: 14px; height: 14px;
  border: 1px solid {p['brd1']};
  border-radius: 3px; background: {p['bg2']};
}}
QCheckBox::indicator:checked {{
  background: {p['acc1']}; border-color: {p['acc1']};
}}
QCheckBox::indicator:hover {{ border-color: {p['acc1']}; }}

/* ── RadioButton ── */
QRadioButton {{ color: {p['txt1']}; spacing: 6px; }}
QRadioButton::indicator {{
  width: 14px; height: 14px;
  border: 1px solid {p['brd1']};
  border-radius: 7px; background: {p['bg2']};
}}
QRadioButton::indicator:checked {{
  background: {p['acc1']}; border-color: {p['acc1']};
}}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# CARTE DE THÈME (widget dans le sélecteur)
# ═══════════════════════════════════════════════════════════════════════════════

class _ThemeCard(QFrame):
    clicked = pyqtSignal(str)  # nom du thème

    def __init__(self, palette: dict, is_active: bool, parent=None):
        super().__init__(parent)
        self._name = palette["name"]
        self._palette = palette
        self.setObjectName("themeCard")
        self.setMinimumHeight(110)
        self.setMaximumHeight(130)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rebuild(palette, is_active)

    def _rebuild(self, p: dict, active: bool):
        # Nettoyer layout existant
        old = self.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QWidget().setLayout(old)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(5)

        # ── En-tête : icône + nom + badge actif ──────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        icon_lbl = QLabel(p["icon"])
        icon_lbl.setFont(QFont("Segoe UI Emoji", 18))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        hdr.addWidget(icon_lbl)

        name_lbl = QLabel(p["name"])
        name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet(
            f"color: {p['acc1']}; background: transparent; border: none;"
        )
        hdr.addWidget(name_lbl)
        hdr.addStretch()

        if active:
            badge = QLabel("  ✓ Actif  ")
            badge.setStyleSheet(
                f"background: {p['acc1']}; color: {p['bg0']};"
                f"padding: 2px 8px; border-radius: 10px;"
                f"font-size: 8pt; font-weight: bold; border: none;"
            )
            hdr.addWidget(badge)
        layout.addLayout(hdr)

        # ── Description ──────────────────────────────────────────────────
        desc_lbl = QLabel(p["desc"])
        desc_lbl.setStyleSheet(
            f"color: {p['txt2']}; font-size: 8pt; background: transparent; border: none;"
        )
        layout.addWidget(desc_lbl)

        # ── Palette de couleurs (dots) ────────────────────────────────────
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(5)
        swatches = [
            ("acc1", p["acc1"], "Accent principal"),
            ("acc2", p["acc2"], "Accent secondaire"),
            ("acc3", p["acc3"], "Succès"),
            ("bg0",  p["bg0"],  "Fond principal"),
            ("bg2",  p["bg2"],  "Fond widget"),
            ("bg4",  p["bg4"],  "Sélection"),
        ]
        for key, color, tip in swatches:
            dot = QLabel()
            dot.setFixedSize(16, 16)
            dot.setStyleSheet(
                f"background: {color}; border-radius: 8px;"
                f"border: 1px solid {p['brd1']};"
            )
            dot.setToolTip(f"{tip}: {color}")
            swatch_row.addWidget(dot)
        swatch_row.addStretch()
        layout.addLayout(swatch_row)

        # ── Style de la carte ─────────────────────────────────────────────
        border_color  = p["acc1"] if active else p["brd0"]
        border_width  = "2px"     if active else "1px"
        bg_card       = p["bg3"]  if active else p["bg1"]

        self.setStyleSheet(
            f"QFrame#themeCard {{"
            f"  background: {bg_card};"
            f"  border: {border_width} solid {border_color};"
            f"  border-left: 4px solid {p['acc1']};"
            f"  border-radius: 8px;"
            f"}}"
            f"QFrame#themeCard:hover {{"
            f"  border-color: {p['acc1']};"
            f"  background: {p['bg3']};"
            f"}}"
        )

    def set_active(self, active: bool):
        self._rebuild(self._palette, active)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._name)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# DIALOGUE SÉLECTEUR DE THÈME
# ═══════════════════════════════════════════════════════════════════════════════

class ThemePickerDialog(QDialog):
    """
    Dialogue visuel de sélection de thème.
    Cliquer sur une carte applique immédiatement le thème (aperçu en temps réel).
    Fermer la fenêtre conserve le thème actif.
    """
    theme_changed = pyqtSignal(str)  # émis sur chaque changement

    def __init__(self, current_theme: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎨 Choisir un thème — PressiomètreIA")
        self.setMinimumSize(780, 560)
        self.setModal(True)
        self._current = current_theme
        self._cards: dict[str, _ThemeCard] = {}
        self._build_ui()

    def _build_ui(self):
        p = get_palette(self._current)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # ── En-tête ──────────────────────────────────────────────────────
        hdr_layout = QHBoxLayout()
        title = QLabel("🎨  Palette de thèmes")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {p['acc1']}; background: transparent;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        lbl_hint = QLabel("Cliquez sur un thème pour l'appliquer instantanément")
        lbl_hint.setStyleSheet(f"color: {p['txt3']}; font-size: 9pt;")
        hdr_layout.addWidget(lbl_hint)
        root.addLayout(hdr_layout)

        # Séparateur
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {p['brd0']};")
        root.addWidget(sep)

        # ── Grille des cartes ────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {p['bg0']}; }}"
        )

        grid_widget = QWidget()
        grid_widget.setStyleSheet(f"background: {p['bg0']};")
        grid = QGridLayout(grid_widget)
        grid.setSpacing(12)
        grid.setContentsMargins(4, 4, 4, 4)

        for i, theme in enumerate(THEMES):
            active = theme["name"] == self._current
            card = _ThemeCard(theme, active)
            card.clicked.connect(self._on_card_clicked)
            self._cards[theme["name"]] = card
            row, col = divmod(i, 2)
            grid.addWidget(card, row, col)

        scroll.setWidget(grid_widget)
        root.addWidget(scroll, stretch=1)

        # ── Bas : thème actif + bouton fermer ────────────────────────────
        bottom = QHBoxLayout()

        self.lbl_active = QLabel(f"Thème actif : {self._current}")
        self.lbl_active.setStyleSheet(
            f"color: {p['acc2']}; font-size: 9pt; font-weight: bold;"
        )
        bottom.addWidget(self.lbl_active)
        bottom.addStretch()

        btn_close = QPushButton("✅  Fermer")
        btn_close.setMinimumWidth(120)
        btn_close.setStyleSheet(
            f"background: {p['btn_ok0']}; color: {p['btn_ok_fg']};"
            f"border: 1px solid {p['btn_ok_bd']}; border-radius: 5px;"
            f"padding: 8px 20px; font-weight: bold;"
        )
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    def _on_card_clicked(self, name: str):
        if name == self._current:
            return
        # Mettre à jour les cartes
        if self._current in self._cards:
            self._cards[self._current].set_active(False)
        self._current = name
        if name in self._cards:
            self._cards[name].set_active(True)
        # Mettre à jour le label
        self.lbl_active.setText(f"Thème actif : {name}")
        # Émettre le signal → main_window applique immédiatement
        self.theme_changed.emit(name)
