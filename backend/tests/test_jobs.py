"""Job runner behind /api/sequence (A3): keys, planning, states, cache. Synthetic cutouts, no network."""

from __future__ import annotations

import asyncio
import gzip
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest
from test_pipeline import MOVER, two_visits

from app.archive.collections import CollectionDiscovery
from app.archive.fetch import FetchResult
from app.archive.http import ArchiveError, make_http
from app.archive.sia import parse_sia_csv
from app.archive.visits import group_visits
from app.domain import Cutout, ExposureMeta, ProgressCallback, SequenceParams, SequenceResult, Target
from app.jobs import (
    ARCHIVE_DOWN,
    Job,
    JobError,
    JobRunner,
    SequenceRequest,
    collections_for_job,
    plan_exposures,
)

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).parent / "fixtures"
REQUEST = SequenceRequest(target=MOVER, params=SequenceParams(fov_arcmin=3.0))


def barnard_exposures() -> list[ExposureMeta]:
    raw = gzip.decompress((FIXTURES / "sia" / "barnard.csv.gz").read_bytes())
    return parse_sia_csv(raw.decode("utf-8"))


async def fetch_synthetic(request: SequenceRequest, progress: ProgressCallback) -> FetchResult:
    cutouts = two_visits()
    progress("downloading", len(cutouts), len(cutouts))
    return FetchResult(cutouts=cutouts, failed=[], off_detector=[])


async def finished(runner: JobRunner, job: Job) -> Job:
    async with asyncio.timeout(60):
        await runner.wait(job)
    return job


class FakeClock:
    def __init__(self) -> None:
        self.now = 1e9

    def __call__(self) -> float:
        return self.now


def test_key_ignores_detector_order_and_duplicates() -> None:
    a = SequenceRequest(target=MOVER, params=SequenceParams(detectors=(5, 3)))
    b = SequenceRequest(target=MOVER, params=SequenceParams(detectors=(3, 5, 3)))
    assert a.key == b.key


@pytest.mark.parametrize(
    "other",
    [
        SequenceRequest(target=Target(ra_deg=150.0, dec_deg=10.0, ref_epoch=2025.0), params=SequenceParams()),
        SequenceRequest(target=MOVER, params=SequenceParams(fov_arcmin=12.0)),
        SequenceRequest(target=MOVER, params=SequenceParams(mode="exposures")),
        SequenceRequest(target=MOVER, params=SequenceParams(detectors=(1,))),
    ],
)
def test_key_changes_with_the_sequence(other: SequenceRequest) -> None:
    assert other.key != SequenceRequest(target=MOVER, params=SequenceParams()).key


def test_plan_caps_each_detector_per_visit() -> None:
    plan = plan_exposures(barnard_exposures(), (1, 2, 3, 4, 5, 6), cap=8)
    per_visit_detector = Counter((visit.id, meta.detector) for visit, meta in plan)
    assert max(per_visit_detector.values()) == 8


def test_plan_keeps_only_requested_detectors() -> None:
    plan = plan_exposures(barnard_exposures(), (5,), cap=8)
    assert {meta.detector for _, meta in plan} == {5}


def test_plan_detector_selection_does_not_change_visits() -> None:
    exposures = barnard_exposures()
    plan = plan_exposures(exposures, (5,), cap=8)
    assert len({visit.id for visit, _ in plan}) == len(group_visits(exposures))


async def test_job_builds_a_bundle_served_under_files(tmp_path: Path) -> None:
    runner = JobRunner(fetch_synthetic, tmp_path)
    job = await finished(runner, runner.submit(REQUEST))
    assert job.state == "done", job.error
    assert job.result is not None
    assert (tmp_path / REQUEST.key / "sequence.json").is_file()
    data_url = job.result.frames[0].data
    assert data_url.startswith(f"/files/{REQUEST.key}/frames/")
    assert (tmp_path / data_url.removeprefix("/files/")).is_file()


async def test_finished_bundle_is_cached_until_the_ttl(tmp_path: Path) -> None:
    clock = FakeClock()
    runner = JobRunner(fetch_synthetic, tmp_path, ttl_s=3600, clock=clock)
    assert await runner.cached(REQUEST) is None
    await finished(runner, runner.submit(REQUEST))
    clock.now = (tmp_path / REQUEST.key / "sequence.json").stat().st_mtime + 60
    assert await runner.cached(REQUEST) is not None
    clock.now += 3600
    assert await runner.cached(REQUEST) is None


async def test_same_request_reuses_the_job(tmp_path: Path) -> None:
    runner = JobRunner(fetch_synthetic, tmp_path)
    first = runner.submit(REQUEST)
    assert runner.submit(REQUEST) is first
    await finished(runner, first)


async def test_failed_job_is_retried_as_a_new_job(tmp_path: Path) -> None:
    async def no_coverage(request: SequenceRequest, progress: ProgressCallback) -> FetchResult:
        raise JobError("No SPHEREx coverage at this position for the selected detectors.")

    runner = JobRunner(no_coverage, tmp_path)
    first = await finished(runner, runner.submit(REQUEST))
    assert first.error == "No SPHEREx coverage at this position for the selected detectors."
    assert runner.submit(REQUEST).id != first.id


async def test_archive_outage_reads_as_a_user_message(tmp_path: Path) -> None:
    async def irsa_down(request: SequenceRequest, progress: ProgressCallback) -> FetchResult:
        raise ArchiveError("HTTP 503 from irsa.ipac.caltech.edu", 503)

    runner = JobRunner(irsa_down, tmp_path)
    job = await finished(runner, runner.submit(REQUEST))
    assert job.error == ARCHIVE_DOWN


async def test_all_downloads_failed_is_an_archive_outage(tmp_path: Path) -> None:
    async def all_failed(request: SequenceRequest, progress: ProgressCallback) -> FetchResult:
        return FetchResult(cutouts=[], failed=[c.meta for c in two_visits()], off_detector=[])

    runner = JobRunner(all_failed, tmp_path)
    job = await finished(runner, runner.submit(REQUEST))
    assert job.error == ARCHIVE_DOWN


async def test_pipeline_bug_ends_the_job_with_an_error(tmp_path: Path) -> None:
    def broken_build(cutouts: Sequence[Cutout], target: Target, params: SequenceParams) -> SequenceResult:
        raise RuntimeError("boom")

    runner = JobRunner(fetch_synthetic, tmp_path, build=broken_build)
    job = await finished(runner, runner.submit(REQUEST))
    assert job.error == "Internal error while building the sequence."


async def test_progress_reports_stacking_after_download(tmp_path: Path) -> None:
    runner = JobRunner(fetch_synthetic, tmp_path)
    job = await finished(runner, runner.submit(REQUEST))
    assert job.progress.stage == "stacking"
    assert job.progress.done == job.progress.total


async def test_hung_collection_discovery_falls_back_to_the_known_list() -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200)

    http = make_http(transport=httpx.MockTransport(hang))
    async with http.client:
        collections = await collections_for_job(http, CollectionDiscovery(fallback=("spherex_dr1",)), wait_s=0.05)
    assert collections == ("spherex_dr1",)
