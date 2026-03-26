"""
api/report_chat.py — Export PDF de la conversation KIBALI (SETRAF GABON)
Génère un rapport PDF professionnel de la session de chat avec KIBALI,
incluant les données pressiométriques analysées et le contexte RAG injecté.
"""
from __future__ import annotations
import io
import datetime
from typing import List, Optional, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)

# ── Import helpers & palette depuis le module report principal ──────────────
from .report import (
    _styles, _tbl_style, _hr, _section_heading, _setraf_header, _logo_img,
    C_NAVY, C_SKY, C_GOLD, C_WHITE, C_LGRAY, C_MGRAY,
    C_DGRAY, C_GREEN, C_RED, C_AMBER, C_ORANGE,
    C_ROW0, C_ROW1, C_HEADER, C_BORDER,
    PAGE_W, PAGE_H, MARGIN_H, MARGIN_V,
)

# Couleurs spécifiques au chat
C_USER_BG   = colors.HexColor("#0a1e3a")   # bulle utilisateur — bleu marine
C_KIBALI_BG = colors.HexColor("#041a10")   # bulle KIBALI — vert très sombre
C_USER_BAR  = colors.HexColor("#38bdf8")   # barre latérale bleu ciel
C_KIBALI_BAR = colors.HexColor("#06d6a0")  # barre latérale vert néon


def _chat_styles() -> dict:
    """Styles supplémentaires pour les bulles de conversation."""
    S = _styles()
    return {
        "user_label": ParagraphStyle(
            "user_label",
            fontName="Helvetica-Bold", fontSize=8,
            textColor=C_USER_BAR, spaceAfter=2, leading=10,
        ),
        "kibali_label": ParagraphStyle(
            "kibali_label",
            fontName="Helvetica-Bold", fontSize=8,
            textColor=C_KIBALI_BAR, spaceAfter=2, leading=10,
        ),
        "user_msg": ParagraphStyle(
            "user_msg",
            fontName="Helvetica", fontSize=9,
            textColor=C_LGRAY, spaceAfter=0, leading=13,
        ),
        "kibali_msg": ParagraphStyle(
            "kibali_msg",
            fontName="Helvetica", fontSize=9,
            textColor=C_LGRAY, spaceAfter=0, leading=13,
        ),
        "timestamp": ParagraphStyle(
            "ts",
            fontName="Helvetica-Oblique", fontSize=7,
            textColor=C_MGRAY, spaceAfter=1, leading=9,
        ),
        "raw_ctx": ParagraphStyle(
            "raw_ctx",
            fontName="Courier", fontSize=6.5,
            textColor=colors.HexColor("#7aabb5"),
            spaceAfter=0, leading=9, leftIndent=4,
        ),
        "meta_key": ParagraphStyle(
            "meta_key",
            fontName="Helvetica-Bold", fontSize=8.5,
            textColor=C_SKY, alignment=TA_LEFT,
        ),
        "meta_val": ParagraphStyle(
            "meta_val",
            fontName="Helvetica", fontSize=8.5,
            textColor=C_LGRAY, alignment=TA_LEFT,
        ),
    }


def _safe(text: str) -> str:
    """Échappe HTML pour ReportLab Paragraph."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _kibali_html(text: str) -> str:
    """
    Formate le texte KIBALI pour ReportLab : sections ## → gras doré,
    listes • → gris, clé:valeur courte → clé colorée.
    """
    lines_out = []
    for line in text.split("\n"):
        safe_line = _safe(line)
        if safe_line.startswith("##"):
            lines_out.append(
                f'<b><font color="#ffd166">{safe_line[2:].strip()}</font></b>'
            )
        elif safe_line.startswith("•") or safe_line.startswith("-"):
            lines_out.append(f'<font color="#94a3b8">  {safe_line}</font>')
        elif ":" in safe_line and len(safe_line) < 100:
            idx = safe_line.index(":")
            key = safe_line[:idx]
            val = safe_line[idx:]
            lines_out.append(
                f'<font color="#06d6a0"><b>{key}</b></font>'
                f'<font color="#e2e8f0">{val}</font>'
            )
        else:
            lines_out.append(f'<font color="#e2e8f0">{safe_line}</font>' if safe_line else " ")
    return "<br/>".join(lines_out)


def _msg_bubble(text: str, style, bar_color, bg_color) -> KeepTogether:
    """Encapsule un message dans une bulle stylisée avec barre latérale colorée."""
    inner_w = PAGE_W - 2 * MARGIN_H
    bubble = Table(
        [[Paragraph(text, style)]],
        colWidths=[inner_w],
    )
    bubble.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg_color),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("LINEBEFORE",    (0, 0), (0, -1), 3.5, bar_color),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, C_BORDER),
    ]))
    return KeepTogether([bubble])


def build_chat_report(
    conversation: list,
    params_map: dict,
    cleaned_map: dict,
    current_essai: Optional[str] = None,
) -> bytes:
    """
    Génère un PDF de session KIBALI (transcrition complète + données).

    Args:
        conversation: liste de dicts {role, text, timestamp, context_snapshot?, essai?}
        params_map:   dict {nom_essai: PressiometricParams}
        cleaned_map:  dict {nom_essai: CleanedEssai}
        current_essai: nom de l'essai actif au moment de l'export
    Returns:
        bytes du PDF généré
    """
    today    = datetime.date.today()
    now      = datetime.datetime.now()
    date_str = today.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")
    ref      = f"KIBALI-{today.strftime('%Y%m%d')}-{now.strftime('%H%M')}"

    S  = _styles()
    CS = _chat_styles()

    n_user   = sum(1 for m in conversation if m.get("role") == "user")
    n_kibali = sum(1 for m in conversation if m.get("role") == "kibali")
    essais_mentionnes = sorted({
        m.get("essai", "")
        for m in conversation
        if m.get("role") == "user" and m.get("essai")
    })
    durée_str = ""
    if conversation:
        try:
            fmt = "%d/%m/%Y %H:%M:%S"
            t0 = datetime.datetime.strptime(conversation[0]["timestamp"], fmt)
            t1 = datetime.datetime.strptime(conversation[-1]["timestamp"], fmt)
            delta = int((t1 - t0).total_seconds())
            mn, sc = divmod(delta, 60)
            durée_str = f"{mn} min {sc} s" if mn else f"{sc} s"
        except Exception:
            pass

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=MARGIN_H, leftMargin=MARGIN_H,
        topMargin=MARGIN_V,   bottomMargin=MARGIN_V,
        title="Rapport conversation KIBALI — SETRAF GABON",
        author="KIBALI IA Géotechnique",
        subject="Session d'analyse pressiométrique assistée par IA",
    )
    story = []

    # ══════════════════════════════════════════════════════════════
    # PAGE DE GARDE
    # ══════════════════════════════════════════════════════════════
    # Logo SETRAF GABON centré en haut
    logo_obj = _logo_img(height_cm=3.0, max_width_cm=9.0)
    if logo_obj:
        logo_obj.hAlign = "CENTER"
        story.append(Spacer(1, 0.6 * cm))
        story.append(logo_obj)
        story.append(Spacer(1, 0.35 * cm))
        story.append(_hr(C_ORANGE, 2))
        story.append(Spacer(1, 0.3 * cm))
    story.append(_setraf_header(ref, date_str))
    story.append(Spacer(1, 1.2 * cm))

    story.append(Paragraph("RAPPORT DE SESSION IA KIBALI", S["cover_title"]))
    story.append(Paragraph(
        "Transcription & Analyse — Assistant Expert Pressiométrique",
        S["cover_sub"]
    ))
    story.append(Spacer(1, 0.3 * cm))
    story.append(_hr(C_GREEN, 2))
    story.append(Spacer(1, 0.5 * cm))

    # Tableau méta-session
    meta_rows = [
        ["Date de session",        date_str],
        ["Heure de génération",    time_str],
        ["Durée conversation",     durée_str or "—"],
        ["Messages utilisateur",   str(n_user)],
        ["Réponses KIBALI",        str(n_kibali)],
        ["Essai(s) discuté(s)",    ", ".join(essais_mentionnes) or "Synthèse générale"],
        ["Essais en mémoire",      f"{len(params_map)} essai(s)"],
        ["Essai actif à l'export", current_essai or "—"],
    ]
    inner_w = PAGE_W - 2 * MARGIN_H
    meta_tbl = Table(
        [
            [Paragraph(k, CS["meta_key"]), Paragraph(v, CS["meta_val"])]
            for k, v in meta_rows
        ],
        colWidths=[5 * cm, inner_w - 5 * cm],
    )
    meta_tbl.setStyle(_tbl_style())
    story.append(meta_tbl)

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "Ce document constitue la transcription officielle de la session d'analyse "
        "géotechnique assistée par KIBALI. Il inclut les données pressiométriques "
        "fournies à l'IA, l'intégralité de la conversation et le contexte RAG injecté.",
        S["body"]
    ))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # SECTION 1 — Données pressiométriques utilisées
    # ══════════════════════════════════════════════════════════════
    _section_heading(
        story, "1",
        "Données pressiométriques analysées",
        "Paramètres disponibles en mémoire lors de la session KIBALI",
    )

    if params_map:
        q_colors = {
            "A": colors.HexColor("#22c55e"),
            "B": colors.HexColor("#fbbf24"),
            "C": colors.HexColor("#f97316"),
            "D": colors.HexColor("#ef4444"),
        }

        hdr = [
            Paragraph(h, S["table_hdr"])
            for h in ["Essai", "Prof. m", "Em MPa", "Pl MPa", "Pf MPa",
                       "Em/Pl", "NC/SC", "Qual.", "Type de sol"]
        ]
        rows = [hdr]
        params_items = list(params_map.items())[:60]
        for name, p in params_items:
            rows.append([
                Paragraph(name, S["table_cell"]),
                Paragraph(str(p.depth_m or "—"), S["table_cell"]),
                Paragraph(f"{p.Em_MPa:.2f}"    if p.Em_MPa    else "—", S["table_cell"]),
                Paragraph(f"{p.Pl_MPa:.3f}"    if p.Pl_MPa    else "—", S["table_cell"]),
                Paragraph(f"{p.Pf_MPa:.3f}"    if p.Pf_MPa    else "—", S["table_cell"]),
                Paragraph(f"{p.ratio_Em_Pl:.1f}" if p.ratio_Em_Pl else "—", S["table_cell"]),
                Paragraph(p.nc_status or "—",  S["table_cell"]),
                Paragraph(p.qualite   or "—",  S["table_cell"]),
                Paragraph((p.sol_type or "—")[:22], S["table_cell"]),
            ])

        col_w = [3.2*cm, 1.5*cm, 2*cm, 2*cm, 2*cm, 1.5*cm, 1.5*cm, 1.3*cm,
                 inner_w - (3.2+1.5+2+2+2+1.5+1.5+1.3)*cm]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        ts_tab = _tbl_style()
        for i, (_, p) in enumerate(params_items, start=1):
            if p.qualite in q_colors:
                ts_tab.add("BACKGROUND", (7, i), (7, i), q_colors[p.qualite])
                ts_tab.add("TEXTCOLOR",  (7, i), (7, i), colors.white)
            if p.nc_status == "NC":
                ts_tab.add("TEXTCOLOR", (5, i), (5, i), C_AMBER)
            elif p.nc_status == "SC":
                ts_tab.add("TEXTCOLOR", (5, i), (5, i), C_SKY)
        t.setStyle(ts_tab)
        story.append(t)

        # Statistiques rapides
        em_vals = [p.Em_MPa for p in params_map.values() if p.Em_MPa]
        pl_vals = [p.Pl_MPa for p in params_map.values() if p.Pl_MPa]
        story.append(Spacer(1, 0.3 * cm))
        if em_vals:
            story.append(Paragraph(
                f"Em : min <b>{min(em_vals):.2f}</b> MPa | "
                f"max <b>{max(em_vals):.2f}</b> MPa | "
                f"moyenne <b>{sum(em_vals)/len(em_vals):.2f}</b> MPa",
                S["body_b"]
            ))
        if pl_vals:
            story.append(Paragraph(
                f"Pl : min <b>{min(pl_vals):.3f}</b> MPa | "
                f"max <b>{max(pl_vals):.3f}</b> MPa | "
                f"moyenne <b>{sum(pl_vals)/len(pl_vals):.3f}</b> MPa",
                S["body_b"]
            ))
    else:
        story.append(Paragraph(
            "Aucun essai pressiométrique en mémoire lors de cette session.",
            S["warn"]
        ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # SECTION 2 — Transcription de la conversation
    # ══════════════════════════════════════════════════════════════
    _section_heading(
        story, "2",
        "Transcription de la conversation KIBALI",
        f"Session du {date_str} à {time_str} — {n_user} questions / {n_kibali} réponses",
    )

    if not conversation:
        story.append(Paragraph("Aucun message enregistré.", S["warn"]))
    else:
        for idx, msg in enumerate(conversation):
            role = msg.get("role", "")
            text = msg.get("text", "")
            ts   = msg.get("timestamp", "")
            essai = msg.get("essai", "")

            if role == "user":
                label = f"👤  Vous   —   {ts}"
                if essai:
                    label += f"   |   Essai : {essai}"
                story.append(Spacer(1, 0.25 * cm))
                story.append(Paragraph(label, CS["timestamp"]))
                story.append(_msg_bubble(
                    _safe(text), CS["user_msg"], C_USER_BAR, C_USER_BG
                ))

            elif role == "kibali":
                label = f"🤖  KIBALI   —   {ts}"
                story.append(Spacer(1, 0.2 * cm))
                story.append(Paragraph(label, CS["timestamp"]))
                story.append(_msg_bubble(
                    _kibali_html(text), CS["kibali_msg"], C_KIBALI_BAR, C_KIBALI_BG
                ))
                # Séparateur discret entre échanges
                if idx < len(conversation) - 1:
                    story.append(Spacer(1, 0.1 * cm))
                    story.append(_hr(C_BORDER, 0.4))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # SECTION 3 — Contexte RAG injecté (dernier snapshot)
    # ══════════════════════════════════════════════════════════════
    last_context = ""
    for msg in reversed(conversation):
        if msg.get("role") == "user" and msg.get("context_snapshot"):
            last_context = msg["context_snapshot"]
            break

    if last_context:
        _section_heading(
            story, "3",
            "Contexte RAG injecté (données réelles)",
            "Données pressiométriques fournies à KIBALI lors du dernier message",
        )
        story.append(Paragraph(
            "Ce bloc reproduit le contexte textuel exact que KIBALI a reçu avec la "
            "dernière question. Il contient les paramètres réels extraits des fichiers Excel.",
            S["body"]
        ))
        story.append(Spacer(1, 0.2 * cm))

        # Afficher par blocs de 60 lignes pour éviter un Paragraph géant
        ctx_lines = last_context.split("\n")
        chunk_size = 60
        for i in range(0, len(ctx_lines), chunk_size):
            chunk = ctx_lines[i : i + chunk_size]
            safe_chunk = "<br/>".join(
                _safe(line) if line.strip() else "&nbsp;"
                for line in chunk
            )
            story.append(Paragraph(safe_chunk, CS["raw_ctx"]))

    # ══════════════════════════════════════════════════════════════
    # Pied de rapport
    # ══════════════════════════════════════════════════════════════
    story.append(Spacer(1, 0.5 * cm))
    story.append(_hr(C_ORANGE, 1.5))
    story.append(Paragraph(
        f"Rapport généré automatiquement par SETRAF GABON — KIBALI IA — "
        f"{date_str} à {time_str}   |   NF P 94-110 / Eurocode 7",
        S["ref"]
    ))

    doc.build(story)
    return buf.getvalue()
