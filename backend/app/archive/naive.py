"""Temporary synchronous fetcher so the science pipeline (Track C) works on real data before Track A's concurrent
fetcher (`archive.fetch`) exists. Scripts only — never call it from a request path.

On 2026-11-14 the IRSA cutout service answered many requests with 503 already at 4 parallel workers, hence the
low worker count and the patient retries.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx
from astropy.time import Time

from ..astrometry import position_at
from ..config import settings
from ..domain import Cutout, ExposureMeta, ProgressCallback, Target, Visit
from .cutouts import cache_name, cutout_size_deg, cutout_url, load_cutout, strip_to_file
from .sia import SEARCH_RADIUS_DEG, SIA_URL, parse_sia_csv, sia_params
from .visits import cap_per_detector, group_visits

logger = logging.getLogger(__name__)

WORKERS: Final = 2
ATTEMPTS: Final = 5
MAX_BACKOFF_S: Final = 60.0
_RETRY_STATUS: Final = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class Sample:
    cutouts: list[Cutout]
    failed: list[ExposureMeta]


def _backoff_s(attempt: int, response: httpx.Response | None) -> float:
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after is not None and retry_after.isdigit():
        return min(float(retry_after), MAX_BACKOFF_S)
    return min(2.0**attempt, MAX_BACKOFF_S) * random.uniform(0.5, 1.5)  # noqa: S311 - jitter, not crypto


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=settings.http_timeout_s,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    )


def _get(client: httpx.Client, url: str, params: dict[str, str] | None = None) -> httpx.Response:
    for attempt in range(1, ATTEMPTS):
        response: httpx.Response | None = None
        try:
            response = client.get(url, params=params)
        except httpx.TransportError as exc:
            logger.info("Attempt %d failed for %s: %s", attempt, url, exc)
        else:
            if response.status_code not in _RETRY_STATUS:
                return response.raise_for_status()
            logger.info("Attempt %d got HTTP %d for %s", attempt, response.status_code, url)
        time.sleep(_backoff_s(attempt, response))
    return client.get(url, params=params).raise_for_status()


def query_exposures(
    client: httpx.Client, target: Target, collections: Sequence[str], radius_deg: float = SEARCH_RADIUS_DEG
) -> list[ExposureMeta]:
    ra_deg, dec_deg = position_at(target, float(Time.now().mjd))
    found: dict[str, ExposureMeta] = {}
    for collection in collections:
        response = _get(client, SIA_URL, sia_params(collection, ra_deg, dec_deg, radius_deg))
        for meta in parse_sia_csv(response.text):
            found.setdefault(meta.key, meta)
    return sorted(found.values(), key=lambda m: (m.mjd_start, m.detector))


def fetch_one(
    client: httpx.Client,
    meta: ExposureMeta,
    visit_id: str,
    center: tuple[float, float],
    size_deg: float,
    raw_dir: Path,
) -> Cutout:
    """Download (or reuse from `raw_dir`) one EPSF-stripped cutout."""
    path = raw_dir / cache_name(meta, center[0], center[1], size_deg)
    if not path.exists():
        response = _get(client, cutout_url(meta.access_url, center[0], center[1], size_deg))
        strip_to_file(response.content, path)
    return load_cutout(path, meta, visit_id)


def fetch_sample(
    target: Target,
    *,
    fov_arcmin: float = 10.0,
    max_per_detector: int = 4,
    collections: Sequence[str] | None = None,
    raw_dir: Path | None = None,
    progress: ProgressCallback | None = None,
) -> Sample:
    """All visits of `target`, at most `max_per_detector` exposures per detector and visit, centred on the
    target's position at the middle of the data span. Exposures that still fail after retries are listed in
    `Sample.failed` instead of aborting the whole sample."""
    cache = raw_dir or settings.raw_dir
    cache.mkdir(parents=True, exist_ok=True)
    with make_client() as client:
        exposures = query_exposures(client, target, collections or settings.fallback_collections)
        plan: list[tuple[Visit, ExposureMeta]] = [
            (visit, meta) for visit in group_visits(exposures) for meta in cap_per_detector(visit, max_per_detector)
        ]
        if not plan:
            return Sample(cutouts=[], failed=[])
        first = min(meta.mjd_mid for _, meta in plan)
        last = max(meta.mjd_mid for _, meta in plan)
        center = position_at(target, (first + last) / 2)
        size_deg = cutout_size_deg(fov_arcmin, target, last - first)

        cutouts: list[Cutout] = []
        failed: list[ExposureMeta] = []
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {
                pool.submit(fetch_one, client, meta, visit.id, center, size_deg, cache): meta for visit, meta in plan
            }
            for future in as_completed(futures):
                try:
                    cutouts.append(future.result())
                except httpx.HTTPError as exc:
                    logger.warning("Giving up on %s: %s", futures[future].key, exc)
                    failed.append(futures[future])
                if progress is not None:
                    progress("fetch", len(cutouts) + len(failed), len(plan))
    cutouts.sort(key=lambda c: (c.mjd_avg, c.meta.detector))
    return Sample(cutouts=cutouts, failed=failed)
