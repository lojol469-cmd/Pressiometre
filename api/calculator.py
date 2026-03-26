"""
Calcul des paramètres pressiométriques (NF P 94-110 / Méthode Ménard)
─────────────────────────────────────────────────────────────────────
Paramètres calculés :
  - Em  : module pressiométrique   (MPa)
  - Pf  : pression de fluage       (MPa)
  - Pl  : pression limite          (MPa)
  - Pl* : pression limite nette    (MPa)  Pl* = Pl - u0 (pression poreale)
  - Em/Pl : rapport consolidation
Classification géotechnique Ménard, qualité de l'essai A/B/C/D.
"""
from __future__ import annotations
from typing import List, Optional
import numpy as np
from scipy.interpolate import interp1d
from scipy.signal import argrelextrema

from .models import CleanedEssai, PressiometricParams

# ─── Volume initial de la sonde Ménard standard ─────────────────────────────
PROBE_V0_DEFAULT = 535.0  # cm³ (sonde 58 mm boîtier 73 mm)

# ─── Classification Ménard ───────────────────────────────────────────────────
SOL_CLASSES = [
    # (Pl_min, Pl_max, Em_min, Em_max, label, color, nc_status)
    (0.0,  0.30,  0.0,   3.0,  "Tourbe / argile très molle",   "#4a9e8b", "NC"),
    (0.30, 1.00,  1.0,   8.0,  "Argile molle peu consolidée",  "#5b9e6e", "NC"),
    (0.30, 1.00,  8.0,   30.0, "Argile de consistance moyenne","#7dbd8a", "NC"),
    (1.00, 2.00,  5.0,   20.0, "Limon / sable lâche",          "#d4b483", "NC"),
    (1.00, 2.00, 20.0,   80.0, "Sable compact",                "#c8964e", "SC"),
    (2.00, 4.00, 20.0,  100.0, "Argile raide / gravier",       "#8b6b32", "SC"),
    (4.00, 8.00, 50.0,  200.0, "Sol très raide",               "#6b4c25", "SC"),
    (8.00, 999., 200.0, 9999., "Rocher altéré / rocheux",      "#5c4033", "SC"),
]

def classify_soil(em: Optional[float], pl: Optional[float]) -> tuple[str, str, str]:
    """Retourne (sol_type, sol_color, nc_status)."""
    if em is None or pl is None:
        return "Indéterminé", "#888888", "?"
    for pl_min, pl_max, em_min, em_max, label, color, nc in SOL_CLASSES:
        if pl_min <= pl < pl_max and em_min <= em < em_max:
            return label, color, nc
    # Fallback sur Pl uniquement
    if pl < 0.3:  return "Tourbe / argile très molle",  "#4a9e8b", "NC"
    if pl < 1.0:  return "Argile molle",                "#5b9e6e", "NC"
    if pl < 2.0:  return "Sol meuble",                  "#d4b483", "NC"
    if pl < 4.0:  return "Sol compact",                 "#c8964e", "SC"
    if pl < 8.0:  return "Sol très raide",              "#6b4c25", "SC"
    return "Rocheux", "#5c4033", "SC"


def _quality_grade(n_paliers: int, n_anomalies: int, p_range: float) -> str:
    """Notation qualité A/B/C/D."""
    if n_paliers >= 8 and n_anomalies == 0 and p_range >= 0.4: return "A"
    if n_paliers >= 5 and n_anomalies <= 1 and p_range >= 0.2: return "B"
    if n_paliers >= 3 and p_range >= 0.1:                       return "C"
    return "D"


def compute_params(cleaned: CleanedEssai, probe_v0_cm3: float = PROBE_V0_DEFAULT) -> PressiometricParams:
    """
    Calcule Em, Pf, Pl sur un essai nettoyé.
    """
    notes: List[str] = []
    pts   = [p for p in cleaned.points if not p.anomalie]

    if len(pts) < 3:
        return PressiometricParams(
            sheet_name=cleaned.sheet_name,
            depth_m=cleaned.depth_m,
            ref_sondage=cleaned.meta.ref_sondage,
            sol_type="Données insuffisantes",
            qualite="D",
            notes=["Moins de 3 paliers valides — paramètres non calculables"],
        )

    # Arrays numpy
    p   = np.array([pt.P60_corr_MPa for pt in pts])
    v60 = np.array([(pt.V60_smooth_cm3 or pt.V60_corr_cm3 or 0.0) for pt in pts])
    v30 = np.array([(pt.V30_smooth_cm3 or pt.V30_corr_cm3 or 0.0) for pt in pts])
    vm  = (v30 + v60) / 2.0
    creep = v60 - v30

    # ─── V0 : volume à pression P0 ≈ pression de repos ──────────────────────
    # Interpolé à p=0, ou valeur du premier palier utile
    if p[0] > 0:
        v0_measured = float(np.interp(0, p, vm))
    else:
        v0_measured = float(vm[0])
    v0 = probe_v0_cm3  # volume de référence sonde

    # ─── Pression de fluage Pf ───────────────────────────────────────────────
    # Méthode : inflexion sur creep  (d(creep)/dP maximal)
    # Alternative si insuffisant : ratio creep > seuil CREEP_RATIO_Pf
    pf: Optional[float] = None
    CREEP_THRESH = 1.15

    if len(p) >= 4:
        # Chercher le premier point où creep/v30 dépasse le seuil
        for i in range(len(pts)):
            v30_i = v30[i]
            v60_i = v60[i]
            if v30_i > 5 and v60_i / v30_i > CREEP_THRESH:
                pf = float(p[i])
                break

        # Si pas trouvé, utiliser la dérivée du creep
        if pf is None and len(p) >= 5:
            try:
                with np.errstate(divide='ignore', invalid='ignore'):
                    d_creep = np.gradient(creep, p)
                    dd_creep = np.gradient(d_creep, p)
                # Point de maximum de d(creep)
                idx_pf = int(np.argmax(d_creep[1:]) + 1)
                if 1 <= idx_pf < len(p) - 1:
                    pf = float(p[idx_pf])
            except Exception:
                pass

    if pf is None and len(p) > 2:
        pf = float(p[len(p) // 2])
        notes.append("Pf estimé par position médiane (données limitées)")

    # ─── Pression limite Pl ──────────────────────────────────────────────────
    # Méthode : extrapolation vers V_limite = 2*Vs + V0
    # Vs = volume de la cavité initiale ≈ probe_v0_cm3
    v_limite = 2.0 * probe_v0_cm3 + v0_measured
    pl: Optional[float] = None

    if vm[-1] >= v_limite:
        # La courbe a atteint la limite : interpolation directe
        try:
            f_p_of_v = interp1d(vm, p, kind="linear",
                                bounds_error=False, fill_value="extrapolate")  # type: ignore[call-overload]
            pl = float(f_p_of_v(v_limite))
            notes.append("Pl interpolé directement sur la courbe (V_limite atteint)")
        except Exception:
            pl = float(p[-1])
    else:
        # Extrapolation : ajustement hyperbolique sur les 4 derniers points
        # Loi : P = Pl * V / (2*(Pl-Pf)*Vs + V)  (hyperbole de Ménard)
        if len(p) >= 4:
            try:
                p_tail = p[-4:]
                v_tail = vm[-4:]
                # Ajustement linéaire en coordonnées (ΔV, ΔP/ΔV) → tangente
                dv = v_tail - v0_measured
                dp = np.diff(p_tail)
                dv_mid = (dv[:-1] + dv[1:]) / 2
                if len(dp) >= 2 and np.all(dv_mid > 0):
                    # Module tangent décroissant → extrapoler à 1/Pl
                    coeffs = np.polyfit(dv_mid, dp / np.diff(dv), 1)
                    pl_candidate = float(-coeffs[1] / coeffs[0]) if coeffs[0] < 0 else None
                    if pl_candidate is not None and pl_candidate > p[-1]:
                        pl = pl_candidate
                        notes.append("Pl extrapolé par tangente hyperbolique")
            except Exception:
                pass

        if pl is None:
            # Dernier recours : pl = 1.3 × la pression du dernier palier
            pl = float(p[-1]) * 1.3
            notes.append("Pl estimé par extrapolation linéaire simple (données insuffisantes)")

    # Pression limite nette Pl* (on ignore la pression de pore ≈ 0 en forage sec)
    pl_star = pl  # pl_star = pl - u0, u0 estimé nul ici

    # ─── Module pressiométrique Em ───────────────────────────────────────────
    # Em = 2(1+ν) × V0 × (ΔP/ΔV)  sur la zone pseudo-élastique (Pf > P > P0)
    # ν = 0.33 → 2(1+ν) ≈ 2.66
    POISSON_FACTOR = 2.66
    em: Optional[float] = None
    p_el_min = p_el_max = v_el_min = v_el_max = slope = None

    # Zone élastique : entre P0 et Pf
    pf_val = pf or float(np.median(p))
    elastic_mask = (p <= pf_val)
    if elastic_mask.sum() >= 2:
        p_el = p[elastic_mask]
        v_el = vm[elastic_mask]
        # Régression linéaire V(P) sur la zone élastique
        try:
            coeffs_el = np.polyfit(p_el, v_el, 1)
            dv_dp_el = coeffs_el[0]  # cm³/MPa
            if dv_dp_el > 0:
                em = float(POISSON_FACTOR * v0 * (1.0 / dv_dp_el))
                slope = float(1.0 / dv_dp_el) if dv_dp_el != 0 else None
                p_el_min = float(p_el[0])
                p_el_max = float(p_el[-1])
                v_el_min = float(v_el[0])
                v_el_max = float(v_el[-1])
        except Exception:
            pass

    if em is None or em <= 0:
        # Fallback : zone complète
        try:
            coeffs_all = np.polyfit(p, vm, 1)
            dv_dp = coeffs_all[0]
            if dv_dp > 0:
                em = float(POISSON_FACTOR * v0 / dv_dp)
                notes.append("Em calculé sur l'ensemble des paliers")
        except Exception:
            em = None

    # ─── Rapport Em/Pl ───────────────────────────────────────────────────────
    ratio = float(em / pl) if (em and pl and pl > 0) else None
    if ratio is not None:
        if ratio < 7:
            notes.append(f"Em/Pl={ratio:.1f} < 7 → sol remanié ou surconsolidé perturbé")
        elif ratio > 12:
            notes.append(f"Em/Pl={ratio:.1f} > 12 → sol surconsolidé")
        else:
            notes.append(f"Em/Pl={ratio:.1f} → sol normalement consolidé")

    # ─── Classification et qualité ───────────────────────────────────────────
    sol_type, sol_color, nc_status = classify_soil(em, pl)
    n_anom = len([a for a in cleaned.anomalies if a.severity == "error"])
    p_range = float(p[-1] - p[0])
    qualite = _quality_grade(len(pts), n_anom, p_range)

    return PressiometricParams(
        sheet_name=cleaned.sheet_name,
        depth_m=cleaned.depth_m,
        ref_sondage=cleaned.meta.ref_sondage,
        V0_probe_cm3=float(probe_v0_cm3),
        Pf_MPa=round(pf, 4) if pf else None,
        Pl_MPa=round(pl, 4) if pl else None,
        Pl_star_MPa=round(pl_star, 4) if pl_star else None,
        Em_MPa=round(em, 2) if em else None,
        ratio_Em_Pl=round(ratio, 2) if ratio else None,
        P_elastic_min_MPa=round(p_el_min, 4) if p_el_min else None,
        P_elastic_max_MPa=round(p_el_max, 4) if p_el_max else None,
        V_elastic_min_cm3=round(v_el_min, 2) if v_el_min else None,
        V_elastic_max_cm3=round(v_el_max, 2) if v_el_max else None,
        slope_elastic_MPa_per_cm3=round(slope, 6) if slope else None,
        sol_type=sol_type,
        sol_color=sol_color,
        nc_status=nc_status,
        n_paliers=len(pts),
        n_anomalies=n_anom,
        qualite=qualite,
        notes=notes,
        is_coherent=(n_anom == 0 and qualite in ("A", "B")),
        coherence_checks=cleaned.coherence if cleaned.coherence else [],
    )


def build_profile(params_list: List[PressiometricParams]):
    """Construit le profil géotechnique trié par profondeur."""
    from .models import ProfileData
    sorted_p = sorted([p for p in params_list if p.depth_m is not None],
                      key=lambda x: x.depth_m or 0.0)
    sondage = sorted_p[0].ref_sondage or "SP" if sorted_p else "SP"
    return ProfileData(
        sondage=sondage,
        depths=[p.depth_m for p in sorted_p],  # type: ignore[list-item]
        Em_MPa=[p.Em_MPa for p in sorted_p],
        Pf_MPa=[p.Pf_MPa for p in sorted_p],
        Pl_MPa=[p.Pl_MPa for p in sorted_p],
        sol_types=[p.sol_type for p in sorted_p],
        sol_colors=[p.sol_color for p in sorted_p],
        Em_Pl_ratios=[p.ratio_Em_Pl for p in sorted_p],
    )


def build_section(params_list, boreholes: list, n_interp: int = 50):
    """
    Construit une coupe géotechnique 2D entre plusieurs sondages.
    boreholes: [{name, x_m, y_m}]
    """
    from .models import SectionData, SectionPoint
    import scipy.ndimage as ndi

    # Créer un dict borehole_name → x_m
    bh_map = {bh["name"]: bh.get("x_m", 0) for bh in boreholes}

    # Grouper par sondage
    from collections import defaultdict
    by_sondage = defaultdict(list)
    for p in params_list:
        sond = p.ref_sondage or "SP"
        by_sondage[sond].append(p)

    # Assigner x_m à chaque sondage (depuis bh_map ou position auto)
    sondage_x = {}
    for i, sond in enumerate(by_sondage.keys()):
        sondage_x[sond] = bh_map.get(sond, float(i) * 10.0)

    # Construire les points de la coupe
    section_pts: list[SectionPoint] = []
    for sond, pts in by_sondage.items():
        x = sondage_x[sond]
        for p in sorted(pts, key=lambda x: x.depth_m or 0):
            section_pts.append(SectionPoint(
                x_m=x,
                depth_m=p.depth_m or 0.0,
                Em_MPa=p.Em_MPa,
                Pl_MPa=p.Pl_MPa,
                Pf_MPa=p.Pf_MPa,
                qualite=p.qualite,
                sol_type=p.sol_type,
                sol_color=p.sol_color,
                sondage=sond,
            ))

    # Interpolation des couches entre sondages
    bh_list = [{"name": k, "x_m": v, "max_depth_m": max(
        (p.depth_m or 0) for p in by_sondage[k])} for k, v in sondage_x.items()]

    return SectionData(
        title="Coupe géotechnique",
        points=section_pts,
        boreholes=bh_list,
        layers=[],  # rempli par le frontend
    )


def build_cloud3d(params_list, boreholes: list, grid_res: int = 20):
    """
    Construit un nuage de points 3D pour la reconstruction du terrain.
    boreholes: [{name, x_m, y_m}]
    """
    from .models import PointCloud3D
    import scipy.interpolate as sci

    bh_map = {bh["name"]: (bh.get("x_m", 0), bh.get("y_m", 0)) for bh in boreholes}

    points_3d = []
    xs, ys = [], []
    for p in params_list:
        if p.depth_m is None:
            continue
        sond = p.ref_sondage or "SP"
        bx, by = bh_map.get(sond, (0.0, 0.0))
        xs.append(bx)
        ys.append(by)
        points_3d.append({
            "x": bx, "y": by, "z": -(p.depth_m),
            "Em": p.Em_MPa, "Pl": p.Pl_MPa, "Pf": p.Pf_MPa,
            "sol_type": p.sol_type,
            "sol_color": p.sol_color,
            "sondage": sond,
            "depth_m": p.depth_m,
        })

    bounds = {
        "xmin": float(min(xs)) if xs else 0.0,
        "xmax": float(max(xs)) if xs else 0.0,
        "ymin": float(min(ys)) if ys else 0.0,
        "ymax": float(max(ys)) if ys else 0.0,
        "zmin": float(-max(p["depth_m"] for p in points_3d)) if points_3d else 0.0,
        "zmax": 0.0,
    }

    bh_list = [{"name": k, "x_m": v[0], "y_m": v[1]} for k, v in bh_map.items()]

    # Grille Em interpolée (IDW) si assez de points
    grid_Em = grid_Pl = grid_x_vals = grid_y_vals = None
    if len(points_3d) >= 4:
        try:
            all_x = np.array([p["x"] for p in points_3d])
            all_y = np.array([p["y"] for p in points_3d])
            all_em = np.array([p["Em"] or 0 for p in points_3d])
            all_pl = np.array([p["Pl"] or 0 for p in points_3d])
            xi = np.linspace(bounds["xmin"], bounds["xmax"], grid_res)
            yi = np.linspace(bounds["ymin"], bounds["ymax"], grid_res)
            xgrid, ygrid = np.meshgrid(xi, yi)
            # IDW simple
            def idw(xq, yq, vals, power=2):
                out = np.zeros_like(xq)
                for i, (xrow, yrow) in enumerate(zip(xq, yq)):
                    for j, (xp, yp) in enumerate(zip(xrow, yrow)):
                        d = np.sqrt((all_x - xp)**2 + (all_y - yp)**2) + 1e-9
                        w = 1.0 / d**power
                        out[i, j] = np.sum(w * vals) / np.sum(w)
                return out
            grid_Em = idw(xgrid, ygrid, all_em).tolist()
            grid_Pl = idw(xgrid, ygrid, all_pl).tolist()
            grid_x_vals = xi.tolist()
            grid_y_vals = yi.tolist()
        except Exception:
            pass

    return PointCloud3D(
        points=points_3d,
        boreholes=bh_list,
        bounds=bounds,
        grid_Em=grid_Em,
        grid_Pl=grid_Pl,
        grid_x=grid_x_vals,
        grid_y=grid_y_vals,
    )
