"""FastAPI entry point. Run from backend/: uvicorn app.main:app --reload --port 8000"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import configure_ssl, settings
from .models import CacheStats, Health, JobAccepted, JobStatus, Overlays, ResolveResult, Sequence, Spectrum

configure_ssl()

app = FastAPI(title="SPHEREx Blink API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET"],
    allow_headers=["*"],
)

settings.processed_dir.mkdir(parents=True, exist_ok=True)
settings.raw_dir.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.processed_dir), name="files")


def _cache_stats() -> CacheStats:
    raw_bytes = sum(p.stat().st_size for p in settings.raw_dir.rglob("*") if p.is_file())
    processed = sum(1 for p in settings.processed_dir.rglob("*.json") if p.is_file())
    return CacheStats(raw_mb=round(raw_bytes / 1e6, 1), processed_items=processed)


@app.get("/api/health", response_model=Health)
def health() -> Health:
    # Track A replaces the static list with TAP discovery (cached, fallback to settings).
    return Health(status="ok", collections=list(settings.fallback_collections), cache=_cache_stats())


def _not_yet(track: str) -> HTTPException:
    return HTTPException(status_code=501, detail=f"Not implemented yet ({track})")


Ra = Annotated[float, Query(ge=0, lt=360, description="ICRS degrees")]
Dec = Annotated[float, Query(ge=-90, le=90, description="ICRS degrees")]
Pm = Annotated[float | None, Query(description="mas/yr; pmra includes cos(dec)")]
RefEpoch = Annotated[float, Query(description="Julian year of ra/dec")]
Fov = Annotated[float, Query(ge=2, le=30, description="arcmin")]


@app.get("/api/resolve", response_model=ResolveResult)
def resolve(name: Annotated[str, Query(min_length=1, max_length=100)]) -> ResolveResult:
    raise _not_yet("Track A")


@app.get("/api/sequence", response_model=Sequence | JobAccepted)
def sequence(
    ra: Ra,
    dec: Dec,
    fov: Fov = 10.0,
    det: Annotated[str, Query(pattern=r"^(all|[1-6](,[1-6])*)$")] = "all",
    mode: Annotated[Literal["visit_stack", "exposures"], Query()] = "visit_stack",
    pmra: Pm = None,
    pmdec: Pm = None,
    ref_epoch: RefEpoch = 2000.0,
    allwise: bool = False,
) -> Sequence | JobAccepted:
    raise _not_yet("Track A")


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def job(job_id: str) -> JobStatus:
    raise _not_yet("Track A")


@app.get("/api/spectrum", response_model=Spectrum)
def spectrum(ra: Ra, dec: Dec, pmra: Pm = None, pmdec: Pm = None, ref_epoch: RefEpoch = 2000.0) -> Spectrum:
    raise _not_yet("Track A, P1")


@app.get("/api/overlays", response_model=Overlays)
def overlays(ra: Ra, dec: Dec, fov: Fov, mjd: float) -> Overlays:
    raise _not_yet("Track A, P1")
