"""FastAPI entry point. Run from backend/: uvicorn app.main:app --reload --port 8000"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import configure_ssl, settings
from .models import CacheStats, Health

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


@app.get("/api/resolve")
def resolve(name: str):
    raise _not_yet("Track A")


@app.get("/api/sequence")
def sequence(ra: float, dec: float, fov: float = 10.0, det: str = "all", mode: str = "visit_stack"):
    raise _not_yet("Track A")


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    raise _not_yet("Track A")


@app.get("/api/spectrum")
def spectrum(ra: float, dec: float):
    raise _not_yet("Track A, P1")


@app.get("/api/overlays")
def overlays(ra: float, dec: float, fov: float, mjd: float):
    raise _not_yet("Track A, P1")
