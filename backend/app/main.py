"""FastAPI entry point. Run from backend/: uvicorn app.main:app --reload --port 8000"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .archive.collections import CollectionDiscovery
from .archive.http import make_http
from .config import configure_ssl, settings
from .domain import DETECTORS, SequenceParams, Target
from .jobs import JobRunner, SequenceRequest, fetch_for_request
from .models import CacheStats, Health, JobAccepted, JobStatus, Overlays, ResolveResult, Sequence, Spectrum

configure_ssl()

settings.processed_dir.mkdir(parents=True, exist_ok=True)
settings.raw_dir.mkdir(parents=True, exist_ok=True)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    http = make_http()
    discovery = CollectionDiscovery()
    warm_up = asyncio.create_task(discovery.collections(http)) if settings.warm_collections else None
    pool = ProcessPoolExecutor(max_workers=settings.pipeline_workers)
    runner = JobRunner(partial(fetch_for_request, http, discovery), settings.processed_dir, executor=pool)
    app.state.discovery = discovery
    app.state.runner = runner
    try:
        yield
    finally:
        if warm_up is not None:
            warm_up.cancel()
        await runner.aclose()
        await http.client.aclose()
        pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="SPHEREx Blink API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.mount("/files", StaticFiles(directory=settings.processed_dir), name="files")


def get_runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner


def get_discovery(request: Request) -> CollectionDiscovery:
    discovery: CollectionDiscovery = request.app.state.discovery
    return discovery


Runner = Annotated[JobRunner, Depends(get_runner)]
Discovery = Annotated[CollectionDiscovery, Depends(get_discovery)]


def _cache_stats() -> CacheStats:
    raw_bytes = sum(p.stat().st_size for p in settings.raw_dir.rglob("*") if p.is_file())
    processed = sum(1 for p in settings.processed_dir.rglob("*.json") if p.is_file())
    return CacheStats(raw_mb=round(raw_bytes / 1e6, 1), processed_items=processed)


@app.get("/api/health", response_model=Health)
def health(discovery: Discovery) -> Health:
    return Health(status="ok", collections=list(discovery.current), cache=_cache_stats())


def _not_yet(track: str) -> HTTPException:
    return HTTPException(status_code=501, detail=f"Not implemented yet ({track})")


Ra = Annotated[float, Query(ge=0, lt=360, description="ICRS degrees")]
Dec = Annotated[float, Query(ge=-90, le=90, description="ICRS degrees")]
Pm = Annotated[float | None, Query(description="mas/yr; pmra includes cos(dec)")]
RefEpoch = Annotated[float, Query(description="Julian year of ra/dec")]
Fov = Annotated[float, Query(ge=2, le=30, description="arcmin")]
JobId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


@app.get("/api/resolve", response_model=ResolveResult)
def resolve(name: Annotated[str, Query(min_length=1, max_length=100)]) -> ResolveResult:
    raise _not_yet("Track A")


def _detectors(det: str) -> tuple[int, ...]:
    return DETECTORS if det == "all" else tuple(sorted({int(d) for d in det.split(",")}))


@app.get("/api/sequence", response_model=Sequence | JobAccepted)
async def sequence(
    runner: Runner,
    response: Response,
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
    """200 with the cached sequence, or 202 with a job to poll at `/api/jobs/{job_id}`."""
    request = SequenceRequest(
        target=Target(ra_deg=ra, dec_deg=dec, ref_epoch=ref_epoch, pmra_masyr=pmra, pmdec_masyr=pmdec),
        params=SequenceParams(fov_arcmin=fov, detectors=_detectors(det), mode=mode, include_allwise=allwise),
    )
    cached = await runner.cached(request)
    if cached is not None:
        return cached
    job = runner.submit(request)
    response.status_code = 202
    return JobAccepted(job_id=job.id)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def job(runner: Runner, job_id: JobId) -> JobStatus:
    found = runner.get(job_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return found.status()


@app.get("/api/spectrum", response_model=Spectrum)
def spectrum(ra: Ra, dec: Dec, pmra: Pm = None, pmdec: Pm = None, ref_epoch: RefEpoch = 2000.0) -> Spectrum:
    raise _not_yet("Track A, P1")


@app.get("/api/overlays", response_model=Overlays)
def overlays(ra: Ra, dec: Dec, fov: Fov, mjd: float) -> Overlays:
    raise _not_yet("Track A, P1")
