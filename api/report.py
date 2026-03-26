"""
api/report.py — Rapport pressiometrique professionnel (ReportLab)
Entreprise : SETRAF GABON
Normes     : NF P 94-110, Eurocode 7, ISO 22476-4, ASTM D4719
Structure  :
  0. En-tete SETRAF + Page de garde
  1. Table des matieres
  2. Cadre normatif et reglementaire (avec enrichissement web optionnel)
  3. Resume des parametres (tableau synoptique)
  4. Profil geotechnique
  5. Coupe geologique
  6. Fiches d essais detaillees (metadonnees + parametres + data + courbe P-V)
  7. Interpretations et recommandations (par essai)
  8. Synthese IA KIBALI (optionnel)
  9. Conclusions generales
"""
from __future__ import annotations
import io
import datetime
from pathlib import Path
from typing import List, Optional, Dict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether, NextPageTemplate,
    Frame, BaseDocTemplate, PageTemplate,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF

from .models import (
    ParsedFile, CleanedEssai, PressiometricParams, ProfileData
)
from .norms import (
    NORMATIVE_REFS, SOIL_NORMS_TABLE, NC_SC_TABLE,
    MENARD_FORMULAS, QUALITY_GRADES, RHEOLOGICAL_ALPHA,
    get_web_normative_context,
)

# ─── Palette SETRAF ───────────────────────────────────────────────────────────
C_NAVY    = colors.HexColor("#0a1628")
C_BLUE    = colors.HexColor("#0d6efd")
C_SKY     = colors.HexColor("#38bdf8")
C_ORANGE  = colors.HexColor("#f97316")
C_GOLD    = colors.HexColor("#fbbf24")
C_WHITE   = colors.white
C_LGRAY   = colors.HexColor("#e2e8f0")
C_MGRAY   = colors.HexColor("#94a3b8")
C_DGRAY   = colors.HexColor("#334155")
C_GREEN   = colors.HexColor("#22c55e")
C_RED     = colors.HexColor("#ef4444")
C_AMBER   = colors.HexColor("#f59e0b")
C_ROW0    = colors.HexColor("#0f1a2e")
C_ROW1    = colors.HexColor("#131f30")
C_HEADER  = colors.HexColor("#0d2040")
C_BORDER  = colors.HexColor("#1e3a5f")

PAGE_W, PAGE_H = A4
MARGIN_H = 1.8*cm
MARGIN_V = 2.2*cm

# ─── Logo SETRAF GABON ────────────────────────────────────────────────
_LOGO_PATH = str(Path(__file__).parent.parent / "LOGO VECTORISE PNG.png")


def _logo_img(height_cm: float = 1.4, max_width_cm: float = 5.0) -> Optional[Image]:
    """Charge et redimensionne le logo SETRAF GABON. Retourne None si introuvable."""
    import os
    if not os.path.isfile(_LOGO_PATH):
        return None
    try:
        img = Image(_LOGO_PATH)
        aspect = img.imageWidth / max(img.imageHeight, 1)
        h_pt   = height_cm * cm
        w_pt   = h_pt * aspect
        max_w  = max_width_cm * cm
        if w_pt > max_w:
            w_pt = max_w
            h_pt = w_pt / aspect
        img.drawWidth  = w_pt
        img.drawHeight = h_pt
        return img
    except Exception:
        return None


# ─── Styles ───────────────────────────────────────────────────────────────────
_STYLES_CACHE = None
def _styles():
    global _STYLES_CACHE
    if _STYLES_CACHE:
        return _STYLES_CACHE
    base = getSampleStyleSheet()

    def S(name, parent="Normal", **kw):
        p = ParagraphStyle(name, parent=base[parent], **kw)
        return p

    _STYLES_CACHE = {
        "cover_company": S("cover_company", "Normal",
            fontSize=28, fontName="Helvetica-Bold", textColor=C_SKY,
            alignment=TA_CENTER, spaceAfter=0, leading=32),
        "cover_sub": S("cover_sub", "Normal",
            fontSize=11, fontName="Helvetica", textColor=C_GOLD,
            alignment=TA_CENTER, spaceAfter=2),
        "cover_title": S("cover_title", "Normal",
            fontSize=22, fontName="Helvetica-Bold", textColor=C_WHITE,
            alignment=TA_CENTER, spaceAfter=8, leading=28),
        "cover_subtitle": S("cover_subtitle", "Normal",
            fontSize=13, fontName="Helvetica-BoldOblique", textColor=C_SKY,
            alignment=TA_CENTER, spaceAfter=4),
        "cover_meta": S("cover_meta", "Normal",
            fontSize=10, fontName="Helvetica", textColor=C_LGRAY,
            alignment=TA_LEFT, spaceAfter=2),
        "cover_norm": S("cover_norm", "Normal",
            fontSize=8, fontName="Helvetica-Oblique", textColor=C_MGRAY,
            alignment=TA_CENTER, spaceAfter=1),
        "h1": S("h1", "Heading1",
            fontSize=13, fontName="Helvetica-Bold", textColor=C_SKY,
            spaceBefore=14, spaceAfter=6, borderPad=4,
            borderWidth=0, leading=16),
        "h2": S("h2", "Heading2",
            fontSize=10.5, fontName="Helvetica-Bold", textColor=C_GOLD,
            spaceBefore=8, spaceAfter=4, leading=13),
        "h3": S("h3", "Heading3",
            fontSize=9.5, fontName="Helvetica-Bold", textColor=C_SKY,
            spaceBefore=5, spaceAfter=3),
        "body": S("body", "Normal",
            fontSize=8.5, fontName="Helvetica", textColor=C_LGRAY,
            spaceAfter=3, leading=12, alignment=TA_JUSTIFY),
        "body_b": S("body_b", "Normal",
            fontSize=8.5, fontName="Helvetica-Bold", textColor=C_WHITE,
            spaceAfter=3, leading=12),
        "small": S("small", "Normal",
            fontSize=7, fontName="Helvetica", textColor=C_MGRAY,
            spaceAfter=2, leading=9),
        "ref": S("ref", "Normal",
            fontSize=7, fontName="Helvetica-Oblique", textColor=C_MGRAY,
            spaceAfter=1, leading=9),
        "table_hdr": S("table_hdr", "Normal",
            fontSize=7.5, fontName="Helvetica-Bold", textColor=C_SKY,
            alignment=TA_CENTER),
        "table_cell": S("table_cell", "Normal",
            fontSize=7.5, fontName="Helvetica", textColor=C_LGRAY,
            alignment=TA_LEFT),
        "warn": S("warn", "Normal",
            fontSize=8, fontName="Helvetica-BoldOblique", textColor=C_AMBER,
            spaceAfter=2),
        "good": S("good", "Normal",
            fontSize=8, fontName="Helvetica-BoldOblique", textColor=C_GREEN,
            spaceAfter=2),
        "toc_title": S("toc_title", "Normal",
            fontSize=11, fontName="Helvetica-Bold", textColor=C_SKY,
            spaceBefore=8, spaceAfter=4, alignment=TA_CENTER),
        "toc_item": S("toc_item", "Normal",
            fontSize=9, fontName="Helvetica", textColor=C_LGRAY,
            spaceAfter=3, leftIndent=12),
    }
    return _STYLES_CACHE


def _tbl_style(header_rows=1, alt=True):
    ts = TableStyle([
        ("BACKGROUND",    (0,0),  (-1,header_rows-1), C_HEADER),
        ("TEXTCOLOR",     (0,0),  (-1,header_rows-1), C_SKY),
        ("FONTNAME",      (0,0),  (-1,header_rows-1), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1),             7.5),
        ("ALIGN",         (0,0),  (-1,header_rows-1), "CENTER"),
        ("VALIGN",        (0,0),  (-1,-1),             "MIDDLE"),
        ("GRID",          (0,0),  (-1,-1),             0.4, C_BORDER),
        ("ROWBACKGROUNDS",(0,header_rows),(-1,-1),
            [C_ROW0, C_ROW1] if alt else [C_ROW0]),
        ("TEXTCOLOR",     (0,1),  (-1,-1), C_LGRAY),
        ("PADDING",       (0,0),  (-1,-1), 4),
        ("LEFTPADDING",   (0,0),  (-1,-1), 6),
        ("TOPPADDING",    (0,0),  (-1,-1), 3),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 3),
        ("LINEBELOW",     (0,0),  (-1,header_rows-1), 1.5, C_SKY),
    ])
    return ts


def _hr(color=C_SKY, thickness=1.0):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=4, spaceBefore=4)

def _fig_to_image(fig, scale=0.95) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    img = Image(buf)
    max_w = (PAGE_W - 2*MARGIN_H) * scale
    s = min(max_w / img.drawWidth, 1.0)
    img.drawWidth  *= s
    img.drawHeight *= s
    return img


# ─── Fonctions dessin matplotlib ─────────────────────────────────────────────
def _draw_curve_pv(cleaned: CleanedEssai, params: PressiometricParams) -> Optional[Image]:
    pts_ok   = [p for p in cleaned.points if not p.anomalie]
    pts_anom = [p for p in cleaned.points if p.anomalie]
    if not pts_ok:
        return None

    v_raw   = [pt.V60_raw_cm3 or 0 for pt in pts_ok]
    p_raw   = [pt.P60_raw_MPa for pt in pts_ok]
    v_corr  = [pt.V60_smooth_cm3 or pt.V60_corr_cm3 or 0 for pt in pts_ok]
    p_corr  = [pt.P60_corr_MPa for pt in pts_ok]
    vm      = [pt.Vm_corr_cm3 or 0 for pt in pts_ok]

    BG = "#0b0e17"
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors="#94a3b8")
    for sp in ax.spines.values(): sp.set_edgecolor("#1e3352")
    ax.xaxis.label.set_color("#94a3b8")
    ax.yaxis.label.set_color("#94a3b8")

    ax.plot(v_raw,  p_raw,  "o--", color="#555", lw=1.0, ms=3, alpha=0.5,  label="Brut V60")
    ax.plot(vm,     p_corr, "o-",  color="#38bdf8", lw=2.2, ms=5, label="Vm corrige")
    ax.plot(v_corr, p_corr, "s-",  color="#7dd3fc", lw=1.2, ms=3, alpha=0.7, label="V60 corrige")

    if pts_anom:
        va = [pt.Vm_corr_cm3 or 0 for pt in pts_anom]
        pa = [pt.P60_corr_MPa for pt in pts_anom]
        ax.scatter(va, pa, marker="X", s=90, color="#ef4444", zorder=5, label="Anomalie")

    if params.Pf_MPa:
        ax.axhline(params.Pf_MPa, ls="--", color="#fbbf24", lw=1.2,
                   label=f"Pf = {params.Pf_MPa:.3f} MPa")
    if params.Pl_MPa:
        ax.axhline(params.Pl_MPa, ls=":", color="#ef4444", lw=1.5,
                   label=f"Pl = {params.Pl_MPa:.3f} MPa")
    if params.P_elastic_min_MPa is not None and params.Pf_MPa:
        ax.axhspan(params.P_elastic_min_MPa, params.Pf_MPa,
                   alpha=0.07, color="#38bdf8", label="Zone elastique")

    ax.set_xlabel("Volume V (cm3)", color="#94a3b8")
    ax.set_ylabel("Pression P (MPa)", color="#94a3b8")
    dep = f"{cleaned.depth_m} m" if cleaned.depth_m else "?"
    ax.set_title(
        f"Courbe Pression-Volume — {cleaned.sheet_name} ({dep})\n"
        f"Em = {params.Em_MPa} MPa | Pf = {params.Pf_MPa} MPa | Pl = {params.Pl_MPa} MPa",
        color="#e2e8f0", fontsize=9
    )
    ax.legend(fontsize=7, facecolor="#111827", labelcolor="#e2e8f0", framealpha=0.8)
    ax.grid(True, color="#1e3352", lw=0.4)
    fig.tight_layout()
    return _fig_to_image(fig)


def _draw_profile(profile: ProfileData) -> Optional[Image]:
    if not profile or not profile.depths:
        return None
    depths  = profile.depths
    em_vals = [e or 0 for e in profile.Em_MPa]
    pl_vals = [p or 0 for p in profile.Pl_MPa]
    cols    = profile.sol_colors or ["#888"] * len(depths)
    types   = profile.sol_types  or ["?"]   * len(depths)

    BG = "#0b0e17"
    fig, (ax1, ax2, ax3) = plt.subplots(
        1, 3, figsize=(10, max(5, len(depths)*0.7)),
        sharey=True, facecolor=BG
    )
    for ax in (ax1, ax2, ax3):
        ax.set_facecolor(BG)
        ax.tick_params(colors="#94a3b8")
        for sp in ax.spines.values(): sp.set_edgecolor("#1e3352")
        ax.invert_yaxis()
        ax.grid(True, axis="x", color="#1e3352", lw=0.4)

    ax1.barh(depths, em_vals, height=0.9, color="#38bdf8", alpha=0.85)
    ax1.set_xlabel("Em (MPa)", color="#94a3b8", fontsize=8)
    ax1.set_ylabel("Profondeur (m)", color="#94a3b8", fontsize=8)
    ax1.set_title("Module Em", color="#e2e8f0", fontsize=8)

    ax2.barh(depths, pl_vals, height=0.9, color="#ef4444", alpha=0.85)
    ax2.set_xlabel("Pl (MPa)", color="#94a3b8", fontsize=8)
    ax2.set_title("Pression limite Pl", color="#e2e8f0", fontsize=8)

    for i, (d, c) in enumerate(zip(depths, cols)):
        thick = depths[i+1]-d if i+1 < len(depths) else 2.0
        ax3.barh(d+thick/2, 1, height=thick, color=c, alpha=0.85)
    ax3.set_xlim(0,1); ax3.set_xticks([])
    ax3.set_title("Lithologie", color="#e2e8f0", fontsize=8)
    for i,(d,st) in enumerate(zip(depths, types)):
        ax3.text(0.5, d, str(st)[:18], ha="center", va="bottom",
                 color="white", fontsize=5)

    sond = getattr(profile, "sondage", "")
    fig.suptitle(f"Profil geotechnique — {sond}", color="#e2e8f0", fontsize=10)
    fig.tight_layout()
    return _fig_to_image(fig)


def _draw_section(cleaned_list, params_list, boreholes) -> Optional[Image]:
    if not boreholes:
        return None
    bh_map = {bh.get("name","BH"): bh.get("x_m", i*10.0)
              for i, bh in enumerate(boreholes)}
    BG = "#0b0e17"
    fig, ax = plt.subplots(figsize=(12, 6), facecolor=BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors="#94a3b8")
    for sp in ax.spines.values(): sp.set_edgecolor("#1e3352")

    from collections import defaultdict
    by_sond  = defaultdict(list)
    par_map  = {p.sheet_name: p for p in params_list}
    for c in cleaned_list:
        sond = (c.meta.ref_sondage or "SP")
        bx   = bh_map.get(sond, 0.0)
        p    = par_map.get(c.sheet_name)
        if c.depth_m is not None:
            by_sond[sond].append((bx, c.depth_m,
                                  p.sol_color if p else "#888",
                                  p.sol_type  if p else "?"))
    for sond, items in by_sond.items():
        its = sorted(items, key=lambda x: x[1])
        for i,(bx,d,col,stype) in enumerate(its):
            thick = its[i+1][1]-d if i+1 < len(its) else 2.0
            rect = mpatches.Rectangle((bx-0.8,-d-thick),1.6,thick,
                                       facecolor=col,edgecolor="#334155",alpha=0.85)
            ax.add_patch(rect)
            ax.text(bx,-(d+thick/2),str(stype)[:12],
                    ha="center",va="center",color="white",fontsize=5)
        ax.text(its[0][0], 0.3, sond, ha="center", color="#38bdf8", fontsize=8)

    snames = list(by_sond.keys())
    if len(snames) >= 2:
        for i in range(len(snames)-1):
            s1 = by_sond[snames[i]]; s2 = by_sond[snames[i+1]]
            for i1 in s1:
                for i2 in s2:
                    if i1[3] == i2[3]:
                        ax.plot([i1[0]+0.8,i2[0]-0.8],[-i1[1],-i2[1]],
                                color="#ffffff18",lw=0.7,ls="--")
    all_d = [it[1] for items in by_sond.values() for it in items]
    maxd  = max(all_d)+2 if all_d else 10
    bh_xs = list(bh_map.values())
    ax.set_ylim(-maxd,1)
    ax.set_xlim(min(bh_xs)-3 if bh_xs else -3, max(bh_xs)+3 if bh_xs else 3)
    ax.set_xlabel("Distance (m)",    color="#94a3b8")
    ax.set_ylabel("Profondeur (m)",  color="#94a3b8")

    try:
        from .calculator import SOL_CLASSES
        patches = [mpatches.Patch(color=s[5], label=s[4][:22]) for s in SOL_CLASSES]
        ax.legend(handles=patches, fontsize=5, facecolor="#111827",
                  labelcolor="white", loc="lower right", ncol=2)
    except Exception:
        pass

    ax.set_title("Coupe geologique schematique (NF P 94-110)", color="#e2e8f0", fontsize=10)
    fig.tight_layout()
    return _fig_to_image(fig)


# ─── En-tete SETRAF GABON ─────────────────────────────────────────────────────
def _setraf_header(report_ref: str = "", date_str: str = "") -> Table:
    """Genere l en-tête SETRAF GABON pour chaque page (cover)."""
    S = _styles()

    logo_obj = _logo_img(height_cm=1.35, max_width_cm=4.8)
    if logo_obj:
        logo_cell = [
            logo_obj,
            Paragraph("Bureau d'etudes Geotechniques", ParagraphStyle("L3",
                fontName="Helvetica-Oblique", fontSize=8, textColor=C_MGRAY,
                spaceAfter=0, leading=10)),
            Paragraph("Port-Gentil — En face du Stade PERENCO — Gabon", ParagraphStyle("L4",
                fontName="Helvetica", fontSize=7, textColor=C_MGRAY,
                spaceAfter=0, leading=9)),
        ]
    else:
        logo_cell = [
            Paragraph("SETRAF", ParagraphStyle("L1", fontName="Helvetica-Bold",
                fontSize=26, textColor=C_SKY, spaceAfter=0, leading=28)),
            Paragraph("GABON", ParagraphStyle("L2", fontName="Helvetica-Bold",
                fontSize=16, textColor=C_GOLD, spaceAfter=0, leading=18)),
            Paragraph("Bureau d'etudes Geotechniques", ParagraphStyle("L3",
                fontName="Helvetica-Oblique", fontSize=8, textColor=C_MGRAY,
                spaceAfter=0, leading=10)),
            Paragraph("Port-Gentil — En face du Stade PERENCO — Gabon", ParagraphStyle("L4",
                fontName="Helvetica", fontSize=7, textColor=C_MGRAY,
                spaceAfter=0, leading=9)),
        ]

    ref_cell = [
        Paragraph("RAPPORT GEOTECHNIQUE", ParagraphStyle("R1",
            fontName="Helvetica-Bold", fontSize=9, textColor=C_LGRAY,
            alignment=TA_RIGHT, spaceAfter=2)),
        Paragraph(f"Ref : {report_ref or 'RPT-2026'}", ParagraphStyle("R2",
            fontName="Helvetica-Bold", fontSize=8, textColor=C_GOLD,
            alignment=TA_RIGHT, spaceAfter=2)),
        Paragraph(f"Date : {date_str or datetime.date.today().strftime('%d/%m/%Y')}",
            ParagraphStyle("R3", fontName="Helvetica", fontSize=8,
            textColor=C_LGRAY, alignment=TA_RIGHT, spaceAfter=0)),
        Paragraph("NF P 94-110 | Eurocode 7 | ISO 22476-4",
            ParagraphStyle("R4", fontName="Helvetica-Oblique", fontSize=7,
            textColor=C_MGRAY, alignment=TA_RIGHT, spaceAfter=0)),
    ]

    t = Table([[logo_cell, ref_cell]],
              colWidths=[PAGE_W - 2*MARGIN_H - 5*cm, 5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), C_NAVY),
        ("PADDING",     (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (0,-1),  16),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW",   (0,0), (-1,0),  2, C_ORANGE),
    ]))
    return t


def _section_heading(story: list, number: str, title: str, sub: str = ""):
    S = _styles()
    story.append(Spacer(1, 0.3*cm))
    story.append(_hr(C_SKY, 1.5))
    story.append(Paragraph(f"{number}. {title}", S["h1"]))
    if sub:
        story.append(Paragraph(sub, S["small"]))
    story.append(_hr(C_DGRAY, 0.4))


# ─── Table des matieres ───────────────────────────────────────────────────────
def _toc_section(story, cleaned_list, has_profile, has_section, has_ai):
    S = _styles()
    story.append(Paragraph("TABLE DES MATIERES", S["toc_title"]))
    story.append(_hr(C_SKY, 1))
    story.append(Spacer(1, 0.2*cm))

    items = [
        ("1.", "Cadre normatif et references reglementaires"),
        ("2.", "Resume synoptique des parametres pressiometriques"),
    ]
    n = 3
    if has_profile:
        items.append((f"{n}.", "Profil geotechnique")); n+=1
    if has_section:
        items.append((f"{n}.", "Coupe geologique schematique")); n+=1
    items.append((f"{n}.", f"Fiches d essais detaillees ({len(cleaned_list)} essais)")); n+=1
    items.append((f"{n}.", "Interpretations et recommandations")); n+=1
    if has_ai:
        items.append((f"{n}.", "Synthese IA KIBALI (geophysique)")); n+=1
    items.append((f"{n}.", "Conclusions et synthese geotechnique"))

    toc_rows = [
        [Paragraph(num, ParagraphStyle("ti", fontName="Helvetica-Bold",
            fontSize=9, textColor=C_GOLD)),
         Paragraph(txt, S["toc_item"])]
        for num, txt in items
    ]
    tbl = Table(toc_rows, colWidths=[1.2*cm, PAGE_W-2*MARGIN_H-1.2*cm])
    tbl.setStyle(TableStyle([
        ("VALIGN",      (0,0), (-1,-1), "TOP"),
        ("PADDING",     (0,0), (-1,-1), 3),
        ("LINEBELOW",   (0,0), (-1,-1), 0.3, C_BORDER),
    ]))
    story.append(tbl)
    story.append(PageBreak())


# ─── Section normative ────────────────────────────────────────────────────────
def _norms_section(story, web_ctx: dict):
    S = _styles()
    _section_heading(story, "1", "Cadre normatif et references reglementaires",
                     "NF P 94-110 | Eurocode 7 | ISO 22476-4 | ASTM D4719")

    # Tableau des normes applicables
    rows = [["Reference", "Titre", "Organisme"]]
    for ref, titre, org in NORMATIVE_REFS:
        rows.append([ref, titre, org])
    t = Table(rows, colWidths=[4.5*cm, 10.5*cm, 2.5*cm])
    ts = _tbl_style()
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    # Tableau NC/SC
    story.append(Paragraph("Classification NC / SC (NF P 94-110, Tab. 3)", S["h2"]))
    rows2 = [["Statut", "Critere Em/Pl", "Signification"]]
    for st, cr, sg in NC_SC_TABLE:
        rows2.append([st, cr, sg])
    t2 = Table(rows2, colWidths=[4.5*cm, 3*cm, 10*cm])
    t2.setStyle(_tbl_style())
    story.append(t2)
    story.append(Spacer(1, 0.4*cm))

    # Formules clefs
    story.append(Paragraph("Formules de calcul Ménard — Résumé", S["h2"]))
    for key, d in MENARD_FORMULAS.items():
        story.append(Paragraph(f"<b>{d['formula']}</b>", S["body_b"]))
        story.append(Paragraph(f"Ref : {d['ref']} — {d['note']}", S["ref"]))

    story.append(Spacer(1, 0.4*cm))

    # Facteurs rhéologiques
    story.append(Paragraph("Facteurs rheologiques alpha (Ménard 1962)", S["h2"]))
    rh_rows = [["Type de sol", "alpha"]] + [
        [k, str(v)] for k, v in RHEOLOGICAL_ALPHA.items()
    ]
    t3 = Table(rh_rows, colWidths=[12*cm, 2*cm])
    t3.setStyle(_tbl_style())
    story.append(t3)

    # Enrichissement web
    if web_ctx and web_ctx.get("snippets"):
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("Sources normatives complementaires (enrichissement web)", S["h2"]))
        for sn in web_ctx["snippets"][:4]:
            story.append(Paragraph(
                f"<b>{sn.get('title','')}</b>",
                S["body_b"]))
            story.append(Paragraph(sn.get("text",""), S["small"]))
            if sn.get("url"):
                story.append(Paragraph(sn["url"], S["ref"]))
            story.append(Spacer(1, 0.15*cm))

    story.append(PageBreak())


# ─── Section recommandations ──────────────────────────────────────────────────
def _recommendations(params: PressiometricParams) -> List[str]:
    recs = []
    em = params.Em_MPa  or 0
    pl = params.Pl_MPa  or 0
    pf = params.Pf_MPa  or 0
    ratio = params.ratio_Em_Pl or 0
    q = params.qualite or "D"

    if q == "D":
        recs.append("ATTENTION : Qualite essai D — Resultat non representatif. Reprise de l essai recommandee.")
    if em < 2.0:
        recs.append(f"Em tres faible ({em:.1f} MPa) — Sol tres compressible. Fondation directe deconseillee. Envisager renforcement (colonnes, pieux).")
    elif em < 5.0:
        recs.append(f"Em faible ({em:.1f} MPa) — Sol peu portant. Semelles filantes avec avant-metrage. Verifier tassements selon NF P 94-261.")
    if pl < 0.3:
        recs.append(f"Pl tres faible ({pl:.3f} MPa) — Risque de fluage sous charge. Prevoir essai de fluage complementaire.")
    if ratio < 5:
        recs.append(f"Em/Pl = {ratio:.1f} — Sol remanié ou perturbé. Verifier protocole forage et repassage eventuel.")
    elif ratio > 20:
        recs.append(f"Em/Pl = {ratio:.1f} — Sol fortement surconsolide. Alpha=1.0 recommandé (roche alteree ou grave).")
    elif ratio <= 12:
        recs.append(f"Em/Pl = {ratio:.1f} — Sol NC (normalement consolide). Alpha = 0.33-0.50 selon classification.")
    else:
        recs.append(f"Em/Pl = {ratio:.1f} — Sol SC (surconsolide). Alpha = 0.50-0.67. Capacite portante favorable.")

    if pf and pl and pf > 0:
        if (pl/pf) > 2.5:
            recs.append(f"Rapport Pl/Pf = {pl/pf:.1f} — Zone plastique large, essai de bonne qualite.")
    if not params.is_coherent and params.coherence_checks:
        for chk in params.coherence_checks:
            if not chk.ok:
                recs.append(f"Incoherence : {chk.message}")
    return recs


def _recs_section(story, cleaned_list, params_list):
    S = _styles()
    par_map = {p.sheet_name: p for p in params_list}
    _section_heading(story, "X", "Interpretations et recommandations geotechniques",
        "Bases sur NF P 94-110, Eurocode 7 (EN 1997-1) et NF P 94-261")
    for c in sorted(cleaned_list, key=lambda x: x.depth_m or 0):
        p = par_map.get(c.sheet_name)
        if not p:
            continue
        dep = f"{c.depth_m} m" if c.depth_m else "?"
        story.append(Paragraph(f"{c.sheet_name} — prof. {dep}", S["h3"]))
        recs = _recommendations(p)
        if recs:
            for r in recs:
                bullet = "warn" if ("ATTENTION" in r or "non representatif" in r
                                    or "Incoherence" in r or "faible" in r.lower()) else "body"
                story.append(Paragraph(f"   > {r}", S[bullet]))
        else:
            story.append(Paragraph("   Essai conforme — Pas de recommandation particuliere.", S["good"]))
        story.append(Spacer(1, 0.15*cm))
    story.append(PageBreak())


# ─── Conclusions ─────────────────────────────────────────────────────────────
def _conclusions_section(story, cleaned_list, params_list, project_title, sondage):
    S = _styles()
    n_total = len(params_list)
    q_count = {"A":0, "B":0, "C":0, "D":0}
    em_vals = []; pl_vals = []; good_params = []
    for p in params_list:
        if p.qualite in q_count: q_count[p.qualite] += 1
        if p.Em_MPa: em_vals.append(p.Em_MPa)
        if p.Pl_MPa: pl_vals.append(p.Pl_MPa)
        if p.qualite in ("A","B"): good_params.append(p)

    em_moy = sum(em_vals)/len(em_vals) if em_vals else 0
    pl_moy = sum(pl_vals)/len(pl_vals) if pl_vals else 0

    _section_heading(story, "X", "Conclusions et synthese geotechnique",
        f"Campagne : {project_title}")

    story.append(Paragraph(
        f"La presente campagne pressiometrique a ete realisee conformement a la norme "
        f"NF P 94-110 (essai pressiometrique Ménard). Elle comprend {n_total} essai(s) "
        f"sur le sondage {sondage}.",
        S["body"]))
    story.append(Spacer(1, 0.2*cm))

    # Tableau qualite
    q_rows = [["Qualite", "Nb essais", "Signification NF P 94-110"]]
    q_desc = {"A":"Excellent — zero anomalie","B":"Bon — anomalie mineure acceptable",
               "C":"Acceptable — a exploiter avec prudence","D":"Mauvais — non representatif"}
    for q,n in q_count.items():
        if n > 0:
            q_rows.append([q, str(n), q_desc.get(q,"")])
    t = Table(q_rows, colWidths=[2*cm, 2.5*cm, PAGE_W-2*MARGIN_H-4.5*cm])
    ts = _tbl_style()
    qcols = {"A":"#22c55e","B":"#fbbf24","C":"#f97316","D":"#ef4444"}
    for i2, q2 in enumerate([r[0] for r in q_rows[1:]], start=1):
        ts.add("BACKGROUND",(0,i2),(0,i2), colors.HexColor(qcols.get(q2,"#888")))
        ts.add("TEXTCOLOR",  (0,i2),(0,i2), colors.white)
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph(
        f"Module pressiometrique Em moyen : <b>{em_moy:.1f} MPa</b>  —  "
        f"Pression limite Pl moyenne : <b>{pl_moy:.3f} MPa</b>",
        S["body_b"]))
    story.append(Spacer(1, 0.15*cm))

    if good_params:
        best = max(good_params, key=lambda p: p.Em_MPa or 0)
        story.append(Paragraph(
            f"Meilleur essai : {best.sheet_name} a {best.depth_m} m — Em = {best.Em_MPa} MPa, "
            f"Pl = {best.Pl_MPa} MPa, Qualite {best.qualite}.",
            S["body"]))

    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Toutes les interpretations sont realisees conformement a la norme NF P 94-110, "
        "a l Eurocode 7 (EN 1997-1) et a la norme ISO 22476-4. Les calculs de fondations "
        "devront suivre la methodologie de la norme NF P 94-261 (fondations superficielles) "
        "ou du Fascicule 62 Titre V.",
        S["body"]))

    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        f"Rapport etabli par SETRAF GABON — {datetime.date.today().strftime('%d/%m/%Y')}",
        S["ref"]))
    story.append(_hr(C_ORANGE, 1.5))


# ─── Fonction principale ──────────────────────────────────────────────────────
def generate_pdf(
    parsed: ParsedFile,
    cleaned_list: List[CleanedEssai],
    params_list: List[PressiometricParams],
    profile: Optional[ProfileData],
    boreholes: list,
    project_title:    str  = "",
    engineer:         str  = "",
    include_raw:      bool = True,
    include_curves:   bool = True,
    ai_summary:       str  = "",
    company:          str  = "SETRAF GABON",
    report_ref:       str  = "",
    location:         str  = "",
    use_web_norms:    bool = False,
) -> bytes:
    """Genere le rapport PDF complet SETRAF GABON. Retourne bytes."""

    # ── Meta
    today     = datetime.date.today()
    date_str  = today.strftime("%d/%m/%Y")
    year      = today.year
    par_map   = {p.sheet_name: p for p in params_list}

    # Auto-titre si vide
    if not project_title:
        sondages   = list({c.meta.ref_sondage for c in cleaned_list if c.meta.ref_sondage})
        sond_str   = " / ".join(sondages) if sondages else ""
        loc_meta   = next((c.meta.localisation for c in cleaned_list if c.meta.localisation), "")
        project_title = f"Essais Pressiometriques Menard — {sond_str or loc_meta or 'Campagne ' + str(year)}"

    if not report_ref:
        report_ref = f"SETRAF-{year}-RPT-{today.strftime('%m%d')}-001"

    sondage = next((c.meta.ref_sondage for c in cleaned_list if c.meta.ref_sondage), "")
    loc     = location or next((c.meta.localisation for c in cleaned_list if c.meta.localisation), "Gabon")
    has_profile = bool(profile)
    has_section = len(boreholes) >= 1
    has_ai      = bool(ai_summary)
    S           = _styles()

    # Web enrichment
    web_ctx = {}
    if use_web_norms:
        try:
            web_ctx = get_web_normative_context(f"{project_title} {sondage}")
        except Exception:
            web_ctx = {}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=MARGIN_H, leftMargin=MARGIN_H,
        topMargin=MARGIN_V,   bottomMargin=MARGIN_V,
    )
    story = []

    # ══════════════════════════════════════════════════════════════
    # PAGE DE GARDE
    # ══════════════════════════════════════════════════════════════
    # Logo SETRAF GABON centré en haut
    logo_cover = _logo_img(height_cm=3.0, max_width_cm=9.0)
    if logo_cover:
        logo_cover.hAlign = "CENTER"
        story.append(Spacer(1, 0.5*cm))
        story.append(logo_cover)
        story.append(Spacer(1, 0.35*cm))
        story.append(_hr(C_ORANGE, 2))
        story.append(Spacer(1, 0.25*cm))
    story.append(_setraf_header(report_ref, date_str))
    story.append(Spacer(1, 1.5*cm))

    # Titre principal
    story.append(Paragraph("RAPPORT D'ESSAIS PRESSIOMETRIQUE", S["cover_title"]))
    story.append(Paragraph("Methode Menard — NF P 94-110 / Eurocode 7", S["cover_sub"]))
    story.append(Spacer(1, 0.4*cm))
    story.append(_hr(C_ORANGE, 2))
    story.append(Spacer(1, 0.4*cm))

    # Titre projet
    story.append(Paragraph(project_title, ParagraphStyle("ptitle",
        fontName="Helvetica-Bold", fontSize=15, textColor=C_GOLD,
        alignment=TA_CENTER, spaceAfter=6)))
    story.append(Spacer(1, 0.6*cm))

    # Tableau metadonnees
    first_meta = (list(parsed.essais.values())[0].meta if parsed.essais else None)
    meta_rows = [
        ["Fichier source",        parsed.filename],
        ["Projet / Affaire",      first_meta.projet or project_title if first_meta else project_title],
        ["Localisation / Site",   loc],
        ["Sondage(s) references", sondage],
        ["Nombre d essais",       str(len(cleaned_list))],
        ["Ingenieur responsable", engineer],
        ["Date du rapport",       date_str],
        ["Reference rapport",     report_ref],
        ["Norme principale",      "NF P 94-110 (essai pressiometrique Menard)"],
        ["Norme calculs",         "Eurocode 7 EN 1997-1 | NF P 94-261 | ISO 22476-4"],
        ["Entreprise",            company],
    ]
    mt = Table(meta_rows, colWidths=[5.5*cm, PAGE_W-2*MARGIN_H-5.5*cm])
    mts = TableStyle([
        ("BACKGROUND",   (0,0),  (0,-1),  C_HEADER),
        ("BACKGROUND",   (1,0),  (1,-1),  C_ROW0),
        ("TEXTCOLOR",    (0,0),  (0,-1),  C_SKY),
        ("TEXTCOLOR",    (1,0),  (1,-1),  C_LGRAY),
        ("FONTNAME",     (0,0),  (0,-1),  "Helvetica-Bold"),
        ("FONTNAME",     (1,0),  (1,-1),  "Helvetica"),
        ("FONTSIZE",     (0,0),  (-1,-1), 8.5),
        ("GRID",         (0,0),  (-1,-1), 0.4, C_BORDER),
        ("PADDING",      (0,0),  (-1,-1), 5),
        ("LEFTPADDING",  (0,0),  (0,-1),  10),
        ("ROWBACKGROUNDS",(1,0),(1,-1),  [C_ROW0, C_ROW1]),
        ("VALIGN",       (0,0),  (-1,-1), "MIDDLE"),
    ])
    mt.setStyle(mts)
    story.append(mt)
    story.append(Spacer(1, 0.8*cm))

    # Confidentialite
    story.append(Paragraph(
        "Document confidentiel — Propriete de SETRAF GABON. "
        "Toute reproduction partielle ou totale est soumise a autorisation ecrite.",
        S["small"]))
    story.append(_hr(C_ORANGE, 1))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # TABLE DES MATIERES
    # ══════════════════════════════════════════════════════════════
    _toc_section(story, cleaned_list, has_profile, has_section, has_ai)

    # ══════════════════════════════════════════════════════════════
    # 1. CADRE NORMATIF
    # ══════════════════════════════════════════════════════════════
    _norms_section(story, web_ctx)

    # ══════════════════════════════════════════════════════════════
    # 2. TABLEAU SYNOPTIQUE
    # ══════════════════════════════════════════════════════════════
    _section_heading(story, "2", "Resume synoptique des parametres pressiometriques",
        "Classes selon NF P 94-110 | Qualites A-D")
    hdrs = ["Essai", "Prof.(m)", "Em(MPa)", "Pf(MPa)", "Pl(MPa)", "Em/Pl",
            "Type sol", "NC/SC", "Qual."]
    rows_tab = [hdrs]
    for c in sorted(cleaned_list, key=lambda x: x.depth_m or 0):
        p = par_map.get(c.sheet_name)
        if not p: continue
        rows_tab.append([
            c.sheet_name[:14],
            str(c.depth_m) if c.depth_m is not None else "?",
            f"{p.Em_MPa:.1f}"      if p.Em_MPa     else "—",
            f"{p.Pf_MPa:.3f}"      if p.Pf_MPa     else "—",
            f"{p.Pl_MPa:.3f}"      if p.Pl_MPa     else "—",
            f"{p.ratio_Em_Pl:.1f}" if p.ratio_Em_Pl else "—",
            p.sol_type[:22],
            p.nc_status[:18],
            p.qualite or "?",
        ])
    cw3 = [3*cm,1.6*cm,1.8*cm,1.8*cm,1.8*cm,1.4*cm,4*cm,3*cm,1.2*cm]
    tbl_syn = Table(rows_tab, colWidths=cw3)
    ts3 = _tbl_style()
    qcols = {"A":C_GREEN,"B":C_GOLD,"C":C_ORANGE,"D":C_RED}
    for i2, row in enumerate(rows_tab[1:], start=1):
        q2 = row[-1]
        if q2 in qcols:
            ts3.add("BACKGROUND", (-1,i2), (-1,i2), qcols[q2])
            ts3.add("TEXTCOLOR",  (-1,i2), (-1,i2), C_NAVY)
    tbl_syn.setStyle(ts3)
    story.append(tbl_syn)
    story.append(Spacer(1, 0.5*cm))

    # Legende qualite
    leg_data = [["A — Excellent","B — Bon","C — Acceptable","D — Mauvais"]]
    lt = Table(leg_data, colWidths=[(PAGE_W-2*MARGIN_H)/4]*4)
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(0,0), C_GREEN),
        ("BACKGROUND", (1,0),(1,0), C_GOLD),
        ("BACKGROUND", (2,0),(2,0), C_ORANGE),
        ("BACKGROUND", (3,0),(3,0), C_RED),
        ("TEXTCOLOR",  (0,0),(-1,0), C_NAVY),
        ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0),(-1,0), 7.5),
        ("ALIGN",      (0,0),(-1,0), "CENTER"),
        ("PADDING",    (0,0),(-1,0), 4),
    ]))
    story.append(lt)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # 3. PROFIL GEOTECHNIQUE (si disponible)
    # ══════════════════════════════════════════════════════════════
    sec_n = 3
    if has_profile:
        _section_heading(story, str(sec_n), "Profil geotechnique",
            "Em et Pl en fonction de la profondeur — NF P 94-110")
        img = _draw_profile(profile)
        if img: story.append(img)
        story.append(PageBreak())
        sec_n += 1

    # ══════════════════════════════════════════════════════════════
    # 4. COUPE GEOLOGIQUE (si sondages multiples)
    # ══════════════════════════════════════════════════════════════
    if has_section:
        _section_heading(story, str(sec_n), "Coupe geologique schematique",
            "Correlation entre sondages — NF P 94-110 | Eurocode 7")
        img2 = _draw_section(cleaned_list, params_list, boreholes)
        if img2: story.append(img2)
        story.append(PageBreak())
        sec_n += 1

    # ══════════════════════════════════════════════════════════════
    # 5. FICHES D ESSAIS
    # ══════════════════════════════════════════════════════════════
    _section_heading(story, str(sec_n), f"Fiches d essais detaillees — {len(cleaned_list)} essai(s)",
        "Conformement a NF P 94-110 §8 et ISO 22476-4 §9")
    sec_n += 1

    for ess_n, c in enumerate(
        sorted(cleaned_list, key=lambda x: x.depth_m or 0), start=1
    ):
        p = par_map.get(c.sheet_name)
        dep = f"{c.depth_m} m" if c.depth_m else "?"
        qual = p.qualite if p else "?"
        qc = qcols.get(qual, C_MGRAY)

        # Titre fiche
        story.append(Spacer(1, 0.3*cm))
        fiche_hdr = Table([[
            Paragraph(f"Fiche {ess_n} — {c.sheet_name}  (prof. {dep})",
                ParagraphStyle("fh", fontName="Helvetica-Bold", fontSize=10,
                    textColor=C_WHITE, spaceAfter=0)),
            Paragraph(f"Qualite : {qual}",
                ParagraphStyle("fq", fontName="Helvetica-Bold", fontSize=10,
                    textColor=C_NAVY, alignment=TA_RIGHT, spaceAfter=0)),
        ]], colWidths=[PAGE_W-2*MARGIN_H-2.5*cm, 2.5*cm])
        fiche_hdr.setStyle(TableStyle([
            ("BACKGROUND",  (0,0),(0,0), C_NAVY),
            ("BACKGROUND",  (1,0),(1,0), qc),
            ("PADDING",     (0,0),(-1,-1), 6),
            ("LEFTPADDING", (0,0),(0,0),  10),
            ("VALIGN",      (0,0),(-1,-1), "MIDDLE"),
            ("LINEBELOW",   (0,0),(-1,0), 2, C_ORANGE),
        ]))
        story.append(fiche_hdr)
        story.append(Spacer(1, 0.2*cm))

        # Metadonnees essai
        m = c.meta
        meta_e = [
            ["Sondage",       m.ref_sondage  or "—",  "Ref essai",  m.ref_essai    or "—"],
            ["Localisation",  m.localisation or "—",  "Technique",  m.technique    or "—"],
            ["Etalonnage",    m.ref_etalonnage or "—","Calibrage",   m.ref_calibrage or "—"],
            ["Pression diff", f"{m.pression_diff_bar:.3f} bar", "Outil forage", m.outil_forage or "—"],
            ["Date essai",    m.date         or "—",  "Type tubul.", m.type_tubulure or "—"],
        ]
        mt_e = Table(meta_e, colWidths=[2.5*cm,5*cm,2.5*cm,5.5*cm])
        mt_e.setStyle(_tbl_style())
        story.append(mt_e)
        story.append(Spacer(1, 0.25*cm))

        # Parametres calcules
        if p:
            story.append(Paragraph("Parametres pressiometriques calcules (NF P 94-110 §8)", S["h3"]))
            pcalc = [
                ["Parametre","Valeur","Parametre","Valeur"],
                ["Em (MPa)",       f"{p.Em_MPa:.2f}"      if p.Em_MPa     else "—",
                 "Pf (MPa)",       f"{p.Pf_MPa:.3f}"      if p.Pf_MPa     else "—"],
                ["Pl (MPa)",       f"{p.Pl_MPa:.3f}"      if p.Pl_MPa     else "—",
                 "Pl* (MPa)",      f"{p.Pl_star_MPa:.3f}" if p.Pl_star_MPa else "—"],
                ["Em/Pl",          f"{p.ratio_Em_Pl:.1f}" if p.ratio_Em_Pl else "—",
                 "Qualite essai",  p.qualite or "?"],
                ["Type de sol",    p.sol_type[:28],
                 "Statut NC/SC",   p.nc_status],
                ["Coherence",      "OK" if p.is_coherent else "NON CONFORME",
                 "Zone elastique", f"{p.P_elastic_min_MPa:.3f} — {p.Pf_MPa:.3f} MPa"
                 if (p.P_elastic_min_MPa and p.Pf_MPa) else "—"],
            ]
            ptbl = Table(pcalc, colWidths=[3*cm,4*cm,3*cm,4.5*cm])
            pts = _tbl_style()
            # Coloriser coherence
            pts.add("TEXTCOLOR", (1,5),(1,5), C_GREEN if p.is_coherent else C_RED)
            # Coloriser qualite
            pts.add("BACKGROUND",(1,3),(1,3), qc)
            pts.add("TEXTCOLOR", (1,3),(1,3), C_NAVY)
            ptbl.setStyle(pts)
            story.append(ptbl)
            story.append(Spacer(1, 0.15*cm))

            # Notes
            for note in (p.notes or []):
                story.append(Paragraph(f"   Note : {note}", S["small"]))
            # Checks coherence
            for chk in (p.coherence_checks or []):
                icon = "OK" if chk.ok else "ECHEC"
                clr  = S["small"] if chk.ok else S["warn"]
                story.append(Paragraph(f"   [{icon}] {chk.message}", clr))
            story.append(Spacer(1, 0.15*cm))

        # Anomalies
        if c.anomalies:
            story.append(Paragraph("Anomalies detectees (NF P 94-110 §7)", S["h3"]))
            anom_rows = [["Palier","Type","Description","Severite"]] + [
                [str(a.palier), a.type, a.description[:55], a.severity]
                for a in c.anomalies
            ]
            at = Table(anom_rows, colWidths=[1.5*cm,2.8*cm,9.5*cm,1.8*cm])
            ats = _tbl_style()
            for i2,a in enumerate(c.anomalies, start=1):
                ce = C_RED if a.severity=="error" else C_AMBER
                ats.add("BACKGROUND", (-1,i2),(-1,i2), ce)
                ats.add("TEXTCOLOR",  (-1,i2),(-1,i2), C_NAVY)
            at.setStyle(ats)
            story.append(at)
            story.append(Spacer(1, 0.15*cm))

        # Tableau donnees tabulees
        if include_raw and c.points:
            story.append(Paragraph(
                "Donnees corrigees et lissees (Savitzky-Golay, calibrage, etalonnage)",
                S["h3"]))
            dh = ["Palier","P_brut(MPa)","P_corr(MPa)","V30_c(cm3)",
                  "V60_c(cm3)","Vm_c(cm3)","Creep"]
            drows = [dh] + [
                [str(pt.palier),
                 f"{pt.P60_raw_MPa:.4f}",
                 f"{pt.P60_corr_MPa:.4f}",
                 f"{pt.V30_corr_cm3:.1f}" if pt.V30_corr_cm3 else "—",
                 f"{pt.V60_corr_cm3:.1f}" if pt.V60_corr_cm3 else "—",
                 f"{pt.Vm_corr_cm3:.1f}"  if pt.Vm_corr_cm3  else "—",
                 f"{pt.creep_ratio:.3f}"  if pt.creep_ratio   else "—"]
                for pt in c.points
            ]
            cw5 = [1.2*cm,2.2*cm,2.2*cm,2.2*cm,2.2*cm,2.2*cm,1.8*cm]
            dts_t = Table(drows, colWidths=cw5)
            dts = _tbl_style()
            for i2,pt in enumerate(c.points, start=1):
                if pt.anomalie:
                    dts.add("BACKGROUND", (0,i2),(-1,i2), colors.HexColor("#ef444420"))
            dts_t.setStyle(dts)
            story.append(dts_t)
            story.append(Spacer(1, 0.25*cm))

        # Courbe P-V
        if include_curves and p:
            story.append(Paragraph(
                "Courbe Pression-Volume (P-V) — Methode Menard NF P 94-110",
                S["h3"]))
            img_pv = _draw_curve_pv(c, p)
            if img_pv:
                story.append(img_pv)

        story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # RECOMMANDATIONS
    # ══════════════════════════════════════════════════════════════
    _recs_section(story, cleaned_list, params_list)

    # ══════════════════════════════════════════════════════════════
    # SYNTHESE IA KIBALI
    # ══════════════════════════════════════════════════════════════
    if ai_summary:
        _section_heading(story, str(sec_n), "Synthese IA KIBALI",
            "Analyse geophysique par intelligence artificielle (modele Ménard-LoRA)")
        story.append(Paragraph(ai_summary, S["body"]))
        story.append(PageBreak())
        sec_n += 1

    # ══════════════════════════════════════════════════════════════
    # CONCLUSIONS
    # ══════════════════════════════════════════════════════════════
    _conclusions_section(story, cleaned_list, params_list, project_title, sondage)

    doc.build(story)
    buf.seek(0)
    return buf.read()
