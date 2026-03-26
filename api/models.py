"""
Modèles Pydantic pour l'API Pressiomètre IA
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# ─── Données brutes parsées ───────────────────────────────────────────────────

class RawMesure(BaseModel):
    palier: int
    V30_cm3: Optional[float] = None
    P60_MPa: Optional[float] = None
    V60_cm3: Optional[float] = None

class EssaiMeta(BaseModel):
    projet: Optional[str] = None
    localisation: Optional[str] = None
    ref_sondage: Optional[str] = None
    ref_essai: Optional[str] = None
    ref_sonde: Optional[str] = None
    profondeur_m: Optional[float] = None
    ref_etalonnage: Optional[str] = None
    ref_calibrage: Optional[str] = None
    passe_forage: Optional[str] = None
    technique: Optional[str] = None
    outil_forage: Optional[str] = None
    pression_diff_bar: float = 0.0
    type_tubulure: Optional[str] = None
    date: Optional[str] = None

class EssaiRaw(BaseModel):
    sheet_name: str
    meta: EssaiMeta
    mesures: List[RawMesure]
    depth_m: Optional[float] = None
    is_calibrage: bool = False
    is_etalonnage: bool = False

class ParsedFile(BaseModel):
    filename: str
    essais: Dict[str, EssaiRaw]          # keyed by sheet_name
    calibrage: Optional[EssaiRaw] = None
    etalonnages: Dict[str, EssaiRaw] = {}


# ─── Données nettoyées ────────────────────────────────────────────────────────

class CleanedPoint(BaseModel):
    palier: int
    P60_raw_MPa: float
    P60_corr_MPa: float
    V30_raw_cm3: Optional[float] = None
    V60_raw_cm3: Optional[float] = None
    V30_corr_cm3: Optional[float] = None
    V60_corr_cm3: Optional[float] = None
    V30_smooth_cm3: Optional[float] = None
    V60_smooth_cm3: Optional[float] = None
    Vm_corr_cm3: Optional[float] = None  # mean corrected volume
    creep_abs_cm3: Optional[float] = None  # V60 - V30 (creep)
    creep_ratio: Optional[float] = None   # V60 / V30
    anomalie: bool = False
    anomalie_type: Optional[str] = None

class Anomalie(BaseModel):
    palier: int
    type: str
    description: str
    severity: str  # "warning" | "error"

class CoherenceCheck(BaseModel):
    ok: bool
    message: str

class CleanedEssai(BaseModel):
    sheet_name: str
    depth_m: Optional[float]
    meta: EssaiMeta
    points: List[CleanedPoint]
    anomalies: List[Anomalie] = []
    coherence: List[CoherenceCheck] = []
    n_paliers_bruts: int = 0
    n_paliers_valides: int = 0


# ─── Paramètres pressiométriques ─────────────────────────────────────────────

class PressiometricParams(BaseModel):
    sheet_name: str
    depth_m: Optional[float]
    ref_sondage: Optional[str] = None
    # Paramètres Ménard
    V0_probe_cm3: float = 535.0     # volume initial sonde
    Pf_MPa: Optional[float] = None  # pression de fluage
    Pl_MPa: Optional[float] = None  # pression limite
    Pl_star_MPa: Optional[float] = None  # pression limite nette (Pl - u0)
    Em_MPa: Optional[float] = None  # module pressiométrique
    ratio_Em_Pl: Optional[float] = None
    # Zones de la courbe
    P_elastic_min_MPa: Optional[float] = None
    P_elastic_max_MPa: Optional[float] = None
    V_elastic_min_cm3: Optional[float] = None
    V_elastic_max_cm3: Optional[float] = None
    slope_elastic_MPa_per_cm3: Optional[float] = None
    # Classification
    sol_type: str = "Indéterminé"
    sol_color: str = "#888888"
    nc_status: str = "NC"  # NC, SC, remanie
    # Qualité
    n_paliers: int = 0
    n_anomalies: int = 0
    qualite: str = "?"  # A, B, C, D
    notes: List[str] = []
    # Cohérence
    is_coherent: bool = True
    coherence_checks: List[CoherenceCheck] = []

class ProfileData(BaseModel):
    sondage: str
    depths: List[float]
    Em_MPa: List[Optional[float]]
    Pf_MPa: List[Optional[float]]
    Pl_MPa: List[Optional[float]]
    sol_types: List[str]
    sol_colors: List[str]
    Em_Pl_ratios: List[Optional[float]]

class SectionPoint(BaseModel):
    x_m: float         # position horizontale sur la coupe
    depth_m: float     # profondeur
    Em_MPa: Optional[float]
    Pl_MPa: Optional[float]
    sol_type: str
    sol_color: str
    sondage: str

class SectionData(BaseModel):
    title: str
    points: List[SectionPoint]
    boreholes: List[Dict[str, Any]]  # [{name, x_m, max_depth_m}]
    layers: List[Dict[str, Any]]     # interpolated layers

class PointCloud3D(BaseModel):
    points: List[Dict[str, Any]]  # [{x,y,z,Em,Pl,sol_type,sol_color,sondage}]
    boreholes: List[Dict[str, Any]]
    bounds: Dict[str, float]      # {xmin, xmax, ymin, ymax, zmin, zmax}
    grid_Em: Optional[List[List[float]]] = None
    grid_Pl: Optional[List[List[float]]] = None
    grid_x: Optional[List[float]] = None
    grid_y: Optional[List[float]] = None


# ─── Requêtes / Réponses API ──────────────────────────────────────────────────

class CleanRequest(BaseModel):
    essai: EssaiRaw
    calibrage: Optional[EssaiRaw] = None
    etalonnage: Optional[EssaiRaw] = None
    probe_v0_cm3: float = 535.0
    smooth_window: int = 5        # Savitzky-Golay window
    smooth_polyorder: int = 2
    outlier_sigma: float = 3.0    # z-score threshold

class CalcRequest(BaseModel):
    cleaned: CleanedEssai
    probe_v0_cm3: float = 535.0

class ProfileRequest(BaseModel):
    params_list: List[PressiometricParams]

class SectionRequest(BaseModel):
    params_list: List[PressiometricParams]
    boreholes: List[Dict[str, Any]]  # [{name, x_m, y_m}]
    n_interp: int = 50

class Cloud3DRequest(BaseModel):
    params_list: List[PressiometricParams]
    boreholes: List[Dict[str, Any]]  # [{name, x_m, y_m}]
    grid_resolution: int = 20

class ReportRequest(BaseModel):
    parsed: ParsedFile
    cleaned_list: List[CleanedEssai]
    params_list: List[PressiometricParams]
    profile: Optional[ProfileData] = None
    section: Optional[SectionData] = None
    project_title: str = "Rapport Pressiométrique"
    engineer: str = ""
    include_raw: bool = True
    include_curves: bool = True
    include_ai_summary: bool = False
    ai_summary: str = ""

class KibaliRequest(BaseModel):
    question: str
    context: str = ""
    max_tokens: int = 512

class KibaliResponse(BaseModel):
    answer: str
    model_loaded: bool
    error: Optional[str] = None
