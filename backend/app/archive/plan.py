"""From a target to the cutouts of a live sequence: collections → SIA → visits → capped plan → downloads."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean
from typing import Final

import anyio

from ..astrometry import position_at
from ..domain import ExposureMeta, ProgressCallback, SequenceParams, Target, Visit
from .collections import CollectionDiscovery
from .cutouts import cutout_size_deg
from .fetch import FetchResult, fetch_cutouts, query_exposures
from .http import Http
from .sia import SiaCache
from .visits import cap_per_detector, group_visits

DISCOVERY_WAIT_S: Final = 30.0
# The frontend recognises this text (frontend/src/api/sequence.ts); JobStatus has no error code yet.
NO_COVERAGE: Final = "No SPHEREx coverage at this position for the selected detectors."


class NoCoverageError(Exception):
    """No exposure of the selected detectors covers the target."""

    def __init__(self) -> None:
        super().__init__(NO_COVERAGE)


def plan_exposures(
    exposures: Sequence[ExposureMeta], detectors: Sequence[int], cap: int
) -> list[tuple[Visit, ExposureMeta]]:
    """Visits are grouped over all detectors, so a detector selection never changes how visits are split."""
    wanted = set(detectors)
    return [
        (visit, meta)
        for visit in group_visits(exposures)
        for meta in cap_per_detector(visit, cap)
        if meta.detector in wanted
    ]


async def collections_for_job(
    http: Http, discovery: CollectionDiscovery, wait_s: float = DISCOVERY_WAIT_S
) -> tuple[str, ...]:
    """A hung TAP (seen 2026-11-14: > 60 s per attempt, 5 attempts) must not hold the job: use the last known list."""
    return await discovery.collections(http, wait_s=wait_s)


async def fetch_exposures(
    http: Http,
    discovery: CollectionDiscovery,
    target: Target,
    params: SequenceParams,
    progress: ProgressCallback,
    *,
    cap_per_detector: int,
    sia_cache: SiaCache | None = None,
) -> FetchResult:
    collections = await collections_for_job(http, discovery)
    exposures = await query_exposures(http, target, collections, cache=sia_cache)
    plan = plan_exposures(exposures, params.detectors, cap_per_detector)
    if not plan:
        raise NoCoverageError
    first = min(meta.mjd_mid for _, meta in plan)
    last = max(meta.mjd_mid for _, meta in plan)
    center = await anyio.to_thread.run_sync(position_at, target, fmean((first, last)))
    size_deg = cutout_size_deg(params.fov_arcmin, target, last - first)
    progress("downloading", 0, len(plan))
    return await fetch_cutouts(
        http, plan, center, size_deg, progress=lambda _stage, done, total: progress("downloading", done, total)
    )
