"""
SvgResultsWidget — Jauges SVG animées pour les résultats pressiométriques.
Utilise QWebEngineView pour afficher du HTML/SVG inline avec animations CSS.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WE = True
except ImportError:
    HAS_WE = False

from api.models import PressiometricParams


# ─── Palette ─────────────────────────────────────────────────────────────────
_QUAL_COLOR = {"A": "#06d6a0", "B": "#ffd166", "C": "#ef8c3f", "D": "#ef476f"}
_EMPTY_COLOR = "#1e2d3d"


def _arc_path(cx, cy, r, pct):
    """Retourne stroke-dasharray/offset pour un arc circulaire (circumference trick)."""
    import math
    circ = 2 * math.pi * r
    dash = pct * circ
    gap  = circ - dash
    return circ, dash, gap


def _gauge_svg(label: str, value: Optional[float], unit: str,
               max_val: float, color: str,
               cx: int = 60, cy: int = 60, r: int = 48,
               width: int = 120, height: int = 130) -> str:
    """Génère un SVG de jauge circulaire animée."""
    pct   = min(1.0, (value or 0) / max_val) if max_val > 0 else 0
    circ  = 2 * 3.14159 * r
    dash  = pct * circ
    val_str = f"{value:.1f}" if value is not None else "—"

    # Rotation de départ = -90° (12h)
    rotate = f"rotate(-90 {cx} {cy})"
    uid = label.replace(" ", "").replace("/", "")

    return f"""
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
     xmlns="http://www.w3.org/2000/svg" style="overflow:visible">
  <defs>
    <linearGradient id="grad_{uid}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:{color};stop-opacity:0.7"/>
      <stop offset="100%" style="stop-color:{color};stop-opacity:1"/>
    </linearGradient>
    <filter id="glow_{uid}">
      <feGaussianBlur stdDeviation="2" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <style>
      @keyframes draw_{uid} {{
        from {{ stroke-dasharray: 0 {circ:.1f}; }}
        to   {{ stroke-dasharray: {dash:.1f} {circ:.1f}; }}
      }}
      @keyframes fadeIn_{uid} {{
        from {{ opacity: 0; transform: scale(0.8); }}
        to   {{ opacity: 1; transform: scale(1); }}
      }}
      .arc_{uid} {{
        stroke-dasharray: 0 {circ:.1f};
        animation: draw_{uid} 1.2s cubic-bezier(0.25,0.46,0.45,0.94) 0.1s forwards;
      }}
      .val_{uid} {{
        animation: fadeIn_{uid} 0.6s ease 0.8s both;
      }}
    </style>
  </defs>

  <!-- Fond cercle -->
  <circle cx="{cx}" cy="{cy}" r="{r}"
    fill="none" stroke="#1e2d3d" stroke-width="8"/>

  <!-- Arc progressif animé -->
  <circle cx="{cx}" cy="{cy}" r="{r}"
    fill="none"
    stroke="url(#grad_{uid})" stroke-width="9"
    stroke-linecap="round"
    class="arc_{uid}"
    filter="url(#glow_{uid})"
    transform="{rotate}"/>

  <!-- Valeur centrale -->
  <text x="{cx}" y="{cy - 6}" text-anchor="middle"
    font-family="'Consolas', monospace" font-size="14" font-weight="bold"
    fill="{color}" class="val_{uid}">{val_str}</text>
  <text x="{cx}" y="{cy + 10}" text-anchor="middle"
    font-family="sans-serif" font-size="8" fill="#aaa"
    class="val_{uid}">{unit}</text>

  <!-- Label bas -->
  <text x="{cx}" y="{height - 8}" text-anchor="middle"
    font-family="sans-serif" font-size="9" fill="#ccc">{label}</text>
</svg>"""


def _quality_badge_svg(qualite: Optional[str], width: int = 80, height: int = 80) -> str:
    q     = qualite or "?"
    color = _QUAL_COLOR.get(q, "#888")
    return f"""
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      @keyframes popQ {{
        0%   {{ transform: scale(0) rotate(-180deg); opacity:0; }}
        60%  {{ transform: scale(1.15) rotate(5deg); opacity:1; }}
        100% {{ transform: scale(1) rotate(0deg); opacity:1; }}
      }}
      .badge {{ animation: popQ 0.7s cubic-bezier(0.34,1.56,0.64,1) 0.3s both;
                transform-origin: {width//2}px {height//2}px; }}
    </style>
    <filter id="glowQ">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <g class="badge">
    <circle cx="{width//2}" cy="{height//2 - 8}" r="26"
      fill="{color}22" stroke="{color}" stroke-width="2.5"
      filter="url(#glowQ)"/>
    <text x="{width//2}" y="{height//2 - 2}" text-anchor="middle"
      font-family="'Consolas', monospace" font-size="22" font-weight="bold"
      fill="{color}">{q}</text>
    <text x="{width//2}" y="{height - 6}" text-anchor="middle"
      font-family="sans-serif" font-size="9" fill="#ccc">Qualité</text>
  </g>
</svg>"""


def _ratio_bar_svg(ratio: Optional[float], width: int = 200, height: int = 50) -> str:
    """Barre animée pour Em/Pl ratio avec zones de classification."""
    r     = ratio or 0
    # Zones NC: 5-12, SC: >12, remanié: <5
    # Normaliser sur 0-20
    max_r = 20.0
    pct   = min(1.0, r / max_r)
    bar_w = int(pct * (width - 20))

    if r < 5:
        color = "#ef476f"
        label = "Sol remanié / perturbé"
    elif r < 12:
        color = "#06d6a0"
        label = "NC — normal"
    else:
        color = "#ffd166"
        label = "SC — surconsolidé"

    return f"""
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      @keyframes growBar {{
        from {{ width: 0; }}
        to   {{ width: {bar_w}px; }}
      }}
      @keyframes fadeLabel {{
        from {{ opacity: 0; }}
        to   {{ opacity: 1; }}
      }}
      .bar   {{ animation: growBar 1s ease 0.5s both; }}
      .lbl   {{ animation: fadeLabel 0.5s ease 1.2s both; }}
    </style>
  </defs>

  <!-- Fond -->
  <rect x="10" y="10" width="{width-20}" height="16" rx="8"
    fill="#1e2d3d"/>

  <!-- Zones de couleur subtiles -->
  <rect x="10" y="10" width="{int((width-20)*5/max_r)}" height="16" rx="8"
    fill="#ef47661a" />
  <rect x="{10 + int((width-20)*5/max_r)}" y="10"
    width="{int((width-20)*7/max_r)}" height="16" fill="#06d6a01a"/>
  <rect x="{10 + int((width-20)*12/max_r)}" y="10"
    width="{int((width-20)*8/max_r)}" height="16" rx="8" fill="#ffd1661a"/>

  <!-- Barre valeur -->
  <rect x="10" y="11" height="14" rx="7"
    fill="{color}" class="bar"/>

  <!-- Valeur + label -->
  <text x="{width//2}" y="{height - 8}" text-anchor="middle"
    font-family="sans-serif" font-size="9" fill="{color}" class="lbl">
    Em/Pl = {r:.1f}  — {label}
  </text>
</svg>"""


def _sol_badge_svg(sol_type: str, sol_color: str,
                   width: int = 260, height: int = 40) -> str:
    return f"""
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      @keyframes slideIn {{
        from {{ transform: translateX(-20px); opacity:0; }}
        to   {{ transform: translateX(0); opacity:1; }}
      }}
      .sol {{ animation: slideIn 0.6s ease 0.2s both; }}
    </style>
  </defs>
  <g class="sol">
    <rect x="4" y="6" width="{width-8}" height="{height-12}" rx="6"
      fill="{sol_color}22" stroke="{sol_color}" stroke-width="1.5"/>
    <circle cx="20" cy="{height//2}" r="6" fill="{sol_color}"/>
    <text x="34" y="{height//2 + 4}" font-family="sans-serif" font-size="11"
      font-weight="bold" fill="{sol_color}">{sol_type[:35]}</text>
  </g>
</svg>"""


def build_results_html(params: Optional[PressiometricParams]) -> str:
    """Construit la page HTML complète avec toutes les jauges SVG animées."""
    if params is None:
        return """<!DOCTYPE html><html><body style="background:#0e1117;
            color:#888;font-family:sans-serif;display:flex;align-items:center;
            justify-content:center;height:100vh;margin:0;">
            <p>Aucun résultat — sélectionnez un essai et lancez l'analyse.</p>
        </body></html>"""

    g_em   = _gauge_svg("Module Em", params.Em_MPa,   "MPa", 100.0, "#06d6a0")
    g_pl   = _gauge_svg("Press. Pl", params.Pl_MPa,   "MPa",   5.0, "#ef476f")
    g_pf   = _gauge_svg("Fluage Pf", params.Pf_MPa,   "MPa",   4.0, "#ffd166")
    g_pls  = _gauge_svg("Pl*",       params.Pl_star_MPa, "MPa", 4.0, "#90e0ef")
    badge  = _quality_badge_svg(params.qualite)
    ratio  = _ratio_bar_svg(params.ratio_Em_Pl)
    sol    = _sol_badge_svg(params.sol_type, params.sol_color)

    depth_str   = f"{params.depth_m} m"  if params.depth_m is not None else "?"
    nc_color    = "#06d6a0" if "NC" in params.nc_status else "#ffd166"
    coh_icon    = "✅" if params.is_coherent else "⚠️"
    coh_color   = "#06d6a0" if params.is_coherent else "#ef476f"

    notes_html = "".join(
        f'<li style="margin:2px 0;font-size:10px;color:#ccc;">⚬ {n}</li>'
        for n in (params.notes or [])
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0e1117;
    color: #e0e0e0;
    font-family: 'Segoe UI', sans-serif;
    padding: 10px;
    overflow-x: hidden;
  }}
  h3 {{
    color: #00b4d8;
    font-size: 13px;
    margin-bottom: 6px;
    border-bottom: 1px solid #1e2d3d;
    padding-bottom: 4px;
  }}
  .row {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: flex-end; }}
  .card {{
    background: #111827;
    border: 1px solid #1e2d3d;
    border-radius: 8px;
    padding: 8px;
    flex: 1;
    min-width: 120px;
  }}
  .card-wide {{ flex: 3; min-width: 220px; }}
  .badge-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  .info-pill {{
    background: #1a2b3c;
    border: 1px solid #1e2d3d;
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 10px;
    color: #ccc;
    white-space: nowrap;
  }}
  .section {{ margin-bottom: 10px; }}
  ul {{ padding-left: 10px; list-style: none; }}

  /* Entrée de toute la page */
  @keyframes pageFade {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  .page {{ animation: pageFade 0.4s ease both; }}

  /* Lignes de scan (esthétique) */
  @keyframes scan {{
    0%   {{ top: 0; opacity: 0.06; }}
    50%  {{ opacity: 0.12; }}
    100% {{ top: 100%; opacity: 0.06; }}
  }}
  .scanline {{
    position: fixed; left: 0; width: 100%;
    height: 2px; background: #00b4d8;
    animation: scan 4s linear infinite;
    pointer-events: none;
  }}
</style>
</head>
<body>
<div class="scanline"></div>
<div class="page">

  <!-- Titre essai -->
  <div class="section">
    <h3>📊 {params.sheet_name} — Profondeur {depth_str}</h3>
    <div class="badge-row">
      {sol}
      <span class="info-pill" style="color:{nc_color};">{params.nc_status}</span>
      <span class="info-pill" style="color:{coh_color};">{coh_icon} {'Cohérent' if params.is_coherent else 'Incohérence détectée'}</span>
    </div>
  </div>

  <!-- Jauges principales -->
  <div class="section">
    <h3>Paramètres Ménard</h3>
    <div class="row">
      <div class="card" style="text-align:center;">{g_em}</div>
      <div class="card" style="text-align:center;">{g_pl}</div>
      <div class="card" style="text-align:center;">{g_pf}</div>
      <div class="card" style="text-align:center;">{g_pls}</div>
      <div class="card" style="text-align:center;">{badge}</div>
    </div>
  </div>

  <!-- Ratio Em/Pl -->
  <div class="section">
    <h3>Rapport Em/Pl</h3>
    <div class="card">
      {ratio}
    </div>
  </div>

  <!-- Notes de calcul -->
  {'<div class="section"><h3>Notes de calcul</h3><div class="card"><ul>' + notes_html + '</ul></div></div>' if params.notes else ''}

</div>
</body>
</html>"""


class SvgResultsWidget(QWidget):
    """Widget affichant les jauges SVG animées via QWebEngineView (ou fallback QLabel)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if HAS_WE:
            self._view = QWebEngineView()
            self._view.setStyleSheet("background:#0e1117;")
            layout.addWidget(self._view)
            self._view.setHtml(build_results_html(None))
        else:
            self._label = QLabel("PyQt6.QtWebEngineWidgets non disponible — animations SVG désactivées.")
            self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._label.setStyleSheet("color:#ffd166; font-size:12px;")
            layout.addWidget(self._label)

    def update_params(self, params: Optional[PressiometricParams]):
        if HAS_WE:
            self._view.setHtml(build_results_html(params))
