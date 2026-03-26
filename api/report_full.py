"""
api/report_full.py — Rapport complet SETRAF GABON (~30 pages)
=============================================================
Contenu :
  Page de garde enrichie
  Table des matières
  Section 1  — Synthèse générale (tableau récapitulatif tous SP)
  Section 2  — Fiche détaillée par SP :
                  métadonnées · tableau données brutes + corrigées ·
                  anomalies/erreurs colorées · paramètres Ménard · courbe P-V
  Section 3  — Tableau de synthèse qualité (A/B/C/D) + statistiques
  Section 4  — Conversation complète KIBALI (bulles colorées)
  Section 5  — Conclusions et recommandations
"""
from __future__ import annotations

import io
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether,
)

# ── Import helpers partagés depuis report.py ─────────────────────────────────
from .report import (
    _styles, _tbl_style, _hr, _section_heading, _setraf_header,
    _fig_to_image, _draw_curve_pv, _logo_img,
    C_NAVY, C_BLUE, C_SKY, C_GOLD, C_WHITE, C_LGRAY, C_MGRAY,
    C_DGRAY, C_GREEN, C_RED, C_AMBER, C_ORANGE,
    C_ROW0, C_ROW1, C_HEADER, C_BORDER,
    PAGE_W, PAGE_H, MARGIN_H, MARGIN_V,
)
from .models import CleanedEssai, PressiometricParams, ParsedFile
from .norms import SOIL_NORMS_TABLE, NC_SC_TABLE, QUALITY_GRADES, MENARD_FORMULAS

# ── Palette étendue ───────────────────────────────────────────────────────────
C_ERR_BG    = colors.HexColor("#2d0a0a")
C_ERR_TXT   = colors.HexColor("#f87171")
C_WARN_BG   = colors.HexColor("#2a1700")
C_WARN_TXT  = colors.HexColor("#fbbf24")
C_OK_BG     = colors.HexColor("#071a0e")
C_OK_TXT    = colors.HexColor("#4ade80")
C_USER_BG   = colors.HexColor("#0a1e3a")
C_KIBALI_BG = colors.HexColor("#041a10")
C_USER_BAR  = colors.HexColor("#38bdf8")
C_KIBALI_BAR= colors.HexColor("#06d6a0")

_QUAL_COLOR = {"A": C_GREEN, "B": C_SKY, "C": C_AMBER, "D": C_RED, "?": C_MGRAY}


# ─── Styles supplémentaires ───────────────────────────────────────────────────
def _extra_styles() -> dict:
    S = _styles()
    def P(name, **kw):
        return ParagraphStyle(name, **kw)
    return {
        "sp_title": P("sp_title",
            fontName="Helvetica-Bold", fontSize=11,
            textColor=C_SKY, spaceBefore=6, spaceAfter=3, leading=14),
        "sp_sub": P("sp_sub",
            fontName="Helvetica-Bold", fontSize=9,
            textColor=C_GOLD, spaceBefore=4, spaceAfter=2, leading=12),
        "err_cell": P("err_cell",
            fontName="Helvetica-Bold", fontSize=7.5,
            textColor=C_ERR_TXT, leading=10),
        "warn_cell": P("warn_cell",
            fontName="Helvetica-BoldOblique", fontSize=7.5,
            textColor=C_WARN_TXT, leading=10),
        "ok_cell": P("ok_cell",
            fontName="Helvetica", fontSize=7.5,
            textColor=C_OK_TXT, leading=10),
        "user_label": P("user_label",
            fontName="Helvetica-Bold", fontSize=8,
            textColor=C_USER_BAR, spaceAfter=2, leading=10),
        "kibali_label": P("kibali_label",
            fontName="Helvetica-Bold", fontSize=8,
            textColor=C_KIBALI_BAR, spaceAfter=2, leading=10),
        "msg": P("msg",
            fontName="Helvetica", fontSize=8.5,
            textColor=C_LGRAY, leading=13, spaceAfter=0),
        "ts": P("ts",
            fontName="Helvetica-Oblique", fontSize=7,
            textColor=C_MGRAY, spaceAfter=1, leading=9),
        "toc_ch": P("toc_ch",
            fontName="Helvetica-Bold", fontSize=10,
            textColor=C_SKY, spaceBefore=6, spaceAfter=2, leading=13),
        "toc_sub": P("toc_sub",
            fontName="Helvetica", fontSize=9,
            textColor=C_LGRAY, spaceAfter=2, leftIndent=16, leading=12),
        "summary_title": P("summary_title",
            fontName="Helvetica-Bold", fontSize=13,
            textColor=C_SKY, alignment=TA_CENTER,
            spaceBefore=12, spaceAfter=4, leading=16),
        "stat_val": P("stat_val",
            fontName="Helvetica-Bold", fontSize=11,
            textColor=C_GOLD, alignment=TA_CENTER, leading=14),
        "stat_lbl": P("stat_lbl",
            fontName="Helvetica", fontSize=8,
            textColor=C_MGRAY, alignment=TA_CENTER, leading=10),
        # ── Styles section courbes P-V ─────────────────────────────────────
        "pv_interp": P("pv_interp",
            fontName="Helvetica", fontSize=8.5,
            textColor=C_LGRAY, leading=13, spaceAfter=4,
            firstLineIndent=0, alignment=TA_JUSTIFY),
        "pv_norm_ref": P("pv_norm_ref",
            fontName="Helvetica-Oblique", fontSize=7.2,
            textColor=C_MGRAY, leading=10, leftIndent=8, spaceAfter=3),
        "pv_section_box": P("pv_section_box",
            fontName="Helvetica-Bold", fontSize=9,
            textColor=C_SKY, leading=12, spaceBefore=8, spaceAfter=2),
        "pv_highlight": P("pv_highlight",
            fontName="Helvetica-Bold", fontSize=8.5,
            textColor=C_GOLD, leading=12, spaceAfter=2),
    }


def _safe(t: str) -> str:
    return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


def _fmt(v, decimals=3, unit="") -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{decimals}f}{(' ' + unit) if unit else ''}"
    except Exception:
        return str(v)


# ─── Page de garde ────────────────────────────────────────────────────────────
def _cover_page(story: list, meta: dict, n_sp: int, now: datetime.datetime):
    S = _styles()
    ES = _extra_styles()

    story.append(Spacer(1, 0.8*cm))

    # ── Logo SETRAF centré en haut de la page de garde ────────────────────
    logo_obj = _logo_img(height_cm=3.2, max_width_cm=9.0)
    if logo_obj:
        logo_obj.hAlign = "CENTER"
        story.append(logo_obj)
        story.append(Spacer(1, 0.4*cm))
        story.append(_hr(C_ORANGE, 2.5))
        story.append(Spacer(1, 0.35*cm))
    else:
        # Texte de secours si le fichier logo est absent
        story.append(Paragraph("SETRAF GABON", S["cover_company"]))
        story.append(Paragraph("Société d'Études Techniques et de Réalisation en Afrique",
                                S["cover_sub"]))
        story.append(_hr(C_ORANGE, 2.5))
        story.append(Spacer(1, 0.35*cm))

    # Titre
    title = meta.get("title") or "RAPPORT COMPLET DE RECONNAISSANCE GÉOTECHNIQUE"
    story.append(Paragraph(title.upper(), S["cover_title"]))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Données pressiométriques · Analyses NF P 94-110 · Synthèse IA KIBALI",
        S["cover_subtitle"]))
    story.append(Spacer(1, 0.8*cm))
    story.append(_hr(C_SKY, 1.2))
    story.append(Spacer(1, 0.5*cm))

    # Bloc méta (table 2 colonnes)
    loc   = meta.get("location", "Port-Gentil, En face du Stade PERENCO, Gabon")
    eng   = meta.get("engineer", "")
    ref   = meta.get("ref", f"SETRAF-{now.strftime('%Y%m%d')}-FULL")
    rows = [
        ["Localisation :", loc,          "Nb. de SP :",       str(n_sp)],
        ["Ingénieur :",    eng or "—",   "Date :",            now.strftime("%d/%m/%Y")],
        ["Référence :",    ref,          "Norme principale :", "NF P 94-110"],
        ["Confidentiel :", "SETRAF GABON","Logiciel :",        "PressiomètreIA v2"],
    ]
    col_w = [(PAGE_W - 2*MARGIN_H) / 4] * 4
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ("TEXTCOLOR",    (0,0), (0,-1), C_SKY),
        ("TEXTCOLOR",    (2,0), (2,-1), C_SKY),
        ("TEXTCOLOR",    (1,0), (1,-1), C_LGRAY),
        ("TEXTCOLOR",    (3,0), (3,-1), C_LGRAY),
        ("FONTNAME",     (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",     (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTNAME",     (1,0), (1,-1), "Helvetica"),
        ("FONTNAME",     (3,0), (3,-1), "Helvetica"),
        ("FONTSIZE",     (0,0), (-1,-1), 8.5),
        ("BACKGROUND",   (0,0), (-1,-1), colors.HexColor("#080c14")),
        ("GRID",         (0,0), (-1,-1), 0.4, C_BORDER),
        ("PADDING",      (0,0), (-1,-1), 5),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.8*cm))

    # Normes de référence
    norms = ["NF P 94-110", "Eurocode 7 (EN 1997-1)", "ISO 22476-4",
             "ASTM D4719", "DTU 13.12"]
    story.append(Paragraph(
        "Normes de référence : " + "  ·  ".join(norms),
        S["cover_norm"]))
    story.append(Spacer(1, 0.4*cm))
    story.append(_hr(C_ORANGE, 2.5))
    story.append(PageBreak())


# ─── Table des matières ───────────────────────────────────────────────────────
def _toc(story: list, sp_names: list[str]):
    S  = _styles()
    ES = _extra_styles()

    _section_heading(story, "0.", "Table des Matières")
    story.append(Spacer(1, 0.3*cm))

    chapters = [
        ("1.", "Synthèse générale — tableau récapitulatif", []),
        ("2.", f"Fiches détaillées par sondage pressiométrique ({len(sp_names)} SP)",
         [f"  SP : {n}" for n in sp_names]),
        ("3.", f"Atlas des courbes P-V — analyse normative ({len(sp_names)} SP)",
         [f"  Courbe P-V : {n}" for n in sp_names]),
        ("4.", "Synthèse qualité & statistiques", []),
        ("5.", "Conversation complète KIBALI — IA géotechnique", []),
        ("6.", "Conclusions et recommandations", []),
    ]
    for num, title, subs in chapters:
        story.append(Paragraph(f"{num}  {title}", ES["toc_ch"]))
        for s in subs:
            story.append(Paragraph(_safe(s), ES["toc_sub"]))
    story.append(PageBreak())


# ─── Section 1 : Tableau récapitulatif ───────────────────────────────────────
def _section_summary(
    story: list,
    cleaned_map: Dict[str, CleanedEssai],
    params_map:  Dict[str, PressiometricParams],
):
    S = _styles()
    _section_heading(story, "1.", "Synthèse Générale des Résultats")
    story.append(Paragraph(
        "Le tableau suivant regroupe les paramètres pressiométriques clés de chaque "
        "sondage (SP) analysé, conformément à la norme NF P 94-110. "
        "Les cellules en rouge indiquent une anomalie critique ; en orange, une alerte.",
        S["body"]))
    story.append(Spacer(1, 0.3*cm))

    headers = ["SP / Essai", "Prof. (m)", "Em (MPa)", "Pf (MPa)", "Pl (MPa)",
               "Em/Pl", "Qualité", "Anomalies", "Cohérence"]
    rows = [headers]

    for name in sorted(params_map.keys()):
        p  = params_map[name]
        cl = cleaned_map.get(name)
        n_anom  = len(cl.anomalies) if cl else p.n_anomalies
        n_err   = sum(1 for a in cl.anomalies if a.severity == "error") if cl else 0
        n_warn  = n_anom - n_err
        qual    = p.qualite or "?"
        coh     = "✓" if p.is_coherent else "✗"

        anom_str = []
        if n_err:   anom_str.append(f"{n_err} err.")
        if n_warn:  anom_str.append(f"{n_warn} alerte(s)")
        if not n_anom: anom_str.append("Aucune")

        rows.append([
            name[:28],
            _fmt(p.depth_m, 1),
            _fmt(p.Em_MPa, 2),
            _fmt(p.Pf_MPa, 3),
            _fmt(p.Pl_MPa, 3),
            _fmt(p.ratio_Em_Pl, 1),
            qual,
            " / ".join(anom_str),
            coh,
        ])

    cw = [3.5*cm, 1.5*cm, 2*cm, 2*cm, 2*cm, 1.5*cm, 1.5*cm, 3.2*cm, 1.8*cm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    ts = _tbl_style(header_rows=1)
    # Colorer qualité + cohérence
    for i, (name, row) in enumerate(zip([""] + list(params_map.keys()), rows)):
        if i == 0:
            continue
        p = params_map.get(name)
        if not p:
            continue
        qual = p.qualite or "?"
        qc   = _QUAL_COLOR.get(qual, C_MGRAY)
        coh_ok = p.is_coherent
        # Qualité (col 6)
        ts.add("TEXTCOLOR",  (6, i), (6, i), qc)
        ts.add("FONTNAME",   (6, i), (6, i), "Helvetica-Bold")
        # Cohérence (col 8)
        ts.add("TEXTCOLOR",  (8, i), (8, i), C_GREEN if coh_ok else C_RED)
        # Anomalies (col 7)
        cl = cleaned_map.get(name)
        n_err = sum(1 for a in cl.anomalies if a.severity == "error") if cl else 0
        if n_err:
            ts.add("BACKGROUND", (7, i), (7, i), C_ERR_BG)
            ts.add("TEXTCOLOR",  (7, i), (7, i), C_ERR_TXT)
        elif cl and cl.anomalies:
            ts.add("BACKGROUND", (7, i), (7, i), C_WARN_BG)
            ts.add("TEXTCOLOR",  (7, i), (7, i), C_WARN_TXT)
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 0.5*cm))
    story.append(PageBreak())


# ─── Section 2 : Fiches SP ───────────────────────────────────────────────────
def _table_donnees(cleaned: CleanedEssai) -> Table:
    """
    Tableau complet des mesures : palier · P60_raw · P60_corr · V30_raw ·
    V60_raw · V60_corr · Creep abs · Creep ratio · Anomalie.
    Lignes en erreur/alerte colorées.
    """
    S = _styles()
    ES = _extra_styles()

    anom_by_palier: Dict[int, Any] = {a.palier: a for a in cleaned.anomalies}

    headers = [
        "Palier", "P60 brut\n(MPa)", "P60 corr\n(MPa)",
        "V30 brut\n(cm³)", "V60 brut\n(cm³)", "V60 corr\n(cm³)", "Vm corr\n(cm³)",
        "Creep\n(cm³)", "Ratio\nV60/V30", "Anomalie",
    ]
    rows = [headers]
    style_cmds = list(_tbl_style(header_rows=1).getCommands())

    for ridx, pt in enumerate(cleaned.points, start=1):
        anom = anom_by_palier.get(pt.palier)
        anom_text = f"{anom.type}: {anom.description[:30]}" if anom else "—"

        row = [
            str(pt.palier),
            _fmt(pt.P60_raw_MPa,  3),
            _fmt(pt.P60_corr_MPa, 3),
            _fmt(pt.V30_raw_cm3,  1),
            _fmt(pt.V60_raw_cm3,  1),
            _fmt(pt.V60_corr_cm3, 1),
            _fmt(pt.Vm_corr_cm3,  1),
            _fmt(pt.creep_abs_cm3,1),
            _fmt(pt.creep_ratio,  3),
            anom_text[:40],
        ]
        rows.append(row)

        if anom and anom.severity == "error":
            for col in range(len(headers)):
                style_cmds.append(("BACKGROUND", (col, ridx), (col, ridx), C_ERR_BG))
                style_cmds.append(("TEXTCOLOR",  (col, ridx), (col, ridx), C_ERR_TXT))
        elif anom and anom.severity == "warning":
            for col in range(len(headers)):
                style_cmds.append(("BACKGROUND", (col, ridx), (col, ridx), C_WARN_BG))
                style_cmds.append(("TEXTCOLOR",  (col, ridx), (col, ridx), C_WARN_TXT))
        elif pt.anomalie:
            style_cmds.append(("BACKGROUND", (-1, ridx), (-1, ridx), C_WARN_BG))
            style_cmds.append(("TEXTCOLOR",  (-1, ridx), (-1, ridx), C_WARN_TXT))

    cw = [1.1*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.5*cm, 1.5*cm, 3.8*cm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle(style_cmds))
    return t


def _table_anomalies(cleaned: CleanedEssai) -> Optional[Table]:
    if not cleaned.anomalies:
        return None
    ES = _extra_styles()
    headers = ["Palier", "Type", "Sévérité", "Description"]
    rows = [headers]
    for a in cleaned.anomalies:
        rows.append([str(a.palier), a.type, a.severity.upper(), a.description[:80]])

    cw = [1.5*cm, 3*cm, 2.5*cm, (PAGE_W - 2*MARGIN_H - 7*cm)]
    t = Table(rows, colWidths=cw, repeatRows=1)
    ts = _tbl_style(header_rows=1)
    for i, a in enumerate(cleaned.anomalies, start=1):
        if a.severity == "error":
            ts.add("BACKGROUND", (0, i), (-1, i), C_ERR_BG)
            ts.add("TEXTCOLOR",  (0, i), (-1, i), C_ERR_TXT)
        else:
            ts.add("BACKGROUND", (0, i), (-1, i), C_WARN_BG)
            ts.add("TEXTCOLOR",  (0, i), (-1, i), C_WARN_TXT)
    t.setStyle(ts)
    return t


def _table_coherence(cleaned: CleanedEssai) -> Optional[Table]:
    checks = cleaned.coherence
    if not checks:
        return None
    headers = ["Vérification", "Résultat"]
    rows = [headers]
    for c in checks:
        rows.append(["✓" if c.ok else "✗", c.message[:100]])
    cw = [2.5*cm, PAGE_W - 2*MARGIN_H - 2.5*cm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    ts = _tbl_style(header_rows=1)
    for i, c in enumerate(checks, start=1):
        if c.ok:
            ts.add("TEXTCOLOR", (0, i), (0, i), C_GREEN)
        else:
            ts.add("TEXTCOLOR", (0, i), (0, i), C_RED)
            ts.add("BACKGROUND",(0, i), (-1, i), C_ERR_BG)
    t.setStyle(ts)
    return t


def _table_params(p: PressiometricParams) -> Table:
    S = _styles()
    rows = [
        ["Paramètre", "Valeur", "", "Paramètre", "Valeur"],
        ["Module Em (MPa)",      _fmt(p.Em_MPa, 2),  "",  "Sol détecté",     p.sol_type],
        ["Pression limite Pl",   _fmt(p.Pl_MPa, 3, "MPa"),  "",
         "Classification",       p.nc_status],
        ["Pression fluage Pf",   _fmt(p.Pf_MPa, 3, "MPa"),  "",
         "Qualité essai",        p.qualite],
        ["Pl* nette",            _fmt(p.Pl_star_MPa, 3, "MPa"), "",
         "N° paliers bruts",     str(p.n_paliers)],
        ["Ratio Em/Pl",          _fmt(p.ratio_Em_Pl, 1),  "",
         "N° anomalies",         str(p.n_anomalies)],
        ["Profondeur",           _fmt(p.depth_m, 2, "m"),  "",
         "Cohérence globale",    "✓ OK" if p.is_coherent else "✗ ÉCHEC"],
    ]
    cw = [4*cm, 3*cm, 0.4*cm, 4*cm, 3*cm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    ts = _tbl_style(header_rows=1)
    ts.add("SPAN",    (2, 0), (2, -1))       # colonne vide séparatrice
    ts.add("LINEAFTER", (1, 1), (1, -1), 0.5, C_BORDER)
    # Colorer la qualité
    qual_row = 4
    qc = _QUAL_COLOR.get(p.qualite or "?", C_MGRAY)
    ts.add("TEXTCOLOR",  (4, qual_row), (4, qual_row), qc)
    ts.add("FONTNAME",   (4, qual_row), (4, qual_row), "Helvetica-Bold")
    # Colorer cohérence
    coh_row = 7
    if not p.is_coherent:
        ts.add("TEXTCOLOR", (4, coh_row), (4, coh_row), C_RED)
    else:
        ts.add("TEXTCOLOR", (4, coh_row), (4, coh_row), C_GREEN)
    t.setStyle(ts)
    return t


def _sp_fiche(
    story: list,
    cleaned: CleanedEssai,
    params:  PressiometricParams,
    sp_index: int,
):
    S  = _styles()
    ES = _extra_styles()

    # ── Titre ──────────────────────────────────────────────────────────────
    _section_heading(
        story,
        f"2.{sp_index}",
        f"Fiche SP : {cleaned.sheet_name}  —  Prof. {_fmt(cleaned.depth_m, 2)} m"
    )

    # ── Métadonnées ────────────────────────────────────────────────────────
    story.append(Paragraph("Métadonnées de l'essai", ES["sp_sub"]))
    meta = cleaned.meta
    meta_rows = [
        ["Projet",           meta.projet or "—",       "Sondage", meta.ref_sondage or "—"],
        ["Localisation",     meta.localisation or "—", "Date",    meta.date or "—"],
        ["Ref essai",        meta.ref_essai or "—",    "Profondeur", _fmt(cleaned.depth_m, 2, "m")],
        ["Réf. sonde",       meta.ref_sonde or "—",    "Technique", meta.technique or "—"],
        ["Outil forage",     meta.outil_forage or "—", "ΔP diff.",  _fmt(meta.pression_diff_bar, 2, "bar")],
    ]
    cw = [3*cm, 5*cm, 3*cm, 5*cm]
    t = Table(meta_rows, colWidths=cw)
    t.setStyle(TableStyle([
        ("TEXTCOLOR",  (0,0), (0,-1), C_SKY),
        ("TEXTCOLOR",  (2,0), (2,-1), C_SKY),
        ("TEXTCOLOR",  (1,0), (1,-1), C_LGRAY),
        ("TEXTCOLOR",  (3,0), (3,-1), C_LGRAY),
        ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",   (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTNAME",   (1,0), (1,-1), "Helvetica"),
        ("FONTNAME",   (3,0), (3,-1), "Helvetica"),
        ("FONTSIZE",   (0,0), (-1,-1), 8),
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#080c14")),
        ("GRID",       (0,0), (-1,-1), 0.4, C_BORDER),
        ("PADDING",    (0,0), (-1,-1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.35*cm))

    # ── Paramètres Ménard ──────────────────────────────────────────────────
    story.append(Paragraph("Paramètres pressiométriques (NF P 94-110)", ES["sp_sub"]))
    story.append(_table_params(params))
    story.append(Spacer(1, 0.35*cm))

    # ── Notes de l'algorithme ──────────────────────────────────────────────
    if params.notes:
        for note in params.notes:
            story.append(Paragraph(f"⚠ {_safe(note)}", S["warn"]))
        story.append(Spacer(1, 0.2*cm))

    # ── Tableau données brutes + corrigées ─────────────────────────────────
    story.append(Paragraph("Tableau complet des mesures (données brutes & corrigées)", ES["sp_sub"]))
    story.append(Paragraph(
        "Lignes <font color='#f87171'>rouge</font> = erreur critique — "
        "lignes <font color='#fbbf24'>orange</font> = alerte — "
        "lignes claires = données valides.",
        S["small"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(_table_donnees(cleaned))
    story.append(Spacer(1, 0.35*cm))

    # ── Tableau anomalies ──────────────────────────────────────────────────
    n_anom = len(cleaned.anomalies)
    story.append(Paragraph("Anomalies détectées", ES["sp_sub"]))
    if n_anom == 0:
        story.append(Paragraph(
            "✅ Aucune anomalie détectée sur cet essai.", S["good"]))
    else:
        n_err  = sum(1 for a in cleaned.anomalies if a.severity == "error")
        n_warn = n_anom - n_err
        summary_txt = []
        if n_err:  summary_txt.append(f"<font color='#f87171'>{n_err} erreur(s) critique(s)</font>")
        if n_warn: summary_txt.append(f"<font color='#fbbf24'>{n_warn} alerte(s)</font>")
        story.append(Paragraph("  —  ".join(summary_txt), S["body_b"]))
        anom_t = _table_anomalies(cleaned)
        if anom_t:
            story.append(anom_t)
    story.append(Spacer(1, 0.35*cm))

    # ── Vérifications de cohérence ─────────────────────────────────────────
    if cleaned.coherence:
        story.append(Paragraph("Vérifications de cohérence", ES["sp_sub"]))
        coh_t = _table_coherence(cleaned)
        if coh_t:
            story.append(coh_t)
        story.append(Spacer(1, 0.35*cm))

    # ── Courbe P-V ─────────────────────────────────────────────────────────
    story.append(Paragraph("Courbe pression-volume (NF P 94-110)", ES["sp_sub"]))
    try:
        img = _draw_curve_pv(cleaned, params)
        if img:
            story.append(img)
    except Exception as e:
        story.append(Paragraph(f"⚠ Courbe indisponible : {_safe(str(e))}", S["warn"]))
    story.append(Spacer(1, 0.4*cm))

    story.append(PageBreak())



# ─── Section 3 : Atlas P-V — courbe grande taille ────────────────────────────
def _draw_curve_pv_large(
    cleaned: CleanedEssai,
    params:  PressiometricParams,
) -> "Optional[Image]":
    """Courbe P-V pleine page (plus grande que la version fiche) avec annotations."""
    pts_ok   = [p for p in cleaned.points if not p.anomalie]
    pts_anom = [p for p in cleaned.points if p.anomalie]
    if not pts_ok:
        return None

    v_raw  = [pt.V60_raw_cm3 or 0  for pt in pts_ok]
    p_raw  = [pt.P60_raw_MPa        for pt in pts_ok]
    v_corr = [pt.V60_smooth_cm3 or pt.V60_corr_cm3 or 0 for pt in pts_ok]
    p_corr = [pt.P60_corr_MPa       for pt in pts_ok]
    vm     = [pt.Vm_corr_cm3 or 0   for pt in pts_ok]

    BG = "#0b0e17"
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors="#94a3b8", labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor("#1e3352")

    ax.plot(v_raw,  p_raw,  "o--", color="#444", lw=0.9, ms=3, alpha=0.45, label="Brut V60")
    ax.plot(vm,     p_corr, "o-",  color="#38bdf8", lw=2.2, ms=5,          label="Vm corrigé")
    ax.plot(v_corr, p_corr, "s-",  color="#7dd3fc", lw=1.2, ms=3, alpha=0.7, label="V60 corrigé")

    # Zone élastique
    if params.P_elastic_min_MPa is not None and params.Pf_MPa:
        ax.axhspan(params.P_elastic_min_MPa, params.Pf_MPa,
                   alpha=0.09, color="#38bdf8")
        ax.annotate("Zone élastique",
                    xy=(min(vm) if vm else 10,
                        (params.P_elastic_min_MPa + params.Pf_MPa) / 2),
                    fontsize=7, color="#38bdf8", alpha=0.75)

    # Anomaly points
    if pts_anom:
        va = [pt.Vm_corr_cm3 or 0 for pt in pts_anom]
        pa = [pt.P60_corr_MPa      for pt in pts_anom]
        ax.scatter(va, pa, marker="X", s=100, color="#ef4444",
                   zorder=6, label="Anomalie")
        for vv, pp in zip(va, pa):
            ax.annotate("⚠", xy=(vv, pp), fontsize=8, color="#ef4444",
                        xytext=(4, 4), textcoords="offset points")

    # Horizontal lines
    if params.Pf_MPa:
        ax.axhline(params.Pf_MPa, ls="--", color="#fbbf24", lw=1.3,
                   label=f"Pf = {params.Pf_MPa:.3f} MPa")
    if params.Pl_MPa:
        ax.axhline(params.Pl_MPa, ls=":",  color="#ef4444", lw=1.5,
                   label=f"Pl = {params.Pl_MPa:.3f} MPa")

    # Labels & title
    ax.set_xlabel("Volume V (cm³)", color="#94a3b8", fontsize=9)
    ax.set_ylabel("Pression P (MPa)", color="#94a3b8", fontsize=9)
    dep = f"{cleaned.depth_m:.1f} m" if cleaned.depth_m else "?"
    em_s  = f"Em = {params.Em_MPa:.2f} MPa" if params.Em_MPa else ""
    pl_s  = f"Pl = {params.Pl_MPa:.3f} MPa" if params.Pl_MPa else ""
    pf_s  = f"Pf = {params.Pf_MPa:.3f} MPa" if params.Pf_MPa else ""
    subtitle = "  |  ".join(x for x in [em_s, pf_s, pl_s] if x)
    ax.set_title(
        f"{cleaned.sheet_name}  —  Prof. {dep}\n{subtitle}",
        color="#e2e8f0", fontsize=9, pad=6,
    )
    ax.legend(fontsize=7.5, facecolor="#111827", labelcolor="#e2e8f0",
              framealpha=0.85, loc="upper left")
    ax.grid(True, color="#1e3352", lw=0.35)
    fig.tight_layout(pad=1.2)
    return _fig_to_image(fig, scale=1.0)


# ─── Interprétation normative d'une courbe P-V ───────────────────────────────
def _pv_interpretation(
    params:  PressiometricParams,
    cleaned: CleanedEssai,
) -> list:
    """
    Retourne une liste de Paragraph avec interprétation normative complète.
    Références NF P 94-110, Eurocode 7, ISO 22476-4, Fascicule 62 titre V.
    """
    S  = _styles()
    ES = _extra_styles()
    parts: list = []

    def _p(style_key: str, txt: str) -> None:
        parts.append(Paragraph(txt, ES.get(style_key, S["body"])))

    em    = params.Em_MPa
    pl    = params.Pl_MPa
    pf    = params.Pf_MPa
    pls   = params.Pl_star_MPa
    ratio = params.ratio_Em_Pl
    qual  = params.qualite or "?"
    depth = params.depth_m
    n_pal = params.n_paliers
    n_ano = params.n_anomalies

    em_s  = f"<b>{em:.2f} MPa</b>"   if em  is not None else "<b>non déterminé</b>"
    pl_s  = f"<b>{pl:.3f} MPa</b>"   if pl  is not None else "<b>non déterminé</b>"
    pf_s  = f"<b>{pf:.3f} MPa</b>"   if pf  is not None else "<b>non déterminé</b>"
    pls_s = f"<b>{pls:.3f} MPa</b>"  if pls is not None else "—"

    # ── §1 Paramètres Ménard ──────────────────────────────────────────────────
    _p("pv_section_box", "▸ Paramètres Ménard calculés (NF P 94-110 §8)")
    _p("pv_interp",
       f"À la profondeur de <b>{depth or '?'} m</b>, l'essai pressiométrique Ménard fournit : "
       f"module Em = {em_s}, pression de fluage Pf = {pf_s}, pression limite Pl = {pl_s} "
       f"(pression limite nette Pl* = {pls_s}). "
       f"Paramètres déterminés conformément à <i>NF P 94-110-1 (AFNOR, 2000) §8.1–8.2</i> "
       f"et <i>ISO 22476-4:2021 §8.3</i>."
    )
    if pf is not None and pl is not None and pl > 0:
        pf_pl = pf / pl
        ok_str = (
            "<font color='#4ade80'><b>satisfait ✓</b></font>"
            if 0.55 <= pf_pl <= 1.05 else
            "<font color='#f87171'><b>hors plage attendue ✗</b></font>"
        )
        _p("pv_interp",
           f"Rapport Pf/Pl = <b>{pf_pl:.2f}</b> — critère NF P 94-110 §8.2 (Pf/Pl ∈ [0.67 ; 1.00]) : {ok_str}."
        )
    _p("pv_norm_ref",
       "Réf. : NF P 94-110-1:2000 §8.1 — Em = 2.66·(ΔP/ΔV)·V₀  ;  "
       "ISO 22476-4:2021 §8.3 — Pf par ratio V₃₀/V₆₀.")

    # ── §2 Classification NC / SC ──────────────────────────────────────────────
    _p("pv_section_box", "▸ Comportement de consolidation NC/SC (NF P 94-110 Tableau 3)")
    if ratio is not None:
        if ratio < 5:
            nc_color, nc_lbl, nc_desc = "#f87171", "Remanié / perturbé", (
                f"Em/Pl = <b>{ratio:.1f}</b> &lt; 5 : sol remanié ou essai de mauvaise qualité. "
                "NF P 94-110 Tab.3 classe ce résultat comme non représentatif du terrain en place. "
                "Une investigation complémentaire (CPT, SPT ou essai pressiométrique répété) est recommandée."
            )
        elif ratio <= 12:
            nc_color, nc_lbl, nc_desc = "#38bdf8", "Normalement Consolidé (NC)", (
                f"Em/Pl = <b>{ratio:.1f}</b> ≤ 12 : classement <b>NC</b> selon NF P 94-110 Tab.3. "
                "Consolidation primaire normale, sans préchargement notable. "
                "Facteur rhéologique α typiquement compris entre 0.33 et 0.50 (Eurocode 7 §3.3.9)."
            )
        else:
            nc_color, nc_lbl, nc_desc = "#fbbf24", "Surconsolidé (SC)", (
                f"Em/Pl = <b>{ratio:.1f}</b> &gt; 12 : classement <b>SC</b> selon NF P 94-110 Tab.3. "
                "Préchargement naturel (érosion, glaciaire) ou anthropique probable. "
                "Facteur rhéologique α de l'ordre de 0.50 à 1.00 selon le type de sol."
            )
        _p("pv_interp",
           f"<font color='{nc_color}'><b>{nc_lbl}</b></font> — {nc_desc}")
    else:
        _p("pv_interp",
           "Rapport Em/Pl non calculable — la classification NC/SC (NF P 94-110 Tab.3) "
           "n'est pas possible pour cet essai.")
    _p("pv_norm_ref",
       "Réf. : NF P 94-110-1:2000 Tableau 3 — NC si Em/Pl ≤ 12, SC si Em/Pl > 12  ;  "
       "Baguelin et al. (1978) — Tableau de référence sol/Em/Pl.")

    # ── §3 Identification géotechnique ────────────────────────────────────────
    _p("pv_section_box", "▸ Identification géotechnique du sol")
    matched = None
    if em is not None and pl is not None:
        for cls_id, cls_name, em_min, em_max, pl_min, pl_max, cls_desc in SOIL_NORMS_TABLE:
            if em_min <= em <= em_max and pl_min <= pl <= pl_max:
                matched = (cls_id, cls_name, cls_desc)
                break
    if matched:
        cls_id, cls_name, cls_desc = matched
        _p("pv_interp",
           f"Les valeurs Em = {em_s} et Pl = {pl_s} correspondent à la classe "
           f"<b>{cls_id} — {_safe(cls_name)}</b> selon la table normative Ménard. "
           f"{_safe(cls_desc)}"
        )
    elif params.sol_type and params.sol_type != "Indéterminé":
        _p("pv_interp",
           f"Type de sol identifié par l'analyseur : <b>{_safe(params.sol_type)}</b>. "
           "Cette classification est basée sur les paramètres pressiométriques calculés."
        )
    else:
        _p("pv_interp",
           "L'identification du type de sol n'a pu être établie avec certitude. "
           "Une corrélation avec les données géologiques locales est nécessaire (Eurocode 7 §3.2)."
        )
    # Gammes compatibles
    if em is not None:
        cands = [
            f"{r[0]} ({r[1]}: Em {r[2]}–{r[3]} MPa)"
            for r in SOIL_NORMS_TABLE
            if r[2] * 0.7 <= em <= r[3] * 1.3
        ][:3]
        if cands:
            _p("pv_norm_ref", "Classes compatibles par gamme Em : " + " | ".join(cands) + ".")
    _p("pv_norm_ref",
       "Réf. : NF P 94-110-1:2000 §9 — Table de corrélation Em/Pl/sol  ;  "
       "Baguelin et al. (1978) — Manuel pressiométrique.")

    # ── §4 Qualité de l'essai ─────────────────────────────────────────────────
    _p("pv_section_box", "▸ Qualité de l'essai (NF P 94-110 §8.3 Tableau 4)")
    qlabels = {"A": ("Excellent",  "#4ade80"), "B": ("Bon",       "#38bdf8"),
               "C": ("Acceptable", "#fbbf24"), "D": ("Mauvais",   "#f87171"),
               "?": ("Non classé", "#94a3b8")}
    ql, qc = qlabels.get(qual, ("?", "#94a3b8"))
    q_map = {row[0]: (row[2], row[3], row[4]) for row in QUALITY_GRADES}
    q_creep, q_maxano, q_desc = q_map.get(qual, (None, None, None))
    n_valid = n_pal - n_ano
    ano_color = "#f87171" if n_ano > 0 else "#4ade80"
    verdict = (
        "Essai de haute qualité — utilisable directement pour le calcul de capacité portante "
        "et de tassements (Eurocode 7 §6.6)."
        if qual in ("A", "B") else
        "Résultats exploitables avec précaution — confirmer par d'autres investigations (EC7 §2.4.1)."
        if qual == "C" else
        "Essai non représentatif — un nouvel essai pressiométrique est recommandé (NF P 94-110 §7.3)."
        if qual == "D" else
        "Qualité non déterminée."
    )
    _p("pv_interp",
       f"Classe de qualité : <font color='{qc}'><b>{qual} — {ql}</b></font>. "
       + (f"{_safe(q_desc)}. " if q_desc else "")
       + f"{n_pal} paliers au total, <b>{n_valid}</b> valides, "
       + f"<font color='{ano_color}'><b>{n_ano}</b></font> anomalie(s). {verdict}"
    )
    _p("pv_norm_ref",
       f"Réf. : NF P 94-110-1:2000 §8.3 Tableau 4 — seuil creep ratio {q_creep or '—'}, "
       f"anomalies admissibles ≤ {q_maxano or '—'}  ;  ASTM D4719-20 §11.1 — contrôle qualité.")

    # ── §5 Zone élastique ─────────────────────────────────────────────────────
    if params.P_elastic_min_MPa is not None and params.P_elastic_max_MPa is not None:
        _p("pv_section_box", "▸ Zone pseudo-élastique (Zone II de Ménard)")
        p_min  = params.P_elastic_min_MPa
        p_max  = params.P_elastic_max_MPa
        v_min  = params.V_elastic_min_cm3
        v_max  = params.V_elastic_max_cm3
        slope  = params.slope_elastic_MPa_per_cm3
        dp     = (p_max - p_min) if p_max and p_min else None
        _p("pv_interp",
           f"Zone pseudo-élastique (Zone II) : de P = <b>{p_min:.3f} MPa</b>"
           + (f" (V = {v_min:.0f} cm³)" if v_min else "")
           + f" à P = <b>{p_max:.3f} MPa</b>"
           + (f" (V = {v_max:.0f} cm³)" if v_max else "")
           + (f". ΔP = <b>{dp:.3f} MPa</b>" if dp else "")
           + (f". Pente ΔP/ΔV = <b>{slope:.4f} MPa/cm³</b>" if slope else "")
           + ". Formule Em = 2.66·(ΔP/ΔV)·V₀ (V₀ = 535 cm³, NF P 94-110 §8.1)."
        )
        _p("pv_norm_ref",
           "Réf. : NF P 94-110-1:2000 Figure 2 — Zones I (remaniement), II (élastique), III (fluage/rupture).")

    # ── §6 Capacité portante estimée ──────────────────────────────────────────
    if pl is not None:
        _p("pv_section_box", "▸ Estimation de la capacité portante (Fascicule 62 titre V / EC7 Annexe D)")
        pls_val = pls if pls is not None else pl
        k       = 1.0
        qnet    = k * pls_val
        _p("pv_interp",
           f"Capacité portante nette estimée à {depth or '?'} m : "
           f"q<sub>net</sub> = k·Pl* ≈ <b>{qnet:.3f} MPa</b> = <b>{qnet * 1000:.0f} kPa</b> "
           f"(k = {k:.1f} — fondation rectangulaire de référence, Pl* ≈ {pls_val:.3f} MPa). "
           "Le coefficient k doit être adapté à la géométrie réelle de la fondation "
           "(B/L, D/B) selon Fascicule 62 titre V §4.3 et Eurocode 7 Annexe D §D.3."
        )
        if em is not None:
            _p("pv_interp",
               f"Tassement par méthode Ménard (Ménard & Rousseau, 1962) : "
               f"s ∝ q·(B₀/9Em)·(B/B₀)^α — Em = {em:.2f} MPa, "
               f"facteur rhéologique α selon type de sol et statut NC/SC. "
               "Réf. : NF P 94-261:2013 §12 — Fondations superficielles."
            )
        _p("pv_norm_ref",
           "Réf. : Fascicule 62 titre V §4.3 — qnet = k·Pl*  ;  "
           "Eurocode 7 EN 1997-1:2004 Annexe D §D.3  ;  Ménard & Rousseau (1962).")

    # ── §7 Anomalies ──────────────────────────────────────────────────────────
    if n_ano > 0:
        _p("pv_section_box", "▸ Anomalies détectées & impact sur les résultats")
        for a in cleaned.anomalies[:6]:
            sc = "#f87171" if a.severity == "error" else "#fbbf24"
            sl = "ERREUR" if a.severity == "error" else "Alerte"
            _p("pv_interp",
               f"<font color='{sc}'>[{sl} · Palier {a.palier}]</font> {_safe(a.description)}"
            )
        if len(cleaned.anomalies) > 6:
            _p("pv_interp",
               f"... et <b>{len(cleaned.anomalies) - 6}</b> autre(s) anomalie(s) "
               "(voir tableau des anomalies en Section 2)."
            )
        _p("pv_norm_ref",
           "Réf. : NF P 94-110 §7.3 — Détection par ratio V₃₀/V₆₀  ;  "
           "ISO 22476-4:2021 §8.5 — Critères de validation des paliers.")

    # ── Références normatives consolidées ─────────────────────────────────────
    parts.append(Spacer(1, 0.15 * cm))
    for rl in [
        "Normes appliquées à cette courbe :",
        "• NF P 94-110-1:2000 (AFNOR) — Essai pressiométrique Ménard — méthode de dépouillement",
        "• ISO 22476-4:2021 (ISO/TC 182) — Essais pressiométriques Ménard — validation & interprétation",
        "• EN 1997-1:2004 Eurocode 7 — Calcul géotechnique — capacité portante & tassements",
        "• Fascicule 62 titre V (MELT, 1993) — Règles de calcul des fondations superficielles",
        "• ASTM D4719-20 — Prebored Pressuremeter Testing — contrôle qualité des mesures",
        "• Ménard & Rousseau (1962) — L'interpretation des résultats des essais pressiométriques",
    ]:
        parts.append(Paragraph(_safe(rl), ES["pv_norm_ref"]))

    return parts


# ─── Section 3 : Atlas des courbes P-V avec interprétations ──────────────────
def _section_courbes_pv(
    story:       list,
    cleaned_map: Dict[str, CleanedEssai],
    params_map:  Dict[str, PressiometricParams],
) -> None:
    """
    Section 3 : regroupe toutes les courbes P-V (grande taille) avec leur
    interprétation normative détaillée générée par PressiomètreIA v2.
    """
    S  = _styles()
    ES = _extra_styles()

    _section_heading(story, "3.", "Atlas des Courbes P-V — Analyse Normative Complète")
    story.append(Paragraph(
        "Cette section regroupe l'ensemble des courbes pression-volume (P-V) issues des "
        "essais pressiométriques Ménard, accompagnées d'une interprétation normative "
        "détaillée. Chaque courbe fait l'objet d'une analyse intégrant : les paramètres "
        "calculés (Em, Pf, Pl), la classification géotechnique du sol, le statut de "
        "consolidation NC/SC, la qualité de l'essai, la zone pseudo-élastique et une "
        "estimation préliminaire de la capacité portante.",
        S["body"]
    ))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(
        "<b>Normes de référence :</b> NF P 94-110-1:2000 · ISO 22476-4:2021 · "
        "EN 1997-1:2004 (Eurocode 7) · Fascicule 62 titre V · ASTM D4719-20.",
        S["small"]
    ))
    story.append(_hr(C_DGRAY, 0.4))
    story.append(PageBreak())

    sp_names = sorted(params_map.keys())
    for idx, name in enumerate(sp_names, start=1):
        cl = cleaned_map.get(name)
        pa = params_map.get(name)
        if not cl or not pa:
            continue

        # ── En-tête du SP ──────────────────────────────────────────────────
        depth_str = f"{pa.depth_m:.1f} m" if pa.depth_m else "?"
        qual      = pa.qualite or "?"
        qc_map    = {"A": "#4ade80", "B": "#38bdf8", "C": "#fbbf24",
                     "D": "#f87171", "?": "#94a3b8"}
        qc = qc_map.get(qual, "#94a3b8")
        nc_lbl = pa.nc_status or "NC"

        em_cell = f"Em = <b>{pa.Em_MPa:.2f} MPa</b>" if pa.Em_MPa else "Em = —"
        pl_cell = f"Pl = <b>{pa.Pl_MPa:.3f} MPa</b>" if pa.Pl_MPa else "Pl = —"
        pf_cell = f"Pf = <b>{pa.Pf_MPa:.3f} MPa</b>" if pa.Pf_MPa else "Pf = —"
        r_cell  = f"Em/Pl = <b>{pa.ratio_Em_Pl:.1f}</b>" if pa.ratio_Em_Pl else "Em/Pl = —"

        hdr = Table(
            [[
                Paragraph(f"<b>3.{idx} — {_safe(name)}</b>", ES["sp_title"]),
                Paragraph(
                    f"Prof. <b>{depth_str}</b>  ·  Qual. <font color='{qc}'><b>{qual}</b></font>  ·  "
                    f"{_safe(nc_lbl)}  ·  Sol : <b>{_safe(pa.sol_type or '?')}</b>",
                    S["small"]
                ),
            ]],
            colWidths=[9 * cm, PAGE_W - 2 * MARGIN_H - 9 * cm],
        )
        hdr.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#080c14")),
            ("BOX",           (0, 0), (-1, -1), 1.5, C_SKY),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(hdr)

        # Ligne paramètres clés
        params_row = Table(
            [[
                Paragraph(em_cell, S["small"]),
                Paragraph(pf_cell, S["small"]),
                Paragraph(pl_cell, S["small"]),
                Paragraph(r_cell,  S["small"]),
            ]],
            colWidths=[(PAGE_W - 2 * MARGIN_H) / 4] * 4,
        )
        params_row.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#060a12")),
            ("LINEBELOW",    (0, 0), (-1, -1), 0.5, C_BORDER),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(params_row)
        story.append(Spacer(1, 0.3 * cm))

        # ── Courbe P-V grande taille ───────────────────────────────────────
        try:
            img = _draw_curve_pv_large(cl, pa)
            if img:
                story.append(img)
            else:
                story.append(Paragraph(
                    "⚠ Courbe P-V non disponible (données insuffisantes).", S["warn"]))
        except Exception as exc:
            story.append(Paragraph(
                f"⚠ Erreur génération courbe : {_safe(str(exc))}", S["warn"]))

        story.append(Spacer(1, 0.4 * cm))

        # ── Interprétation normative ───────────────────────────────────────
        story.append(Paragraph(
            "Analyse &amp; interprétation normative — PressiomètreIA v2 alimenté par les "
            "normes internationales (NF P 94-110 · EC7 · ISO 22476-4)",
            ES["sp_sub"],
        ))
        story.append(Spacer(1, 0.1 * cm))

        interp = _pv_interpretation(pa, cl)
        for ip in interp:
            story.append(ip)

        story.append(Spacer(1, 0.4 * cm))
        story.append(_hr(C_DGRAY, 0.6))
        story.append(PageBreak())


# ─── Section 4 : Synthèse qualité & statistiques ─────────────────────────────
def _section_quality(
    story: list,
    params_map: Dict[str, PressiometricParams],
    cleaned_map: Dict[str, CleanedEssai],
):
    S  = _styles()
    ES = _extra_styles()

    _section_heading(story, "4.", "Synthèse Qualité & Statistiques")

    # Statistiques globales
    all_em  = [p.Em_MPa  for p in params_map.values() if p.Em_MPa  is not None]
    all_pl  = [p.Pl_MPa  for p in params_map.values() if p.Pl_MPa  is not None]
    all_pf  = [p.Pf_MPa  for p in params_map.values() if p.Pf_MPa  is not None]
    qual_cnt = {"A": 0, "B": 0, "C": 0, "D": 0, "?": 0}
    for p in params_map.values():
        qual_cnt[p.qualite or "?"] = qual_cnt.get(p.qualite or "?", 0) + 1

    def _stat_block(vals, label, unit):
        if not vals:
            return [Paragraph(f"{label} : — ({unit})", S["body"])]
        return [
            Paragraph(f"{np.mean(vals):.2f}", ES["stat_val"]),
            Paragraph(f"moy. {label} ({unit})", ES["stat_lbl"]),
            Paragraph(
                f"min {np.min(vals):.2f}  ·  max {np.max(vals):.2f}  ·  "
                f"σ {np.std(vals):.2f}  ·  n={len(vals)}",
                S["small"]),
        ]

    # Box stats
    stat_rows = [[
        _stat_block(all_em, "Em", "MPa"),
        _stat_block(all_pl, "Pl", "MPa"),
        _stat_block(all_pf, "Pf", "MPa"),
    ]]
    # Flatten inner lists into cells
    flat_stats = []
    for row in stat_rows:
        flat_row = []
        for cell in row:
            cell_widget = Table([[c] for c in cell], colWidths=[4.5*cm])
            cell_widget.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#080c14")),
                ("BOX",        (0,0), (-1,-1), 0.8, C_BORDER),
                ("PADDING",    (0,0), (-1,-1), 6),
                ("ALIGN",      (0,0), (-1,-1), "CENTER"),
            ]))
            flat_row.append(cell_widget)
        flat_stats.append(flat_row)

    t_stats = Table(flat_stats, colWidths=[5*cm, 5*cm, 5*cm])
    t_stats.setStyle(TableStyle([
        ("PADDING",    (0,0), (-1,-1), 8),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 0.5*cm))

    # Distribution qualité
    story.append(Paragraph("Distribution des classes de qualité", ES["sp_sub"]))
    qual_rows = [["Classe", "A — Excellent", "B — Bon", "C — Acceptable", "D — Médiocre", "? — Inconnu"]]
    qual_rows.append(["Nb. SP"] + [str(qual_cnt.get(q, 0)) for q in ["A", "B", "C", "D", "?"]])
    cw_q = [2.5*cm] + [3.2*cm]*5
    tq = Table(qual_rows, colWidths=cw_q, repeatRows=1)
    ts_q = _tbl_style(header_rows=1)
    for i, q in enumerate(["A", "B", "C", "D", "?"], start=1):
        ts_q.add("TEXTCOLOR",  (i, 1), (i, 1), _QUAL_COLOR.get(q, C_MGRAY))
        ts_q.add("FONTNAME",   (i, 1), (i, 1), "Helvetica-Bold")
    tq.setStyle(ts_q)
    story.append(tq)
    story.append(Spacer(1, 0.5*cm))

    # Graphique de distribution Em
    if len(all_em) >= 2:
        _plot_distribution(story, all_em, "Em (MPa)", "Distribution du Module Pressiométrique Em")
    if len(all_pl) >= 2:
        _plot_distribution(story, all_pl, "Pl (MPa)", "Distribution de la Pression Limite Pl")

    story.append(PageBreak())


def _plot_distribution(story: list, vals: list, xlabel: str, title: str):
    """Mini histogramme matplotlib inséré dans le PDF."""
    fig, ax = plt.subplots(figsize=(6, 2.5), facecolor="#080c14")
    ax.set_facecolor("#0b0f1a")
    ax.hist(vals, bins=min(12, len(vals)), color="#38bdf8", edgecolor="#0d2040", alpha=0.85)
    ax.axvline(float(np.mean(vals)), color="#fbbf24", linestyle="--", lw=1.5,
               label=f"Moy. {np.mean(vals):.2f}")
    ax.set_xlabel(xlabel, color="#94a3b8", fontsize=8)
    ax.set_ylabel("Nb. SP", color="#94a3b8", fontsize=8)
    ax.set_title(title, color="#38bdf8", fontsize=9)
    ax.tick_params(colors="#64748b", labelsize=7)
    for sp in ax.spines.values():
        sp.set_color("#1e3352")
    ax.legend(fontsize=7, facecolor="#111827", edgecolor="#1e3352",
              labelcolor="#fbbf24")
    plt.tight_layout()
    story.append(_fig_to_image(fig, scale=0.85))
    story.append(Spacer(1, 0.25*cm))


# ─── Section 4 : Conversation KIBALI ─────────────────────────────────────────
def _section_chat(story: list, conversation: list):
    S  = _styles()
    ES = _extra_styles()

    _section_heading(story, "5.", "Conversation Complète KIBALI — IA Géotechnique")

    if not conversation:
        story.append(Paragraph(
            "Aucune conversation enregistrée dans cette session.",
            S["body"]))
        story.append(PageBreak())
        return

    story.append(Paragraph(
        f"Session de {len(conversation)} message(s) enregistrée(s). "
        "Les messages utilisateur sont en bleu ciel, les réponses KIBALI en vert néon.",
        S["body"]))
    story.append(Spacer(1, 0.3*cm))

    for idx, msg in enumerate(conversation, start=1):
        role = msg.get("role", "user")
        text = msg.get("text", "")
        ts_raw = msg.get("timestamp", "")

        is_user  = (role == "user")
        bar_color = C_USER_BAR if is_user else C_KIBALI_BAR
        bg_color  = C_USER_BG  if is_user else C_KIBALI_BG
        label     = f"Utilisateur  #{idx}" if is_user else f"KIBALI  #{idx}"
        lbl_style = ES["user_label"] if is_user else ES["kibali_label"]

        inner = [
            [Paragraph(label, lbl_style)],
            [Paragraph(_safe(text[:1600]), ES["msg"])],
        ]
        if ts_raw:
            inner.append([Paragraph(str(ts_raw), ES["ts"])])

        cell_t = Table(inner, colWidths=[PAGE_W - 2*MARGIN_H - 1.5*cm])
        cell_t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg_color),
            ("PADDING",    (0,0), (-1,-1), 6),
            ("LEFTPADDING",(0,0), (-1,-1), 10),
            ("TOPPADDING", (0,0), (0, 0),  6),
        ]))

        # Barre colorée à gauche
        bubble_row = [[
            Table([[""]], colWidths=[4],
                  style=TableStyle([
                      ("BACKGROUND", (0,0), (0,0), bar_color),
                      ("ROWHEIGHT",  (0,0), (0,0), 0),
                  ])),
            cell_t,
        ]]
        bubble = Table(bubble_row, colWidths=[4, PAGE_W - 2*MARGIN_H - 4])
        bubble.setStyle(TableStyle([
            ("PADDING",  (0,0), (-1,-1), 0),
            ("VALIGN",   (0,0), (-1,-1), "TOP"),
        ]))
        story.append(KeepTogether([bubble, Spacer(1, 0.3*cm)]))

    story.append(PageBreak())


# ─── Section 5 : Conclusions ─────────────────────────────────────────────────
def _section_conclusions(
    story: list,
    params_map: Dict[str, PressiometricParams],
    cleaned_map: Dict[str, CleanedEssai],
    meta: dict,
):
    S = _styles()
    _section_heading(story, "6.", "Conclusions et Recommandations")

    n_sp    = len(params_map)
    n_ok    = sum(1 for p in params_map.values() if p.qualite in ("A","B"))
    n_anom  = sum(len(c.anomalies) for c in cleaned_map.values())
    n_coh   = sum(1 for p in params_map.values() if not p.is_coherent)
    all_em  = [p.Em_MPa for p in params_map.values() if p.Em_MPa is not None]
    all_pl  = [p.Pl_MPa for p in params_map.values() if p.Pl_MPa is not None]

    story.append(Paragraph(
        f"L'analyse pressiométrique a porté sur <b>{n_sp}</b> sondage(s) (SP). "
        f"<b>{n_ok}</b> SP ont obtenu une qualité A ou B (classe supérieure). "
        f"Un total de <b>{n_anom}</b> anomalie(s) a été détecté sur l'ensemble des essais, "
        f"et <b>{n_coh}</b> SP présente(nt) des incohérences de mesure.", S["body"]))
    story.append(Spacer(1, 0.25*cm))

    if all_em:
        story.append(Paragraph(
            f"Le module pressiométrique moyen Em est de <b>{np.mean(all_em):.2f} MPa</b> "
            f"(min {np.min(all_em):.2f} — max {np.max(all_em):.2f} MPa).", S["body"]))
    if all_pl:
        story.append(Paragraph(
            f"La pression limite moyenne Pl est de <b>{np.mean(all_pl):.3f} MPa</b> "
            f"(min {np.min(all_pl):.3f} — max {np.max(all_pl):.3f} MPa).", S["body"]))

    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Les résultats devront être interprétés conjointement avec les données "
        "géologiques locales et les exigences du projet (Eurocode 7, DTU 13.12). "
        "Tout essai de qualité C ou D nécessite une investigation complémentaire.",
        S["body"]))
    story.append(Spacer(1, 0.3*cm))

    eng = meta.get("engineer", "")
    loc = meta.get("location", "Port-Gentil, En face du Stade PERENCO, Gabon")
    now_str = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")
    story.append(Paragraph(
        f"Rapport généré le {now_str} par PressiomètreIA v2 — SETRAF GABON. "
        f"{'Ingénieur responsable : ' + eng + ' — ' if eng else ''}{loc}.",
        S["small"]))


# ─── Point d'entrée principal ─────────────────────────────────────────────────
def build_full_report(
    parsed_files:  Dict[str, ParsedFile],
    cleaned_map:   Dict[str, CleanedEssai],
    params_map:    Dict[str, PressiometricParams],
    conversation:  list,
    meta: Optional[dict] = None,
) -> bytes:
    """
    Génère le rapport complet (~30 pages) en PDF et retourne les bytes.

    Parameters
    ----------
    parsed_files  : tous les fichiers parsés (pour métadonnées brutes)
    cleaned_map   : essais nettoyés keyed by sheet_name
    params_map    : paramètres Ménard keyed by sheet_name
    conversation  : liste de dicts {role, text, timestamp, ...}
    meta          : dict optionnel {title, engineer, location, ref}
    """
    meta = meta or {}
    now  = datetime.datetime.now()
    buf  = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_H,
        rightMargin=MARGIN_H,
        topMargin=MARGIN_V,
        bottomMargin=MARGIN_V,
        title=meta.get("title", "Rapport Complet Pressiométrique — SETRAF"),
        author="SETRAF GABON — PressiomètreIA v2",
    )

    story: list = []

    # ── Page de garde ──────────────────────────────────────────────────────
    _cover_page(story, meta, len(params_map), now)

    # ── Table des matières ─────────────────────────────────────────────────
    sp_names = sorted(params_map.keys())
    _toc(story, sp_names)

    # ── Section 1 : tableau récap ──────────────────────────────────────────
    _section_summary(story, cleaned_map, params_map)

    # ── Section 2 : fiches SP ─────────────────────────────────────────────
    _section_heading(story, "2.", "Fiches Détaillées par Sondage Pressiométrique")
    story.append(PageBreak())
    for idx, name in enumerate(sp_names, start=1):
        cl = cleaned_map.get(name)
        pa = params_map.get(name)
        if cl and pa:
            _sp_fiche(story, cl, pa, idx)

    # ── Section 3 : Atlas P-V avec interprétations normatives ─────────────
    _section_courbes_pv(story, cleaned_map, params_map)

    # ── Section 4 : qualité & stats ───────────────────────────────────────
    _section_quality(story, params_map, cleaned_map)

    # ── Section 5 : conversation KIBALI ───────────────────────────────────
    _section_chat(story, conversation)

    # ── Section 6 : conclusions ───────────────────────────────────────────
    _section_conclusions(story, params_map, cleaned_map, meta)

    doc.build(story, onFirstPage=_setraf_header, onLaterPages=_setraf_header)
    return buf.getvalue()
