"""
Nettoyage, correction et lissage des données pressiométriques.
Applique :
  1. Filtre des valeurs nulles / hors-plage physique
  2. Correction calibrage (rigidité sonde) par interpolation
  3. Correction pression différentielle (colonne d'eau + pertes de charge)
  4. Lissage Savitzky-Golay sur les volumes
  5. Détection d'anomalies (creep excessif, saut de volume, pression non-monotone)
  6. Vérifications de cohérence
"""
from __future__ import annotations
from typing import Optional, List
import numpy as np
from scipy.signal import savgol_filter
from scipy.interpolate import interp1d
from scipy.stats import zscore

from .models import (
    EssaiRaw, CleanedEssai, CleanedPoint, Anomalie, CoherenceCheck, CleanRequest
)

# ─── Constantes physiques ──────────────────────────────────────────────────────
P_MIN_MPa = 0.0
P_MAX_MPa = 20.0     # limite physique raisonnable
V_MIN_cm3 = 0.0
V_MAX_cm3 = 1500.0   # limite technique

CREEP_RATIO_Pf = 1.15   # V60/V30 > seuil → début fluage
CREEP_RATIO_Pl = 1.30   # V60/V30 > seuil → proche pression limite
VOLUME_JUMP_cm3 = 200   # saut brusque → rupture membrane probable


def _build_calib_interp(calibrage: Optional[EssaiRaw]):
    """
    Construit des interpolateurs V30(P) et V60(P) à partir du calibrage.
    Extrapolation linéaire hors des bornes.
    """
    if calibrage is None or not calibrage.mesures:
        return None, None

    pts = [(m.P60_MPa, m.V30_cm3, m.V60_cm3)
           for m in calibrage.mesures
           if m.P60_MPa is not None and m.P60_MPa >= 0]
    if len(pts) < 2:
        return None, None

    pts.sort(key=lambda x: x[0])
    p_arr  = np.array([x[0] for x in pts])
    v30_arr = np.array([x[1] if x[1] is not None else 0 for x in pts])
    v60_arr = np.array([x[2] if x[2] is not None else 0 for x in pts])

    f30 = interp1d(p_arr, v30_arr, kind="linear", bounds_error=False,
                   fill_value=(v30_arr[0], v30_arr[-1]))  # type: ignore[call-overload]
    f60 = interp1d(p_arr, v60_arr, kind="linear", bounds_error=False,
                   fill_value=(v60_arr[0], v60_arr[-1]))  # type: ignore[call-overload]
    return f30, f60


def _smooth(arr: np.ndarray, window: int, poly: int) -> np.ndarray:
    """Lissage Savitzky-Golay. Retourne arr si trop peu de points."""
    n = len(arr)
    if n < window or n < poly + 2:
        return arr.copy()
    w = window if window % 2 == 1 else window + 1  # doit être impair
    w = min(w, n if n % 2 == 1 else n - 1)
    if w <= poly:
        return arr.copy()
    return savgol_filter(arr, w, poly)  # type: ignore[return-value]


def clean_essai(req: CleanRequest) -> CleanedEssai:
    """Nettoie un essai pressiométrique. Retourne CleanedEssai."""
    essai     = req.essai
    calibrage = req.calibrage
    # etalonnage pas encore utilisé pour correction de pression
    # (les données de cet exemple ne l'exigent pas)

    calib_f30, calib_f60 = _build_calib_interp(calibrage)

    # Pression différentielle (bar → MPa) avec signe
    pression_diff_mpa = essai.meta.pression_diff_bar / 10.0

    anomalies: List[Anomalie] = []
    coherences: List[CoherenceCheck] = []

    # ─── Étape 1 : extraire données brutes valides ──────────────────────────
    raw_points = []
    for m in essai.mesures:
        if m.P60_MPa is None:
            continue
        p = m.P60_MPa
        if not (P_MIN_MPa <= p <= P_MAX_MPa):
            anomalies.append(Anomalie(
                palier=m.palier, type="pression_hors_plage",
                description=f"P60={p:.3f} MPa hors plage [{P_MIN_MPa},{P_MAX_MPa}]",
                severity="error"
            ))
            continue
        raw_points.append(m)

    n_bruts = len(raw_points)
    if n_bruts == 0:
        return CleanedEssai(
            sheet_name=essai.sheet_name,
            depth_m=essai.depth_m,
            meta=essai.meta,
            points=[],
            anomalies=anomalies + [Anomalie(palier=0, type="aucune_donnee",
                                             description="Aucun palier valide",
                                             severity="error")],
            coherence=[CoherenceCheck(ok=False, message="Aucune donnée valide")],
            n_paliers_bruts=0,
            n_paliers_valides=0,
        )

    # ─── Étape 2 : vérifier monotonie des pressions ─────────────────────────
    p_arr_raw = np.array([m.P60_MPa for m in raw_points])
    for i in range(1, len(p_arr_raw)):
        if p_arr_raw[i] < p_arr_raw[i - 1]:
            anomalies.append(Anomalie(
                palier=raw_points[i].palier, type="pression_non_monotone",
                description=f"P[{i}]={p_arr_raw[i]:.3f} < P[{i-1}]={p_arr_raw[i-1]:.3f} MPa",
                severity="warning"
            ))
    # Dédoublonner par pression croissante
    seen_p = set()
    dedupe = []
    for m in raw_points:
        if m.P60_MPa not in seen_p:
            seen_p.add(m.P60_MPa)
            dedupe.append(m)
    dedupe.sort(key=lambda m: m.P60_MPa)
    raw_points = dedupe

    # ─── Étape 3 : isolation des volumes bruts ──────────────────────────────
    p_arr  = np.array([m.P60_MPa for m in raw_points])
    v30_arr = np.array([m.V30_cm3 if m.V30_cm3 is not None else np.nan for m in raw_points])
    v60_arr = np.array([m.V60_cm3 if m.V60_cm3 is not None else np.nan for m in raw_points])

    # ─── Étape 4 : outlier removal (z-score sur V60) ────────────────────────
    valid_mask = ~np.isnan(v60_arr)
    if valid_mask.sum() >= 4:
        z = zscore(v60_arr[valid_mask])
        outlier_idx = np.where(valid_mask)[0][np.abs(z) > req.outlier_sigma]  # type: ignore[index]
        for idx in outlier_idx:
            anomalies.append(Anomalie(
                palier=raw_points[idx].palier, type="outlier_volume",
                description=f"V60={v60_arr[idx]:.0f} cm³ déviation z={z[np.where(valid_mask)[0] == idx][0]:.1f}σ",
                severity="warning"
            ))
            v30_arr[idx] = np.nan
            v60_arr[idx] = np.nan

    # ─── Étape 5 : correction calibrage ─────────────────────────────────────
    v30_corr = v30_arr.copy()
    v60_corr = v60_arr.copy()

    if calib_f30 is not None and calib_f60 is not None:
        cal30 = calib_f30(p_arr)
        cal60 = calib_f60(p_arr)
        v30_corr = np.where(np.isnan(v30_arr), np.nan, v30_arr - cal30)
        v60_corr = np.where(np.isnan(v60_arr), np.nan, v60_arr - cal60)
        # Pincer à 0 (ne pas avoir de volumes négatifs)
        v30_corr = np.where(v30_corr < 0, 0, v30_corr)
        v60_corr = np.where(v60_corr < 0, 0, v60_corr)

    # ─── Étape 6 : correction pression différentielle ───────────────────────
    p_corr = p_arr + pression_diff_mpa
    p_corr = np.clip(p_corr, 0, P_MAX_MPa)

    # ─── Étape 7 : lissage Savitzky-Golay (sur volumes corrigés) ────────────
    v60_smooth = v60_corr.copy()
    valid_v60  = ~np.isnan(v60_corr)
    if valid_v60.sum() >= req.smooth_window:
        v60_tmp = v60_corr.copy()
        # Interpoler les NaN pour lissage
        xfull = np.arange(len(v60_tmp))
        xvalid = xfull[valid_v60]
        yvalid = v60_tmp[valid_v60]
        if len(xvalid) >= req.smooth_window:
            interp_full = np.interp(xfull, xvalid, yvalid)
            smoothed = _smooth(interp_full, req.smooth_window, req.smooth_polyorder)
            v60_smooth = np.where(valid_v60, smoothed, np.nan)

    v30_smooth = v30_corr.copy()
    valid_v30  = ~np.isnan(v30_corr)
    if valid_v30.sum() >= req.smooth_window:
        v30_tmp = v30_corr.copy()
        xfull  = np.arange(len(v30_tmp))
        xvalid = xfull[valid_v30]
        yvalid = v30_tmp[valid_v30]
        if len(xvalid) >= req.smooth_window:
            interp_full = np.interp(xfull, xvalid, yvalid)
            smoothed = _smooth(interp_full, req.smooth_window, req.smooth_polyorder)
            v30_smooth = np.where(valid_v30, smoothed, np.nan)

    # ─── Étape 8 : volume moyen et ratio creep ──────────────────────────────
    vm_arr     = np.nanmean(np.stack([v30_corr, v60_corr], axis=1), axis=1)
    creep_abs  = v60_corr - v30_corr
    _creep_mask = (v30_corr > 1) & ~np.isnan(v30_corr) & ~np.isnan(v60_corr)
    creep_ratio = np.full(len(v30_corr), np.nan)
    np.divide(v60_corr, v30_corr, out=creep_ratio, where=_creep_mask)

    # ─── Étape 9 : détection anomalies sur volumes ───────────────────────────
    anomalie_flags = [False] * len(raw_points)
    anomalie_types: List[Optional[str]] = [None] * len(raw_points)

    for i in range(1, len(raw_points)):
        if not np.isnan(v60_corr[i]) and not np.isnan(v60_corr[i - 1]):
            jump = abs(v60_corr[i] - v60_corr[i - 1])
            if jump > VOLUME_JUMP_cm3:
                anomalie_flags[i] = True
                anomalie_types[i] = "rupture_membrane"
                anomalies.append(Anomalie(
                    palier=raw_points[i].palier, type="rupture_membrane",
                    description=f"Saut volume ΔV={jump:.0f} cm³ (> {VOLUME_JUMP_cm3})",
                    severity="error"
                ))

    for i, m in enumerate(raw_points):
        if not np.isnan(creep_ratio[i]) and creep_ratio[i] > CREEP_RATIO_Pl:
            anomalies.append(Anomalie(
                palier=m.palier, type="fluage_critique",
                description=f"Creep ratio={creep_ratio[i]:.2f} > {CREEP_RATIO_Pl} → proche Pl",
                severity="warning"
            ))

    # ─── Étape 10 : cohérence globale ───────────────────────────────────────
    n_valid = len(raw_points)
    coherences.append(CoherenceCheck(
        ok=n_valid >= 5,
        message=f"{n_valid} paliers valides" + (" (minimum 5 recommandés)" if n_valid < 5 else "")
    ))

    p_range = float(p_corr[-1] - p_corr[0]) if len(p_corr) > 1 else 0
    coherences.append(CoherenceCheck(
        ok=p_range > 0.05,
        message=f"Plage de pression : {p_range:.3f} MPa" + (" (trop faible)" if p_range <= 0.05 else "")
    ))

    v_max = float(np.nanmax(v60_corr)) if not np.all(np.isnan(v60_corr)) else 0
    coherences.append(CoherenceCheck(
        ok=v_max < V_MAX_cm3,
        message=f"Volume max : {v_max:.0f} cm³"
    ))

    n_anom = sum(1 for a in anomalies if a.severity == "error")
    coherences.append(CoherenceCheck(
        ok=n_anom == 0,
        message=f"{n_anom} erreur(s) critiques détectée(s)"
    ))

    # ─── Construction des CleanedPoint ──────────────────────────────────────
    points: List[CleanedPoint] = []
    for i, m in enumerate(raw_points):
        def _f(v): return None if np.isnan(v) else float(round(v, 2))
        points.append(CleanedPoint(
            palier=m.palier,
            P60_raw_MPa=float(m.P60_MPa),
            P60_corr_MPa=float(round(p_corr[i], 4)),
            V30_raw_cm3=float(m.V30_cm3) if m.V30_cm3 is not None else None,
            V60_raw_cm3=float(m.V60_cm3) if m.V60_cm3 is not None else None,
            V30_corr_cm3=_f(v30_corr[i]),
            V60_corr_cm3=_f(v60_corr[i]),
            V30_smooth_cm3=_f(v30_smooth[i]),
            V60_smooth_cm3=_f(v60_smooth[i]),
            Vm_corr_cm3=_f(vm_arr[i]),
            creep_abs_cm3=_f(creep_abs[i]) if not np.isnan(creep_abs[i]) else None,
            creep_ratio=_f(creep_ratio[i]) if not np.isnan(creep_ratio[i]) else None,
            anomalie=anomalie_flags[i],
            anomalie_type=anomalie_types[i],
        ))

    return CleanedEssai(
        sheet_name=essai.sheet_name,
        depth_m=essai.depth_m,
        meta=essai.meta,
        points=points,
        anomalies=anomalies,
        coherence=coherences,
        n_paliers_bruts=n_bruts,
        n_paliers_valides=n_valid,
    )
