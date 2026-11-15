"""Composition root: builds the app and its shared resources. Run from backend/: uvicorn app.main:app --port 8000"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from concurrent.futures import ProcessPoolExecutor
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import ROUTERS
from .archive.collections import CollectionDiscovery
from .archive.fetch import FetchResult
from .archive.gaia import GaiaCatalog
from .archive.http import Http, make_http
from .archive.plan import fetch_exposures
from .archive.resolve import Resolver
from .archive.sia import SiaCache
from .config import configure_ssl, settings
from .domain import ProgressCallback
from .jobs import FetchFn, JobRunner, SequenceRequest
from .storage import BundleStore

FILES_PREFIX: Final = "/files"


def live_fetch(http: Http, discovery: CollectionDiscovery) -> FetchFn:
    sia_cache = SiaCache()

    async def fetch(request: SequenceRequest, progress: ProgressCallback) -> FetchResult:
        return await fetch_exposures(
            http,
            discovery,
            request.target,
            request.params,
            progress,
            cap_per_detector=settings.live_cap_per_detector,
            sia_cache=sia_cache,
        )

    return fetch


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    http = make_http()
    discovery = CollectionDiscovery()
    if settings.warm_collections:
        discovery.start(http)
    pool = ProcessPoolExecutor(max_workers=settings.pipeline_workers)
    store = BundleStore(settings.processed_dir, url_prefix=FILES_PREFIX, ttl_s=settings.processed_ttl_h * 3600)
    runner = JobRunner(live_fetch(http, discovery), store, executor=pool)
    gaia = GaiaCatalog()
    app.state.http = http
    app.state.resolver = Resolver()
    app.state.discovery = discovery
    app.state.runner = runner
    app.state.gaia = gaia
    try:
        yield
    finally:
        await discovery.aclose()
        await gaia.aclose()
        await runner.aclose()
        await http.client.aclose()
        pool.shutdown(wait=False, cancel_futures=True)


def create_app() -> FastAPI:
    configure_ssl()
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="SPHEREx Blink API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.mount(FILES_PREFIX, StaticFiles(directory=settings.processed_dir), name="files")
    for router in ROUTERS:
        app.include_router(router)
    return app


app = create_app()
