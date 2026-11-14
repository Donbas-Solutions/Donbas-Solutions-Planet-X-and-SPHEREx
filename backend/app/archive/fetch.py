"""Concurrent archive access for request paths (Track A: A1, A2).

Same results as `archive.naive`, but async: one shared `httpx.AsyncClient`, at most `settings.max_concurrency`
requests in flight, retries with backoff and jitter, atomic writes into the raw cache, progress reporting.
Building blocks to reuse: `sia.parse_sia_csv`, `visits.group_visits`, `visits.cap_per_detector`,
`cutouts.cutout_url`, `cutouts.cutout_size_deg`, `cutouts.cache_name`, `cutouts.strip_to_file`,
`cutouts.load_cutout` (blocking: run it in a worker thread).
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from ..domain import Cutout, ExposureMeta, ProgressCallback, Target, Visit


async def query_exposures(client: httpx.AsyncClient, target: Target, collections: Sequence[str]) -> list[ExposureMeta]:
    raise NotImplementedError("Track A: A1")


async def fetch_cutouts(
    client: httpx.AsyncClient,
    plan: Sequence[tuple[Visit, ExposureMeta]],
    center: tuple[float, float],
    size_deg: float,
    progress: ProgressCallback | None = None,
) -> list[Cutout]:
    raise NotImplementedError("Track A: A2")
