"""Concurrent archive access for request paths (Track A: A1, A2).

Same results as `archive.naive`, but async: one shared client (`http.Http`), at most `settings.max_concurrency`
requests in flight, retries with backoff and jitter. Fetch strategy (OD-4): S3 range reads, IRSA `ibe`
multi-range as fallback. `cutouts.load_cutout` is blocking: run it in a worker thread.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import anyio
from astropy.time import Time

from ..astrometry import position_at
from ..domain import Cutout, ExposureMeta, ProgressCallback, Target, Visit
from .http import ArchiveError, Http, get
from .sia import SEARCH_RADIUS_DEG, SIA_URL, parse_sia_csv, sia_params


def _position_now(target: Target) -> tuple[float, float]:
    return position_at(target, float(Time.now().mjd))


async def query_exposures(
    http: Http, target: Target, collections: Sequence[str], radius_deg: float = SEARCH_RADIUS_DEG
) -> list[ExposureMeta]:
    """All exposures of `collections` covering the target, unique by (obs_id, detector), sorted by time.

    Collections are queried concurrently; any collection failing fails the query, because a silently missing
    collection would drop whole visits. On duplicates the earlier collection in `collections` wins.
    """
    ra_deg, dec_deg = await anyio.to_thread.run_sync(_position_now, target)
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(get(http, SIA_URL, sia_params(collection, ra_deg, dec_deg, radius_deg)))
                for collection in collections
            ]
    except* ArchiveError as failures:
        first = failures.exceptions[0]
        raise ArchiveError(f"SIA query failed: {first}", getattr(first, "status", None)) from failures

    found: dict[str, ExposureMeta] = {}
    for task in tasks:
        for meta in parse_sia_csv(task.result().text):
            found.setdefault(meta.key, meta)
    return sorted(found.values(), key=lambda m: (m.mjd_start, m.detector))


async def fetch_cutouts(
    http: Http,
    plan: Sequence[tuple[Visit, ExposureMeta]],
    center: tuple[float, float],
    size_deg: float,
    progress: ProgressCallback | None = None,
) -> list[Cutout]:
    raise NotImplementedError("Track A: A2")
