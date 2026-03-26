"""
FastAPI main — Pressiomètre API
Routes :
  GET  /health
  GET  /kibali/status
  POST /parse          (multipart file upload)
  POST /clean
  POST /calculate
  POST /profile
  POST /section
  POST /cloud3d
  POST /report         (retourne bytes PDF)
  POST /kibali/ask
"""
from __future__ import annotations
import io
import json
import logging
import sys
import traceback
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
import uvicorn

# ─── Logging console (visible dans le terminal launcher) ─────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="[API %(levelname)s] %(asctime)s — %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logger = logging.getLogger("pressiometre")

# Réduire le bruit des bibliothèques tierces
for _noisy in ("matplotlib", "PIL", "fontTools", "urllib3",
               "asyncio", "uvicorn.access", "uvicorn.error",
               "httpx", "transformers", "torch", "bitsandbytes"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

from .parser     import load_excel
from .cleaner    import clean_essai
from .calculator import compute_params, build_profile, build_section, build_cloud3d
from .report     import generate_pdf
from .kibali     import load_async as kibali_load_async, ask as kibali_ask, is_ready as kibali_is_ready, get_error as kibali_get_error
from .models     import (
    ParsedFile, CleanRequest, CleanedEssai,
    CalcRequest, PressiometricParams,
    ProfileRequest, ProfileData,
    SectionRequest, SectionData,
    Cloud3DRequest, PointCloud3D,
    KibaliRequest, KibaliResponse,
)

# ─── Lifespan (démarrage KIBALI en arrière-plan) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== PressiomètreAPI démarrage ===")
    kibali_load_async()        # Lance le thread de chargement NF4 4-bit
    yield
    logger.info("=== PressiomètreAPI arrêt ===")

app = FastAPI(
    title="PressiomètreAPI",
    version="2.0.0",
    description="API géotechnique pressiométrique (NF P 94-110) + IA KIBALI",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Santé ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ─── Statut KIBALI ───────────────────────────────────────────────────────────
@app.get("/kibali/status")
def kibali_status():
    return {
        "ready": kibali_is_ready(),
        "error": kibali_get_error(),
    }


# ─── Handler global d'exceptions non gérées ─────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error("Exception non gérée sur %s\n%s", request.url.path, tb)
    return JSONResponse(status_code=500, content={"detail": f"Erreur interne : {exc}", "traceback": tb})


# ─── Parse fichier Excel ─────────────────────────────────────────────────────
@app.post("/parse", response_model=ParsedFile)
async def parse_file(file: UploadFile = File(...)):
    logger.info("Parsing fichier : %s (taille ~%s o)", file.filename, file.size)
    content = await file.read()
    try:
        buf = io.BytesIO(content)
        parsed = load_excel(buf, filename=file.filename or "upload.xlsx")
        logger.info("Parsing OK — %d essais, calibrage=%s, étalonnages=%d",
                    len(parsed.essais), parsed.calibrage is not None, len(parsed.etalonnages))
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("Erreur parsing %s :\n%s", file.filename, tb)
        raise HTTPException(status_code=422, detail=f"Erreur parsing : {exc}\n\n{tb}")
    return parsed


# ─── Nettoyage d'un essai ────────────────────────────────────────────────────
@app.post("/clean", response_model=CleanedEssai)
def clean(req: CleanRequest):
    try:
        result = clean_essai(req)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur nettoyage : {exc}\n{traceback.format_exc()}")
    return result


# ─── Calcul paramètres Ménard ────────────────────────────────────────────────
@app.post("/calculate", response_model=PressiometricParams)
def calculate(req: CalcRequest):
    try:
        result = compute_params(req.cleaned, probe_v0_cm3=req.probe_v0_cm3)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur calcul : {exc}\n{traceback.format_exc()}")
    return result


# ─── Profil géotechnique ─────────────────────────────────────────────────────
@app.post("/profile", response_model=ProfileData)
def profile(req: ProfileRequest):
    try:
        result = build_profile(req.params_list)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur profil : {exc}")
    return result


# ─── Coupe géologique ────────────────────────────────────────────────────────
@app.post("/section", response_model=SectionData)
def section(req: SectionRequest):
    try:
        result = build_section(req.params_list, req.boreholes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur coupe : {exc}")
    return result


# ─── Nuage de points 3D ──────────────────────────────────────────────────────
@app.post("/cloud3d", response_model=PointCloud3D)
def cloud3d(req: Cloud3DRequest):
    try:
        result = build_cloud3d(req.params_list, req.boreholes, grid_res=req.grid_resolution)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur 3D : {exc}")
    return result


# ─── Génération PDF ──────────────────────────────────────────────────────────
@app.post("/report")
def report(
    parsed_json:       str  = Form(...),
    cleaned_json:      str  = Form(...),
    params_json:       str  = Form(...),
    profile_json:      str  = Form("null"),
    boreholes_json:    str  = Form("[]"),
    project_title:     str  = Form(""),
    engineer:          str  = Form(""),
    include_raw:       bool = Form(True),
    include_curves:    bool = Form(True),
    ai_summary:        str  = Form(""),
    location:          str  = Form(""),
    report_ref:        str  = Form(""),
    use_web_norms:     bool = Form(False),
):
    try:
        parsed     = ParsedFile.model_validate_json(parsed_json)
        cleaned_l  = [CleanedEssai.model_validate(c) for c in json.loads(cleaned_json)]
        params_l   = [PressiometricParams.model_validate(p) for p in json.loads(params_json)]
        profile    = ProfileData.model_validate_json(profile_json) if profile_json != "null" else None
        boreholes  = json.loads(boreholes_json)

        pdf_bytes = generate_pdf(
            parsed=parsed,
            cleaned_list=cleaned_l,
            params_list=params_l,
            profile=profile,
            boreholes=boreholes,
            project_title=project_title,
            engineer=engineer,
            include_raw=include_raw,
            include_curves=include_curves,
            ai_summary=ai_summary,
            location=location,
            report_ref=report_ref,
            use_web_norms=use_web_norms,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur PDF : {exc}\n{traceback.format_exc()}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=rapport_pressiometrique.pdf"},
    )


# ─── KIBALI ask ──────────────────────────────────────────────────────────────
@app.post("/kibali/ask", response_model=KibaliResponse)
def kibali_ask_route(req: KibaliRequest):
    if not kibali_is_ready():
        err = kibali_get_error()
        if err:
            raise HTTPException(status_code=503, detail=f"KIBALI erreur : {err}")
        raise HTTPException(status_code=503, detail="KIBALI en cours de chargement…")
    try:
        answer = kibali_ask(
            question=req.question,
            context=req.context,
            max_tokens=req.max_tokens,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur inférence KIBALI : {exc}")
    return KibaliResponse(answer=answer, model_loaded=True)


# ─── Entrée directe (développement) ──────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("api.main:app", host="127.0.0.1", port=8502, reload=False)
