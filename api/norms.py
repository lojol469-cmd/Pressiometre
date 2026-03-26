"""
api/norms.py — Données normatives internationales pour l'analyse pressiométrique
Sources :
  - NF P 94-110 (AFNOR, 2000) — Essai pressiométrique Ménard
  - Eurocode 7 (EN 1997-1:2004) — Calcul géotechnique
  - ISO 22476-4:2021 — Essai pressiométrique
  - ASTM D4719-20 — Prebored pressuremeter testing
  - Ménard & Rousseau (1962), Baguelin et al. (1978)
"""
from __future__ import annotations
import sys, os
from pathlib import Path

# ─── Paramètres Ménard de classification (NF P 94-110 §8) ─────────────────────
# Facteur rhéologique alpha : Em/Pl* utilisé pour settlement calc
# Format : (sol_type, alpha, k_factor_description)
RHEOLOGICAL_ALPHA = {
    "Tourbe / organique":       0.10,
    "Sol mou très compressible": 0.15,
    "Argile molle NC":           0.33,
    "Argile raide NC":           0.50,
    "Argile SC / limon":         0.67,
    "Sable lâche NC":            0.33,
    "Sable dense SC":            0.50,
    "Sable compact NGF":         0.50,
    "Grave":                     0.33,
    "Roche altérée":             0.67,
    "Roche peu altérée":         1.00,
}

# ─── Classement qualité NF P 94-110 §8.3 ──────────────────────────────────────
# (code, label, creep_ratio_max, n_anomalies_max, description)
QUALITY_GRADES = [
    ("A", "Excellent",  1.30, 0, "Aucune anomalie — courbe très régulière"),
    ("B", "Bon",        1.40, 1, "1 anomalie mineure acceptable"),
    ("C", "Acceptable", 1.50, 2, "2 anomalies — résultats exploitables avec précaution"),
    ("D", "Mauvais",    9.99, 99,"Trop d'anomalies — non représentatif"),
]

# ─── Classes de sol Ménard + valeurs caractéristiques ─────────────────────────
# (classe_id, nom, Em_min, Em_max, Pl_min, Pl_max, description_eurocode)
SOIL_NORMS_TABLE = [
    ("T1", "Tourbe / sol organique",        0.2,  0.5, 0.1, 0.3,
     "Sol de très faible consistance, non utilisable en fondation directe. EC7 §6.2"),
    ("A1", "Argile très molle",             0.5,  3.0, 0.1, 0.5,
     "Argile NC, taux de travail ≤ 50 kPa. Risque tassement différentiel. EC7 §6.6.1"),
    ("A2", "Argile molle à ferme",          3.0,  8.0, 0.3, 1.0,
     "Fondation superficielle possible si Pl > 0.5 MPa. NF P 94-110 Tab.1"),
    ("A3", "Argile raide / limono-argile",  8.0, 25.0, 1.0, 2.5,
     "Bon sol de fondation — capacité portante estimée par qc = (Pl*/1.5) MPa"),
    ("B1", "Sable lâche",                   2.0,  8.0, 0.2, 0.8,
     "Densification possible par compactage. ASTM D4719 §9.3"),
    ("B2", "Sable dense ou compact",        8.0, 25.0, 0.8, 2.0,
     "Bon sol de fondation — Em/Pl ratio ~ 8-12 (NC). NF P 94-110"),
    ("B3", "Grave / sable graveleux",      25.0, 80.0, 2.0, 5.0,
     "Haute capacité portante. Fondation semelle filante recommandée."),
    ("C1", "Roche altérée / résiduelle",   10.0, 40.0, 1.0, 4.0,
     "Vérifier hétérogénéité. ISO 22476-4 §7.4"),
    ("C2", "Roche peu altérée",            40.0,200.0, 4.0,20.0,
     "Fondation sur puits ou pieux de pointe. Eurocode 7 annexe D"),
]

# ─── Tableau NC/SC (NF P 94-110 Tab.3) ─────────────────────────────────────
NC_SC_TABLE = [
    ("NC — Normalement Consolidé", "Em/Pl ≤ 12",
     "Terrain en place, consolidation normale, alpha=0.33-0.50"),
    ("SC — Surconsolidé",          "Em/Pl > 12",
     "Préchargement naturel ou anthropique, alpha=0.50-1.00"),
    ("Remanié / perturbé",         "Em/Pl < 5",
     "Résultat d'essai de mauvaise qualité ou sol remanié"),
]

# ─── Formules de calcul (Ménard 1962) ─────────────────────────────────────────
MENARD_FORMULAS = {
    "module_de_deformation": {
        "formula": "Em = 2.66 × ΔP/ΔV × V₀  [MPa]",
        "ref": "NF P 94-110 §8.1",
        "note": "V₀ = volume initial de la cellule (cm³), ΔP/ΔV = pente de la zone élastique",
    },
    "pression_limite": {
        "formula": "Pl = extrapolation tangente hyperbolique V(P)",
        "ref": "NF P 94-110 §8.2",
        "note": "Pl* = pression limite nette = Pl - P₀ (pression des terres au repos)",
    },
    "pression_fluage": {
        "formula": "Pf déterminée par Vm(P) — point d'inflexion ou creep ratio > seuil",
        "ref": "NF P 94-110 §8.2",
        "note": "Creep ratio = V30/V60 — alarme si > 1.30",
    },
    "capacite_portante_nette": {
        "formula": "qnet = k × Pl*  (k dépend de B/L et D/B de la fondation)",
        "ref": "Fascicule 62 titre V, Eurocode 7 annexe D",
        "note": "k = 0.8 à 2.0 selon forme fondation et type sol",
    },
    "tassement_menard": {
        "formula": "s = Cq × q × (B₀/9Em) × (B/B₀)^α + Cd × q × (α_B/9Em)",
        "ref": "Ménard & Rousseau (1962), NF P 94-261 §12",
        "note": "alpha = facteur rhéologique, B₀ = 0.60 m (fondation référence)",
    },
}

# ─── Références normatives complètes ──────────────────────────────────────────
NORMATIVE_REFS = [
    ("NF P 94-110-1 (2000)",
     "Reconnaissance et essais — Essai pressiométrique Ménard. Partie 1 : essai sans cycle",
     "AFNOR"),
    ("NF P 94-110-2 (2000)",
     "Reconnaissance et essais — Essai pressiométrique Ménard. Partie 2 : essai avec cycle",
     "AFNOR"),
    ("Eurocode 7 / EN 1997-1 (2004)",
     "Calcul géotechnique — Partie 1 : Règles générales. Utilisation Pl* pour capacité portante et tassements",
     "CEN"),
    ("ISO 22476-4 (2021)",
     "Investigation et essais géotechniques — Essais en place — Partie 4 : essai pressiométrique Ménard",
     "ISO / TC 182"),
    ("ASTM D4719-20",
     "Standard Test Methods for Prebored Pressuremeter Testing in Soils",
     "ASTM International"),
    ("NF P 94-261 (2013)",
     "Justification des ouvrages géotechniques — Fondations superficielles (méthode pressiométrique)",
     "AFNOR"),
    ("Baguelin, Jézéquel & Shields (1978)",
     "The Pressuremeter and Foundation Engineering — Technical Publications Palatine",
     "Référence académique"),
    ("Fascicule 62 Titre V (1993)",
     "Règles techniques de conception et de calcul des fondations des ouvrages de génie civil",
     "MELT-DAF France"),
]

# ─── Enrichissement normatif par web search (optionnel) ───────────────────────
def get_web_normative_context(query_extra: str = "") -> dict:
    """
    Interroge le moteur de recherche web (tools/web.py) pour enrichir
    le contexte normatif avec des prescriptions récentes.
    Retourne un dict {source, snippets, images}.
    """
    empty = {"source": "none", "snippets": [], "images": []}

    # Importer web.py depuis tools/ (path relatif au root du projet)
    try:
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from tools.web import web_search
    except ImportError:
        return empty

    query = (
        "pressiometre Menard NF P 94-110 Eurocode 7 calcul fondation "
        "pression limite module pressiometrique classification sol " + query_extra
    )
    try:
        result = web_search(query, disabled=False)
    except Exception:
        return empty

    snippets = []
    for r in (result.get("results") or [])[:5]:
        url   = r.get("url") or r.get("href") or ""
        title = r.get("title") or r.get("name") or ""
        body  = r.get("body") or r.get("snippet") or r.get("description") or ""
        if body:
            snippets.append({"title": title, "url": url, "text": body[:400]})

    return {
        "source":   result.get("source", "unknown"),
        "snippets": snippets,
        "images":   (result.get("images") or [])[:3],
    }
