"""
frontend/icon_factory.py — Icône et logo SETRAF GABON / PressiomètreIA v2
==========================================================================
Génération 100 % Qt (QPainter) — aucune dépendance PIL / Pillow.

Produits :
  • get_app_icon()            → QIcon multi-résolutions (16…256 px)
  • make_icon_pixmap(size)    → QPixmap de l'icône à une taille donnée
  • make_logo_banner(w, h)    → QPixmap bannière SETRAF pour la sidebar
  • ensure_ico_file(path)     → écrit un .ico Windows si absent
"""
from __future__ import annotations

import struct
from pathlib import Path

from PyQt6.QtCore  import Qt, QRectF, QPointF, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui   import (
    QPixmap, QIcon, QPainter, QColor, QPen, QBrush,
    QLinearGradient, QRadialGradient, QPainterPath, QFont,
)

# ─── Palette de marque SETRAF GABON ──────────────────────────────────────────
_NAVY    = "#050d1c"
_NAVY2   = "#0d1f38"
_NAVY3   = "#112040"
_BLUE    = "#1e3a5f"
_SKY     = "#38bdf8"
_SKY2    = "#7dd3fc"
_SKY3    = "#bae6fd"
_GOLD    = "#fbbf24"
_GOLD2   = "#fde68a"
_ORANGE  = "#f97316"
_WHITE   = "#e2e8f0"
_GRAY    = "#94a3b8"

# Strates géologiques (du haut vers le bas)
_STRATA = [
    ("#1e3a20", "#2a4e2c"),  # argile verte (proche surface)
    ("#2a1808", "#3e2610"),  # argile marron
    ("#3c2e10", "#58451a"),  # sablo-limoneux ocre
    ("#5a4630", "#78603e"),  # sable graveux beige
]


# ─── Icône principale ─────────────────────────────────────────────────────────

def make_icon_pixmap(size: int = 256) -> QPixmap:
    """
    Dessine l'icône PressiomètreIA / SETRAF avec QPainter.

    Design :
      - Fond marine arrondi avec dégradé
      - Strates géologiques dans le bas (45–92 %)
      - Sonde pressiométrique centrale (tube + cellule gonflée)
      - Grande lettre « P » en bleu ciel (coin haut gauche)
      - Badge « IA » en or (coin haut droit)
      - Bordure extérieure avec halo sky bleu
    """
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    s = float(size)
    pad = s * 0.055
    radius = s * 0.14

    bg_rect = QRectF(pad, pad, s - 2 * pad, s - 2 * pad)

    # ── 1. Fond dégradé (bleu marine) ─────────────────────────────────────
    grad_bg = QLinearGradient(s / 2, 0.0, s / 2, s)
    grad_bg.setColorAt(0.0, QColor(_NAVY3))
    grad_bg.setColorAt(1.0, QColor(_NAVY))
    p.setBrush(QBrush(grad_bg))
    p.setPen(QPen(QColor(_BLUE), max(1.0, s * 0.011)))
    p.drawRoundedRect(bg_rect, radius, radius)

    # ── 2. Strates géologiques (bas 47 %) — clippées au fond ──────────────
    clip = QPainterPath()
    clip.addRoundedRect(bg_rect, radius, radius)
    p.setClipPath(clip)

    y = s * 0.453
    fracs = [0.115, 0.115, 0.115, 0.145]
    for (c0, c1), frac in zip(_STRATA, fracs):
        h = frac * s
        sg = QLinearGradient(0.0, y, 0.0, y + h)
        sg.setColorAt(0.0, QColor(c0))
        sg.setColorAt(1.0, QColor(c1))
        p.setBrush(QBrush(sg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(pad, y, s - 2 * pad, h + 1))

        # petite ligne de séparation entre couches
        p.setPen(QPen(QColor("#ffffff18"), max(1, int(s * 0.004))))
        p.drawLine(QPointF(pad + 2, y), QPointF(s - pad - 2, y))
        p.setPen(Qt.PenStyle.NoPen)
        y += h

    p.setClipping(False)

    # ── 3. Tube de la sonde (ligne verticale, dégradé latéral) ────────────
    cx   = s * 0.5
    tw   = s * 0.065                     # largeur tube
    ttop = s * 0.17
    tbot = s * 0.925
    tube = QRectF(cx - tw / 2, ttop, tw, tbot - ttop)
    tg = QLinearGradient(cx - tw / 2, 0.0, cx + tw / 2, 0.0)
    tg.setColorAt(0.00, QColor("#0d2a45"))
    tg.setColorAt(0.40, QColor(_SKY2))
    tg.setColorAt(0.60, QColor(_SKY3))
    tg.setColorAt(1.00, QColor("#0d2a45"))
    p.setBrush(QBrush(tg))
    p.setPen(QPen(QColor(_SKY), max(1, int(s * 0.005))))
    p.drawRoundedRect(tube, tw * 0.5, tw * 0.5)

    # ── 4. Cellule pressiométrique (ovale expansé au centre) ──────────────
    ccy  = s * 0.575
    cw   = tw * 3.8
    ch   = s  * 0.235
    cell = QRectF(cx - cw / 2, ccy - ch / 2, cw, ch)
    rg = QRadialGradient(cx, ccy, cw * 0.5)
    rg.setColorAt(0.00, QColor(_SKY3))
    rg.setColorAt(0.30, QColor(_SKY))
    rg.setColorAt(0.75, QColor("#0ea5e9"))
    rg.setColorAt(1.00, QColor(_BLUE))
    p.setBrush(QBrush(rg))
    p.setPen(QPen(QColor(_SKY2), max(1, int(s * 0.010))))
    p.drawEllipse(cell)

    # halo autour de la cellule
    halo = QRectF(cx - cw * 0.75, ccy - ch * 0.75, cw * 1.5, ch * 1.5)
    hg = QRadialGradient(cx, ccy, cw * 0.75)
    hg.setColorAt(0.50, QColor("#38bdf830"))
    hg.setColorAt(1.00, QColor("#38bdf800"))
    p.setBrush(QBrush(hg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(halo)

    # ── 5. Lettre « P » (coin haut gauche) ────────────────────────────────
    fp = QFont("Segoe UI")
    fp.setWeight(QFont.Weight.Black)
    fp.setPixelSize(max(8, int(s * 0.22)))
    fp.setStyleHint(QFont.StyleHint.SansSerif)
    p.setFont(fp)
    # ombre légère
    p.setPen(QColor("#00000060"))
    p_rect = QRectF(pad + s * 0.025 + 1, pad + s * 0.025 + 2, s * 0.30, s * 0.28)
    p.drawText(p_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "P")
    # lettre
    p.setPen(QColor(_SKY))
    p_rect2 = QRectF(pad + s * 0.025, pad + s * 0.025, s * 0.30, s * 0.28)
    p.drawText(p_rect2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "P")

    # ── 6. Badge « IA » (coin haut droit) ────────────────────────────────
    bw = s * 0.27
    bh = s * 0.14
    bx = s - pad - bw - s * 0.025
    by = pad + s * 0.038
    badge = QRectF(bx, by, bw, bh)
    p.setBrush(QBrush(QColor("#fbbf2422")))
    p.setPen(QPen(QColor(_GOLD), max(1, int(s * 0.009))))
    p.drawRoundedRect(badge, s * 0.025, s * 0.025)

    fi = QFont("Segoe UI")
    fi.setWeight(QFont.Weight.Bold)
    fi.setPixelSize(max(6, int(s * 0.105)))
    fi.setStyleHint(QFont.StyleHint.SansSerif)
    p.setFont(fi)
    p.setPen(QColor(_GOLD))
    p.drawText(badge, Qt.AlignmentFlag.AlignCenter, "IA")

    # ── 7. Halo de bordure extérieure (glow sky bleu) ─────────────────────
    outer = QRectF(pad * 0.3, pad * 0.3, s - pad * 0.6, s - pad * 0.6)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#38bdf828"), max(2, int(s * 0.028))))
    p.drawRoundedRect(outer, radius * 1.18, radius * 1.18)

    p.end()
    return pix


def get_app_icon() -> QIcon:
    """Retourne l'icône de l'application avec plusieurs résolutions (16 – 256 px)."""
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_icon_pixmap(sz), QIcon.Mode.Normal, QIcon.State.Off)
    return icon


# ─── Bannière logo pour la sidebar ───────────────────────────────────────────

def make_logo_banner(width: int = 228, height: int = 72) -> QPixmap:
    """
    Génère le bandeau logo SETRAF GABON pour la barre latérale.

    Mise en page :
      [ mini-icône 44 px ] | SETRAF  (sky bleu, gras)
                           | GABON   (or, gras)
                           | PressiomètreIA v2 · NF P 94-110  (gris)
      ──────────────────── ligne orange (bas)
    """
    pix = QPixmap(width, height)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    w, h = float(width), float(height)

    # ── Fond dégradé ──────────────────────────────────────────────────────
    bg = QLinearGradient(0.0, 0.0, w, 0.0)
    bg.setColorAt(0.00, QColor("#0d2040"))
    bg.setColorAt(0.55, QColor("#0a1628"))
    bg.setColorAt(1.00, QColor("#070e1a"))
    p.setBrush(QBrush(bg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, w, h), 6, 6)

    # ── Mini-icône de l'application ───────────────────────────────────────
    ico_sz  = 46
    ico_pad = 7
    ico_pix = make_icon_pixmap(ico_sz)
    p.drawPixmap(ico_pad, int((h - ico_sz) / 2), ico_pix)

    # ── Textes (SETRAF / GABON / sous-titre) ──────────────────────────────
    tx = ico_pad + ico_sz + 10

    f_setraf = QFont("Segoe UI")
    f_setraf.setWeight(QFont.Weight.Black)
    f_setraf.setPixelSize(17)
    f_setraf.setStyleHint(QFont.StyleHint.SansSerif)
    f_setraf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
    p.setFont(f_setraf)
    p.setPen(QColor(_SKY))
    p.drawText(tx, int(h * 0.435), "SETRAF")

    f_gabon = QFont("Segoe UI")
    f_gabon.setWeight(QFont.Weight.Bold)
    f_gabon.setPixelSize(11)
    f_gabon.setStyleHint(QFont.StyleHint.SansSerif)
    f_gabon.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.4)
    p.setFont(f_gabon)
    p.setPen(QColor(_GOLD))
    p.drawText(tx, int(h * 0.685), "GABON")

    f_sub = QFont("Segoe UI")
    f_sub.setPixelSize(8)
    f_sub.setStyleHint(QFont.StyleHint.SansSerif)
    p.setFont(f_sub)
    p.setPen(QColor(_GRAY))
    p.drawText(tx, int(h * 0.895), "PressiomètreIA v2  ·  NF P 94-110")

    # ── Ligne d'accentuation orange (bas de la bannière) ──────────────────
    p.setPen(QPen(QColor(_ORANGE), 2))
    p.drawLine(QPointF(0, h - 1), QPointF(w, h - 1))

    # ── Barre laterale sky bleu (bord gauche chaud) ───────────────────────
    accent = QLinearGradient(0.0, 4.0, 0.0, h - 4.0)
    accent.setColorAt(0.0, QColor("#38bdf890"))
    accent.setColorAt(0.5, QColor(_SKY))
    accent.setColorAt(1.0, QColor("#38bdf890"))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QBrush(accent), 3))
    p.drawLine(QPointF(1, 4), QPointF(1, h - 4))

    p.end()
    return pix


# ─── Sauvegarde du fichier .ico Windows ──────────────────────────────────────

def ensure_ico_file(ico_path: str, png_path: str | None = None) -> bool:
    """
    Génère le fichier .ico multi-résolutions si absent.
    Sauvegarde aussi une copie .png si `png_path` est fourni.
    Retourne True si le fichier a été créé, False s'il existait déjà.

    Format ICO : PNG-in-ICO (Vista+) avec 6 tailles : 16, 32, 48, 64, 128, 256.
    """
    ico_p = Path(ico_path)
    if ico_p.exists():
        return False

    ico_p.parent.mkdir(parents=True, exist_ok=True)
    master = make_icon_pixmap(256)

    if png_path:
        png_p = Path(png_path)
        png_p.parent.mkdir(parents=True, exist_ok=True)
        master.save(str(png_p), "PNG")

    sizes = [16, 32, 48, 64, 128, 256]
    blobs: list[bytes] = []

    for sz in sizes:
        scaled = master.scaled(
            sz, sz,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        ba  = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buf, "PNG")
        buf.close()
        blobs.append(bytes(ba))

    n            = len(sizes)
    data_offset  = 6 + n * 16         # ICONDIR (6) + n × ICONDIRENTRY (16)

    # ICONDIR : reserved=0, type=1 (icon), count=n
    ico_bytes = struct.pack("<HHH", 0, 1, n)

    for sz, blob in zip(sizes, blobs):
        w = sz if sz < 256 else 0      # 256 s'écrit 0 dans le format ICO
        h = sz if sz < 256 else 0
        ico_bytes += struct.pack(
            "<BBBBHHII",
            w, h,          # largeur, hauteur
            0,             # nb couleurs (0 = PNG)
            0,             # réservé
            1,             # plans
            32,            # bits par pixel
            len(blob),     # taille données
            data_offset,   # offset données
        )
        data_offset += len(blob)

    for blob in blobs:
        ico_bytes += blob

    ico_p.write_bytes(ico_bytes)
    return True
