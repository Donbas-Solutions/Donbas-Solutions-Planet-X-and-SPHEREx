"""Concurrent archive access for request paths (Track A: A1, A2).

Same results as `archive.naive`, but async: one shared client (`http.Http`), at most `settings.max_concurrency`
requests in flight, retries with backoff and jitter. Fetch order per exposure (OD-4): S3 range reads, IRSA `ibe`
multi-range reads, the IRSA cutout service. Every source writes the same stripped file into the raw cache.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import anyio
from astropy.time import Time

from ..astrometry import position_at
from ..config import settings
from ..domain import Cutout, ExposureMeta, ProgressCallback, Target, Visit
from .cutouts import cache_name, cutout_url, load_cutout, strip_to_file
from .http import ArchiveError, Http, get, raise_first
from .ranges import OffDetectorError, fetch_window, s3_url
from .sia import SEARCH_RADIUS_DEG, SIA_URL, parse_sia_csv, sia_params

logger = logging.getLogger(__name__)

Source = Literal["s3", "ibe", "cutout"]
SOURCES: Final[tuple[Source, ...]] = ("s3", "ibe", "cutout")


@dataclass(frozen=True)
class FetchResult:
    cutouts: list[Cutout]
    failed: list[ExposureMeta]
    off_detector: list[ExposureMeta]


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
        raise_first(failures)

    found: dict[str, ExposureMeta] = {}
    for task in tasks:
        for meta in parse_sia_csv(task.result().text):
            found.setdefault(meta.key, meta)
    return sorted(found.values(), key=lambda m: (m.mjd_start, m.detector))


async def _download(
    http: Http, source: Source, meta: ExposureMeta, center: tuple[float, float], size_deg: float, path: Path
) -> None:
    if source == "cutout":
        response = await get(http, cutout_url(meta.access_url, center[0], center[1], size_deg))
        await anyio.to_thread.run_sync(strip_to_file, response.content, path)
        return
    url = s3_url(meta.access_url) if source == "s3" else meta.access_url
    await fetch_window(http, url, center, size_deg, path, multi=source == "ibe")


async def fetch_one(
    http: Http,
    meta: ExposureMeta,
    visit_id: str,
    center: tuple[float, float],
    size_deg: float,
    raw_dir: Path,
    sources: Sequence[Source] = SOURCES,
) -> Cutout:
    """Reuse the cached window or download it from the first source that works."""
    path = raw_dir / cache_name(meta, center[0], center[1], size_deg)
    if not await anyio.Path(path).exists():
        errors: list[str] = []
        for source in sources:
            try:
                await _download(http, source, meta, center, size_deg, path)
            except OffDetectorError:
                raise
            except ArchiveError as exc:
                logger.info("%s failed for %s: %s", source, meta.key, exc)
                errors.append(f"{source}: {exc}")
            else:
                break
        else:
            raise ArchiveError(f"All sources failed for {meta.key} ({'; '.join(errors)})")
    return await anyio.to_thread.run_sync(load_cutout, path, meta, visit_id)


async def fetch_cutouts(
    http: Http,
    plan: Sequence[tuple[Visit, ExposureMeta]],
    center: tuple[float, float],
    size_deg: float,
    progress: ProgressCallback | None = None,
    raw_dir: Path | None = None,
) -> FetchResult:
    """Cutouts of every planned exposure, sorted by time and detector. Exposures that fail on every source go to
    `failed` and exposures whose window misses the detector to `off_detector`; neither fails the sequence."""
    cache = raw_dir or settings.raw_dir
    in_flight = asyncio.Semaphore(settings.max_concurrency)
    cutouts: list[Cutout] = []
    failed: list[ExposureMeta] = []
    off_detector: list[ExposureMeta] = []

    async def one(visit: Visit, meta: ExposureMeta) -> None:
        async with in_flight:
            try:
                cutouts.append(await fetch_one(http, meta, visit.id, center, size_deg, cache))
            except OffDetectorError as exc:
                logger.info("Skipping %s: %s", meta.key, exc)
                off_detector.append(meta)
            except ArchiveError as exc:
                logger.warning("Giving up on %s: %s", meta.key, exc)
                failed.append(meta)
        if progress is not None:
            progress("fetch", len(cutouts) + len(failed) + len(off_detector), len(plan))

    async with asyncio.TaskGroup() as group:
        for visit, meta in plan:
            group.create_task(one(visit, meta))
    cutouts.sort(key=lambda c: (c.mjd_avg, c.meta.detector))
    return FetchResult(cutouts=cutouts, failed=failed, off_detector=off_detector)
