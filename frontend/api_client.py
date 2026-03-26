"""
Client HTTP asynchrone vers l'API FastAPI Pressiomètre (port 8502).
Toutes les méthodes sont async et utilisent httpx.AsyncClient.
"""
from __future__ import annotations
import json
from typing import List, Optional, Any
import httpx

from api.models import (
    ParsedFile, CleanedEssai, PressiometricParams,
    ProfileData, SectionData, PointCloud3D,
    CleanRequest, CalcRequest, ProfileRequest,
    SectionRequest, Cloud3DRequest, KibaliRequest, KibaliResponse,
)

BASE_URL = "http://127.0.0.1:8502"
TIMEOUT  = httpx.Timeout(300.0)   # 5 min max pour PDF / KIBALI


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status  = status
        self.detail  = detail
        super().__init__(f"HTTP {status} — {detail}")


def _raise(r: httpx.Response):
    if r.is_error:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise ApiError(r.status_code, detail)


class ApiClient:
    """Client synchrone pour usage depuis les slots Qt (appels dans un QThread)."""

    def __init__(self, base_url: str = BASE_URL):
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(timeout=TIMEOUT)

    # ── Health ────────────────────────────────────────────────────────────────
    def health(self) -> dict:
        r = self._client.get(f"{self._base}/health")
        _raise(r); return r.json()

    # ── KIBALI status ─────────────────────────────────────────────────────────
    def kibali_status(self) -> dict:
        r = self._client.get(f"{self._base}/kibali/status")
        _raise(r); return r.json()

    # ── Parse ─────────────────────────────────────────────────────────────────
    def parse_file(self, file_path: str) -> ParsedFile:
        with open(file_path, "rb") as fh:
            r = self._client.post(
                f"{self._base}/parse",
                files={"file": (file_path, fh, "application/octet-stream")},
            )
        _raise(r)
        return ParsedFile.model_validate(r.json())

    # ── Clean ─────────────────────────────────────────────────────────────────
    def clean_essai(self, req: CleanRequest) -> CleanedEssai:
        r = self._client.post(
            f"{self._base}/clean",
            content=req.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        _raise(r)
        return CleanedEssai.model_validate(r.json())

    # ── Calculate ─────────────────────────────────────────────────────────────
    def calculate(self, req: CalcRequest) -> PressiometricParams:
        r = self._client.post(
            f"{self._base}/calculate",
            content=req.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        _raise(r)
        return PressiometricParams.model_validate(r.json())

    # ── Profile ───────────────────────────────────────────────────────────────
    def build_profile(self, req: ProfileRequest) -> ProfileData:
        r = self._client.post(
            f"{self._base}/profile",
            content=req.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        _raise(r)
        return ProfileData.model_validate(r.json())

    # ── Section 2D ────────────────────────────────────────────────────────────
    def build_section(self, req: SectionRequest) -> SectionData:
        r = self._client.post(
            f"{self._base}/section",
            content=req.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        _raise(r)
        return SectionData.model_validate(r.json())

    # ── Cloud 3D ──────────────────────────────────────────────────────────────
    def build_cloud3d(self, req: Cloud3DRequest) -> PointCloud3D:
        r = self._client.post(
            f"{self._base}/cloud3d",
            content=req.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        _raise(r)
        return PointCloud3D.model_validate(r.json())

    # ── Rapport PDF ───────────────────────────────────────────────────────────
    def generate_report(
        self,
        parsed: ParsedFile,
        cleaned_list: List[CleanedEssai],
        params_list: List[PressiometricParams],
        profile: Optional[ProfileData] = None,
        boreholes: list = [],
        project_title: str = "",
        engineer: str = "",
        include_raw: bool = True,
        include_curves: bool = True,
        ai_summary: str = "",
        location: str = "",
        report_ref: str = "",
        use_web_norms: bool = False,
    ) -> bytes:
        form = {
            "parsed_json":    parsed.model_dump_json(),
            "cleaned_json":   json.dumps([c.model_dump() for c in cleaned_list]),
            "params_json":    json.dumps([p.model_dump() for p in params_list]),
            "profile_json":   profile.model_dump_json() if profile else "null",
            "boreholes_json": json.dumps(boreholes),
            "project_title":  project_title,
            "engineer":       engineer,
            "include_raw":    str(include_raw).lower(),
            "include_curves": str(include_curves).lower(),
            "ai_summary":     ai_summary,
            "location":       location,
            "report_ref":     report_ref,
            "use_web_norms":  str(use_web_norms).lower(),
        }
        r = self._client.post(f"{self._base}/report", data=form)
        _raise(r)
        return r.content

    # ── KIBALI ask ────────────────────────────────────────────────────────────
    def ask_kibali(self, question: str, context: str = "", max_new_tokens: int = 512) -> str:
        req = KibaliRequest(question=question, context=context, max_tokens=max_new_tokens)
        r = self._client.post(
            f"{self._base}/kibali/ask",
            content=req.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        _raise(r)
        return KibaliResponse.model_validate(r.json()).answer

    def close(self):
        self._client.close()

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass
