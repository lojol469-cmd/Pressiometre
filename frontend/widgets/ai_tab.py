"""
Onglet IA KIBALI — Chat géotechnique avec accès aux données réelles (RAG).
KIBALI perçoit toutes les données chargées, anomalies, courbes et paramètres.
"""
from __future__ import annotations
from typing import Optional, Dict, List
import html as _html
import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QSpinBox,
    QGroupBox, QSplitter, QCheckBox, QScrollArea,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui  import QFont, QColor, QTextCursor, QTextCharFormat


class KibaliWorker(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn, self._a, self._kw = fn, args, kwargs

    def run(self):
        try:
            self.done.emit(self._fn(*self._a, **self._kw))
        except Exception as exc:
            self.error.emit(str(exc))


class PdfWorker(QThread):
    """Worker dédié à la génération PDF — retourne des bytes."""
    done  = pyqtSignal(object)   # bytes
    error = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:
            self.error.emit(str(exc))


# ─── Constructeur de contexte RAG ─────────────────────────────────────────────
def build_rag_context(params_map: dict, cleaned_map: dict, parsed_files: dict,
                      current_essai: Optional[str] = None,
                      max_chars: int = 6000) -> str:
    """
    Construit un contexte textuel structuré à partir des données pressiométriques réelles.
    Priorité : essai actif (détail complet) → synthèse tous essais.
    max_chars : limite de taille pour ne pas dépasser la fenêtre de contexte du modèle.
    """
    lines: List[str] = []

    # ── En-tête global ──────────────────────────────────────────────────────
    n_files  = len(parsed_files)
    n_essais = len(params_map)
    filenames = ", ".join(f.replace("\\", "/").split("/")[-1] for f in parsed_files)
    lines.append("=== DONNÉES PRESSIOMÉTRIQUES CHARGÉES ===")
    lines.append(f"Fichiers : {filenames or 'aucun'}")
    lines.append(f"Essais analysés : {n_essais}")

    if not params_map:
        lines.append("(Aucun essai analysé — charge un fichier Excel et clique Analyser)")
        return "\n".join(lines)

    # ── Essai actif (détail complet) ─────────────────────────────────────────
    active = current_essai or (next(iter(params_map)) if params_map else None)
    if active and active in params_map:
        p = params_map[active]
        c = cleaned_map.get(active)
        lines.append(f"\n=== ESSAI ACTIF : {active} ===")
        lines.append(f"Profondeur        : {p.depth_m} m")
        lines.append(f"Module Em         : {p.Em_MPa:.3f} MPa" if p.Em_MPa else "Module Em         : non calculé")
        lines.append(f"Pression limite Pl: {p.Pl_MPa:.3f} MPa" if p.Pl_MPa else "Pression limite Pl: non calculée")
        lines.append(f"Pression fluage Pf: {p.Pf_MPa:.3f} MPa" if p.Pf_MPa else "Pression fluage Pf: non calculée")
        lines.append(f"Pl* (nette)       : {p.Pl_star_MPa:.3f} MPa" if p.Pl_star_MPa else "Pl* (nette)       : —")
        lines.append(f"Rapport Em/Pl     : {p.ratio_Em_Pl:.2f}" if p.ratio_Em_Pl else "Rapport Em/Pl     : —")
        lines.append(f"Classification sol: {p.sol_type or '?'}")
        lines.append(f"NC/SC             : {p.nc_status or '?'}")
        lines.append(f"Qualité essai     : {p.qualite or '?'}")
        lines.append(f"Cohérence         : {'✅ Cohérent' if p.is_coherent else '⚠️ INCOHÉRENT'}")
        if p.notes:
            for note in (p.notes if isinstance(p.notes, list) else [p.notes]):
                lines.append(f"Note              : {note}")

        if c and c.points:
            pts_ok   = [pt for pt in c.points if not pt.anomalie]
            pts_anom = [pt for pt in c.points if pt.anomalie]
            lines.append(f"Points valides    : {len(pts_ok)} | Anomalies paliers : {len(pts_anom)}")
            if pts_ok:
                lines.append("Courbe P-V (P_corr MPa → Vm_corr cm³) :")
                for pt in pts_ok[:20]:
                    p_val = f"{pt.P60_corr_MPa:.4f}" if pt.P60_corr_MPa is not None else "—"
                    v_val = f"{pt.Vm_corr_cm3:.1f}" if pt.Vm_corr_cm3 is not None else "—"
                    lines.append(f"  P={p_val}  V={v_val}")
            if pts_anom:
                lines.append("Paliers anomalies :")
                for pt in pts_anom[:5]:
                    reason = pt.anomalie_type or "type inconnu"
                    p_val = f"{pt.P60_corr_MPa:.4f}" if pt.P60_corr_MPa is not None else "?"
                    lines.append(f"  P={p_val} MPa → {reason}")
            # Anomalies structurelles de l'essai entier
            if c.anomalies:
                lines.append("Anomalies détectées sur l'essai :")
                for anom in c.anomalies[:6]:
                    lines.append(f"  [{anom.severity.upper()}] palier {anom.palier} — {anom.type}: {anom.description}")
            # Incohérences
            if c.coherence:
                for chk in c.coherence:
                    if not chk.ok:
                        lines.append(f"  ⚠ Incohérence: {chk.message}")

    # ── Synthèse de tous les essais ──────────────────────────────────────────
    lines.append("\n=== SYNTHÈSE TOUS LES ESSAIS ===")
    lines.append(f"{'Essai':<14} {'Prof m':>6} {'Em MPa':>8} {'Pl MPa':>8} {'Pf MPa':>8} "
                 f"{'Em/Pl':>6} {'NC/SC':>5} {'Qual':>5} {'Sol':<20}")
    lines.append("-" * 80)
    em_vals, pl_vals, depths = [], [], []
    nc_count, sc_count = 0, 0
    for name, p in list(params_map.items())[:40]:  # max 40 lignes
        em   = f"{p.Em_MPa:.2f}" if p.Em_MPa else "—"
        pl   = f"{p.Pl_MPa:.3f}" if p.Pl_MPa else "—"
        pf   = f"{p.Pf_MPa:.3f}" if p.Pf_MPa else "—"
        ratio = f"{p.ratio_Em_Pl:.1f}" if p.ratio_Em_Pl else "—"
        lines.append(f"{name:<14} {str(p.depth_m or '?'):>6} {em:>8} {pl:>8} {pf:>8} "
                     f"{ratio:>6} {p.nc_status or '?':>5} {p.qualite or '?':>5} "
                     f"{(p.sol_type or '?')[:20]:<20}")
        if p.Em_MPa:  em_vals.append(p.Em_MPa)
        if p.Pl_MPa:  pl_vals.append(p.Pl_MPa)
        if p.depth_m: depths.append(p.depth_m)
        if p.nc_status == "NC": nc_count += 1
        elif p.nc_status == "SC": sc_count += 1

    # ── Statistiques globales ────────────────────────────────────────────────
    lines.append("\n=== STATISTIQUES GLOBALES ===")
    if em_vals:
        lines.append(f"Em  : min={min(em_vals):.2f}  max={max(em_vals):.2f}  moy={sum(em_vals)/len(em_vals):.2f} MPa")
    if pl_vals:
        lines.append(f"Pl  : min={min(pl_vals):.3f}  max={max(pl_vals):.3f}  moy={sum(pl_vals)/len(pl_vals):.3f} MPa")
    if depths:
        lines.append(f"Profondeurs : {min(depths):.1f} m → {max(depths):.1f} m")
    lines.append(f"NC : {nc_count} essais | SC : {sc_count} essais")

    # tronquer si trop long
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n[... données tronquées pour limite contexte ...]"
    return result


# ─── Boutons de questions rapides ─────────────────────────────────────────────
QUICK_QUESTIONS = [
    ("🔍 Anomalies",
     "Analyse en détail toutes les anomalies dans les données de l'essai actif. "
     "Explique chaque anomalie, sa cause probable et son impact sur les résultats."),
    ("⚠️ Risque sol",
     "Évalue le risque géotechnique de ce sol. Analyse la capacité portante, "
     "le risque de tassement différentiel, et définis le niveau de risque (faible/moyen/élevé)."),
    ("🏗️ Fondation",
     "Sur la base des paramètres pressiométriques réels, quelle type de fondation recommandes-tu ? "
     "Calcule la contrainte admissible selon NF P 94-110 et donne des dimensions indicatives."),
    ("📊 Interprétation",
     "Interprète complètement les paramètres Em, Pl et Pf de l'essai actif. "
     "Type de sol, état de consolidation, résistance mécanique, et comportement sous charge."),
    ("📈 Qualité essai",
     "Évalue la qualité de l'essai actif (grade A/B/C/D selon NF P 94-110). "
     "Justifie en analysant la forme de la courbe P-V, la cohérence Em/Pl et les anomalies."),
    ("🔄 Comparaison sondages",
     "Compare tous les essais chargés. Identifie les variations stratigraphiques, "
     "les hétérogénéités du sol et les zones à risque entre les différents sondages."),
    ("📐 Calcul fondation",
     "Calcule la contrainte pressiométrique admissible σ_adm selon la formule Ménard "
     "(NF P 94-110) pour une fondation superficielle B=1m et une fondation profonde. "
     "Montre les calculs étape par étape."),
    ("🌊 Tassement",
     "Estime le tassement probable sous une charge de 200 kPa en utilisant "
     "la méthode pressiométrique Ménard. Montre les calculs avec les données réelles."),
    ("📋 Rapport synthèse",
     "Rédige une synthèse géotechnique professionnelle de l'ensemble des données chargées. "
     "Inclus : description du sol, paramètres clés, anomalies, recommandations et conclusion."),
    ("🔬 Détail courbe P-V",
     "Analyse en détail la courbe P-V de l'essai actif. Identifie les 3 phases "
     "(élastique, pseudo-élastique, plastique), les points caractéristiques, "
     "et commente la qualité de la courbe."),
]


class AITab(QWidget):
    """Onglet IA KIBALI avec accès aux données réelles (RAG)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[KibaliWorker] = None
        self._export_worker: Optional[PdfWorker] = None
        self._params_map:  dict = {}
        self._cleaned_map: dict = {}
        self._parsed_files: dict = {}
        self._current_essai: Optional[str] = None
        self._msg_count: int = 0
        self._conversation: list = []
        self._conv_context: str = ""
        self._build_ui()

    # ─── Méthodes publiques (appelées par main_window) ───────────────────────
    def update_data(self, params_map: dict, cleaned_map: dict, parsed_files: dict):
        """Met à jour les données réelles disponibles pour le RAG."""
        self._params_map  = params_map
        self._cleaned_map = cleaned_map
        self._parsed_files = parsed_files
        self._refresh_data_indicator()
        if self._chk_autocontext.isChecked():
            self._rebuild_context()

    def set_current_essai(self, name: str):
        """Définit l'essai 'actif' mis en avant dans le contexte RAG."""
        self._current_essai = name
        self._refresh_data_indicator()
        if self._chk_autocontext.isChecked():
            self._rebuild_context()

    # ─── Construction UI ─────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # ── Barre de statut et indicateur de données ──
        top = QHBoxLayout()
        self.lbl_status = QLabel("KIBALI : vérification…")
        self.lbl_status.setStyleSheet("color:#ffd166; font-size:11px; font-weight:bold;")
        top.addWidget(self.lbl_status)

        self.lbl_data = QLabel("📂 Aucune donnée chargée")
        self.lbl_data.setStyleSheet(
            "color:#64748b; font-size:10px; padding:2px 8px;"
            "background:#111827; border-radius:4px; border:1px solid #1e3352;"
        )
        top.addWidget(self.lbl_data)
        top.addStretch()

        self.btn_export_pdf = QPushButton("📄 Exporter PDF")
        self.btn_export_pdf.setToolTip("Exporter la conversation KIBALI en PDF")
        self.btn_export_pdf.setStyleSheet(
            "background:#0d3d2e; color:#06d6a0; border:1px solid #0d6e4f;"
            "border-radius:4px; padding:4px 10px; font-size:9px;"
        )
        self.btn_export_pdf.clicked.connect(self._export_chat_pdf)
        top.addWidget(self.btn_export_pdf)

        btn_check = QPushButton("↻")
        btn_check.setFixedWidth(28)
        btn_check.setToolTip("Vérifier statut KIBALI")
        btn_check.clicked.connect(self._check_status)
        top.addWidget(btn_check)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ══════════════════════════════════════════════════
        # GAUCHE — Chat principal
        # ══════════════════════════════════════════════════
        chat_widget = QWidget()
        clay = QVBoxLayout(chat_widget)
        clay.setContentsMargins(0, 0, 4, 0)
        clay.setSpacing(4)

        self.txt_history = QTextEdit()
        self.txt_history.setReadOnly(True)
        self.txt_history.setFont(QFont("Segoe UI", 9))
        self.txt_history.setStyleSheet(
            "background:#060a10; color:#e2e8f0;"
            "border:1px solid #1e3352; border-radius:6px; padding:6px;"
        )
        clay.addWidget(self.txt_history, stretch=1)

        # Indicateur de saisie
        self.lbl_thinking = QLabel("")
        self.lbl_thinking.setStyleSheet("color:#ffd166; font-size:10px;")
        clay.addWidget(self.lbl_thinking)

        # Zone saisie
        input_row = QHBoxLayout()
        self.edt_question = QLineEdit()
        self.edt_question.setPlaceholderText(
            "Posez n'importe quelle question sur vos données pressiométriques…"
        )
        self.edt_question.setStyleSheet(
            "background:#111827; color:#e2e8f0; border:1px solid #2d5a8a;"
            "border-radius:5px; padding:6px 10px; font-size:10pt;"
        )
        self.edt_question.returnPressed.connect(self._send)
        input_row.addWidget(self.edt_question)

        self.btn_send = QPushButton("Envoyer ▶")
        self.btn_send.setMinimumWidth(100)
        self.btn_send.setStyleSheet(
            "background:#1a4a7a; color:#e2e8f0; border-radius:5px; padding:6px 12px; font-weight:bold;"
        )
        self.btn_send.clicked.connect(self._send)
        input_row.addWidget(self.btn_send)
        clay.addLayout(input_row)

        splitter.addWidget(chat_widget)

        # ══════════════════════════════════════════════════
        # DROITE — Panneau contextuel
        # ══════════════════════════════════════════════════
        right = QWidget()
        right.setMinimumWidth(270)
        right.setMaximumWidth(320)
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(4, 0, 0, 0)
        rlay.setSpacing(6)

        # ── Contexte RAG ──
        grp_ctx = QGroupBox("🧠 Contexte RAG (données réelles)")
        grp_ctx.setStyleSheet(
            "QGroupBox{color:#38bdf8; font-weight:bold; border:1px solid #1e3a5f;"
            "border-radius:5px; margin-top:6px; padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin; left:8px;}"
        )
        ctx_lay = QVBoxLayout(grp_ctx)
        ctx_lay.setSpacing(4)

        ctx_top = QHBoxLayout()
        self._chk_autocontext = QCheckBox("Auto-injecter données")
        self._chk_autocontext.setChecked(True)
        self._chk_autocontext.setStyleSheet("color:#94a3b8; font-size:9px;")
        self._chk_autocontext.toggled.connect(self._on_autocontext_toggled)
        ctx_top.addWidget(self._chk_autocontext)
        btn_rebuild = QPushButton("↺")
        btn_rebuild.setFixedWidth(26)
        btn_rebuild.setToolTip("Regénérer le contexte")
        btn_rebuild.clicked.connect(self._rebuild_context)
        ctx_top.addWidget(btn_rebuild)
        ctx_lay.addLayout(ctx_top)

        self.edt_context = QTextEdit()
        self.edt_context.setPlaceholderText(
            "Le contexte RAG sera automatiquement rempli\n"
            "avec vos données pressiométriques réelles\naprès analyse.\n\n"
            "Vous pouvez aussi saisir du contexte manuellement."
        )
        self.edt_context.setMinimumHeight(160)
        self.edt_context.setMaximumHeight(250)
        self.edt_context.setStyleSheet(
            "background:#04080e; color:#94a3b8; font-size:8pt; font-family:Consolas;"
            "border:1px solid #1e3352; border-radius:4px;"
        )
        ctx_lay.addWidget(self.edt_context)
        rlay.addWidget(grp_ctx)

        # ── Analyses rapides ──
        grp_quick = QGroupBox("⚡ Analyses rapides")
        grp_quick.setStyleSheet(
            "QGroupBox{color:#06d6a0; font-weight:bold; border:1px solid #0d3d2e;"
            "border-radius:5px; margin-top:6px; padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin; left:8px;}"
        )
        q_lay = QVBoxLayout(grp_quick)
        q_lay.setSpacing(3)

        scroll_q = QScrollArea()
        scroll_q.setWidgetResizable(True)
        scroll_q.setStyleSheet("border:none; background:transparent;")
        scroll_q.setMaximumHeight(340)
        q_inner = QWidget()
        q_inner_lay = QVBoxLayout(q_inner)
        q_inner_lay.setSpacing(3)
        q_inner_lay.setContentsMargins(0, 0, 0, 0)

        for label, question in QUICK_QUESTIONS:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "text-align:left; padding:5px 8px; font-size:9pt;"
                "background:#0d1a2e; border:1px solid #1e3352; border-radius:4px;"
                "color:#94a3b8;"
                "QPushButton:hover{background:#1a2d45; color:#e2e8f0;}"
            )
            btn.clicked.connect(lambda _, q=question: self._send_quick(q))
            q_inner_lay.addWidget(btn)

        q_inner_lay.addStretch()
        scroll_q.setWidget(q_inner)
        q_lay.addWidget(scroll_q)
        rlay.addWidget(grp_quick)

        # ── Paramètres ──
        grp_set = QGroupBox("⚙ Inférence")
        grp_set.setStyleSheet(
            "QGroupBox{color:#94a3b8; border:1px solid #1e2d3d;"
            "border-radius:5px; margin-top:6px; padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin; left:8px;}"
        )
        set_lay = QHBoxLayout(grp_set)
        set_lay.addWidget(QLabel("Tokens max :"))
        self.spn_tokens = QSpinBox()
        self.spn_tokens.setRange(128, 2048)
        self.spn_tokens.setValue(768)
        self.spn_tokens.setSingleStep(128)
        set_lay.addWidget(self.spn_tokens)
        btn_clear = QPushButton("🗑")
        btn_clear.setFixedWidth(28)
        btn_clear.setToolTip("Effacer conversation")
        btn_clear.clicked.connect(self._clear_history)
        set_lay.addWidget(btn_clear)
        rlay.addWidget(grp_set)

        splitter.addWidget(right)
        splitter.setSizes([820, 290])
        layout.addWidget(splitter)

        # Afficher message d'accueil
        self._show_welcome()

    # ─── Logique contexte RAG ─────────────────────────────────────────────────
    def _rebuild_context(self):
        if not self._params_map:
            return
        ctx = build_rag_context(
            self._params_map, self._cleaned_map, self._parsed_files,
            current_essai=self._current_essai,
        )
        self.edt_context.setPlainText(ctx)

    def _on_autocontext_toggled(self, checked: bool):
        if checked and self._params_map:
            self._rebuild_context()

    def _refresh_data_indicator(self):
        n = len(self._params_map)
        if n == 0:
            self.lbl_data.setText("📂 Aucune donnée chargée")
            self.lbl_data.setStyleSheet(
                "color:#64748b; font-size:10px; padding:2px 8px;"
                "background:#111827; border-radius:4px; border:1px solid #1e3352;"
            )
        else:
            active = f" | actif: {self._current_essai}" if self._current_essai else ""
            self.lbl_data.setText(f"✅ {n} essais en mémoire{active}")
            self.lbl_data.setStyleSheet(
                "color:#06d6a0; font-size:10px; padding:2px 8px;"
                "background:#051a10; border-radius:4px; border:1px solid #0d3d2e;"
            )

    # ─── Envoi de messages ────────────────────────────────────────────────────
    def _send_quick(self, question: str):
        self.edt_question.setText(question)
        self._send()

    def _send(self):
        question = self.edt_question.text().strip()
        if not question:
            return

        # Construire le contexte : auto-RAG ou manuel
        if self._chk_autocontext.isChecked() and self._params_map:
            context = build_rag_context(
                self._params_map, self._cleaned_map, self._parsed_files,
                current_essai=self._current_essai,
            )
        else:
            context = self.edt_context.toPlainText().strip()

        self._conv_context = context
        max_toks = self.spn_tokens.value()
        self._msg_count += 1

        # Sauvegarder dans l'historique pour l'export PDF
        self._conversation.append({
            "role": "user",
            "text": question,
            "timestamp": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "context_snapshot": context,
            "essai": self._current_essai or "",
        })

        self._append_user(question)
        self.edt_question.clear()
        self.btn_send.setEnabled(False)
        self.btn_send.setText("…")
        self.lbl_thinking.setText("⏳ KIBALI analyse vos données…")

        from frontend.api_client import ApiClient
        client = ApiClient()

        def do_ask():
            return client.ask_kibali(question=question, context=context,
                                     max_new_tokens=max_toks)

        w = KibaliWorker(do_ask)
        w.done.connect(self._on_answer)
        w.error.connect(self._on_kibali_error)
        self._worker = w
        w.start()

    def _on_answer(self, answer: str):
        self.lbl_thinking.setText("")
        # Sauvegarder la réponse KIBALI
        self._conversation.append({
            "role": "kibali",
            "text": answer,
            "timestamp": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        })
        self._append_kibali(answer)
        self.btn_send.setEnabled(True)
        self.btn_send.setText("Envoyer ▶")

    def _on_kibali_error(self, err: str):
        self.lbl_thinking.setText("")
        self._append_error(err)
        self.btn_send.setEnabled(True)
        self.btn_send.setText("Envoyer ▶")

    # ─── Affichage HTML du chat ───────────────────────────────────────────────
    def _show_welcome(self):
        self.txt_history.setHtml("""
<div style="color:#1e3352; font-size:14pt; font-weight:bold; padding:20px 0 8px 0;">
  🤖 KIBALI — Expert Géotechnique IA
</div>
<div style="color:#475569; font-size:9pt; line-height:1.6;">
  Je suis KIBALI, spécialiste des essais pressiométriques Ménard (NF P 94-110).<br>
  <br>
  <b style="color:#38bdf8;">Avec accès aux données réelles :</b><br>
  • J'analyse vos courbes P-V, modules Em, pressions Pl/Pf<br>
  • Je détecte les anomalies et incohérences réelles<br>
  • Je calcule capacité portante et tassements<br>
  • Je recommande fondations selon vos paramètres réels<br>
  <br>
  <span style="color:#ffd166;">→ Chargez et analysez un fichier, puis utilisez les boutons ou posez votre question.</span>
</div>
<hr style="border:none; border-top:1px solid #1e2d3d; margin:12px 0;">
""")

    def _append_user(self, text: str):
        safe_text = _html.escape(text).replace("\n", "<br>")
        self.txt_history.append(
            f'<div style="margin:8px 0 4px 0;">'
            f'<span style="color:#38bdf8; font-weight:bold;">Vous :</span>&nbsp;'
            f'<span style="color:#e2e8f0;">{safe_text}</span>'
            f'</div>'
        )
        self._scroll_to_bottom()

    def _append_kibali(self, text: str):
        # Formate les sections en gras (lignes commençant par ##)
        lines = []
        for line in text.split("\n"):
            line_esc = _html.escape(line)
            if line_esc.startswith("##"):
                lines.append(f'<b style="color:#ffd166;">{line_esc[2:].strip()}</b>')
            elif line_esc.startswith("•") or line_esc.startswith("-"):
                lines.append(f'<span style="color:#94a3b8;">{line_esc}</span>')
            elif ":" in line_esc and len(line_esc) < 80:
                # Ligne clé:valeur — colorer la clé
                idx = line_esc.index(":")
                key = line_esc[:idx]
                val = line_esc[idx:]
                lines.append(
                    f'<span style="color:#06d6a0;">{key}</span>'
                    f'<span style="color:#e2e8f0;">{val}</span>'
                )
            else:
                lines.append(f'<span style="color:#e2e8f0;">{line_esc}</span>')
        body = "<br>".join(lines)
        self.txt_history.append(
            f'<div style="margin:4px 0 10px 0; padding:10px 14px;"'
            f' style="background:#030a0a;">'
            f'<div style="color:#06d6a0; font-weight:bold; margin-bottom:6px;">'
            f'🤖 KIBALI :</div>'
            f'<div style="line-height:1.65;">{body}</div>'
            f'</div>'
            f'<hr style="border:none; border-top:1px solid #0d1a2e; margin:4px 0;">'
        )
        self._scroll_to_bottom()

    def _append_error(self, err: str):
        safe = _html.escape(err)
        self.txt_history.append(
            f'<div style="color:#ef476f; margin:6px 0; padding:8px; '
            f'border:1px solid #7f1d1d; border-radius:4px;">'
            f'⚠ Erreur KIBALI : {safe}</div>'
        )
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        cursor = self.txt_history.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.txt_history.setTextCursor(cursor)
        self.txt_history.ensureCursorVisible()

    def _clear_history(self):
        self.txt_history.clear()
        self._msg_count = 0
        self._conversation = []
        self._conv_context = ""
        self._show_welcome()

    # ─── Export PDF conversation ──────────────────────────────────────────────
    def _export_chat_pdf(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        if not self._conversation:
            QMessageBox.information(
                self, "Export PDF",
                "Aucune conversation à exporter.\n"
                "Discutez d'abord avec KIBALI, puis exportez."
            )
            return

        default_name = f"kibali_session_{datetime.date.today().strftime('%Y%m%d_%H%M')}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter conversation KIBALI", default_name, "PDF (*.pdf)"
        )
        if not path:
            return

        self.btn_export_pdf.setEnabled(False)
        self.btn_export_pdf.setText("⏳ Génération…")

        conv_snapshot = list(self._conversation)
        params_snapshot = dict(self._params_map)
        cleaned_snapshot = dict(self._cleaned_map)
        essai_snapshot = self._current_essai

        def do_export():
            from api.report_chat import build_chat_report
            return build_chat_report(
                conversation=conv_snapshot,
                params_map=params_snapshot,
                cleaned_map=cleaned_snapshot,
                current_essai=essai_snapshot,
            )

        w = PdfWorker(do_export)

        def _on_pdf_done(result):
            try:
                with open(path, "wb") as f:
                    f.write(result)
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self, "Export réussi",
                    f"Conversation exportée avec succès :\n{path}"
                )
            except Exception as exc:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Erreur sauvegarde", str(exc))
            finally:
                self.btn_export_pdf.setEnabled(True)
                self.btn_export_pdf.setText("📄 Exporter PDF")

        def _on_pdf_error(err: str):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Erreur PDF", f"Génération échouée :\n{err}")
            self.btn_export_pdf.setEnabled(True)
            self.btn_export_pdf.setText("📄 Exporter PDF")

        w.done.connect(_on_pdf_done)
        w.error.connect(_on_pdf_error)
        self._export_worker: Optional[PdfWorker] = w
        w.start()

    # ─── Statut KIBALI ────────────────────────────────────────────────────────
    def _check_status(self):
        from frontend.api_client import ApiClient
        try:
            info = ApiClient().kibali_status()
            if info.get("ready"):
                self.lbl_status.setText("KIBALI : ✅ Prêt (NF4 4-bit)")
                self.lbl_status.setStyleSheet("color:#06d6a0; font-size:11px; font-weight:bold;")
            elif info.get("error"):
                self.lbl_status.setText(f"KIBALI : ❌ {info['error'][:50]}")
                self.lbl_status.setStyleSheet("color:#ef476f; font-size:11px; font-weight:bold;")
            else:
                self.lbl_status.setText("KIBALI : ⏳ Chargement en cours…")
                self.lbl_status.setStyleSheet("color:#ffd166; font-size:11px; font-weight:bold;")
        except Exception as e:
            self.lbl_status.setText(f"KIBALI : ⚠ API hors ligne")
