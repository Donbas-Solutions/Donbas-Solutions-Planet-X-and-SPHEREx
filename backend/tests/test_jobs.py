"""Job runner behind /api/sequence (A3) and the target spectra it measures. Synthetic cutouts, no network."""

from __future__ import annotations

import asyncio
import gzip
import os
import time
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from test_pipeline import MOVER, two_visits

from app.archive.collections import CollectionDiscovery
from app.archive.fetch import FetchResult
from app.archive.http import ArchiveError, make_http
from app.archive.plan import NO_COVERAGE, NoCoverageError, collections_for_job, plan_exposures
from app.archive.sia import parse_sia_csv
from app.archive.visits import group_visits
from app.domain import Cutout, ExposureMeta, ProgressCallback, SequenceParams, SequenceResult, Target
from app.jobs import (
    ARCHIVE_DOWN,
    Job,
    JobRunner,
    SequenceRequest,
    target_key,
)
from app.models import Spectrum, SpectrumPoint
from app.storage import SPECTRA_DIR, SPECTRUM, BundleStore, store_spectrum

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


def store_at(root: Path, *, ttl_s: float = 3600.0, clock: Callable[[], float] = time.time) -> BundleStore:
    return BundleStore(root, url_prefix="/files", ttl_s=ttl_s, clock=clock)


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
    runner = JobRunner(fetch_synthetic, store_at(tmp_path))
    job = await finished(runner, runner.submit(REQUEST))
    assert job.state == "done", job.error
    assert job.result is not None
    assert (tmp_path / REQUEST.key / "sequence.json").is_file()
    data_url = job.result.frames[0].data
    assert data_url.startswith(f"/files/{REQUEST.key}/frames/")
    assert (tmp_path / data_url.removeprefix("/files/")).is_file()


async def test_finished_bundle_is_cached_until_the_ttl(tmp_path: Path) -> None:
    clock = FakeClock()
    runner = JobRunner(fetch_synthetic, store_at(tmp_path, clock=clock), clock=clock)
    assert await runner.cached(REQUEST) is None
    await finished(runner, runner.submit(REQUEST))
    clock.now = (tmp_path / REQUEST.key / "sequence.json").stat().st_mtime + 60
    assert await runner.cached(REQUEST) is not None
    clock.now += 3600
    assert await runner.cached(REQUEST) is None


async def test_same_request_reuses_the_job(tmp_path: Path) -> None:
    runner = JobRunner(fetch_synthetic, store_at(tmp_path))
    first = runner.submit(REQUEST)
    assert runner.submit(REQUEST) is first
    await finished(runner, first)


async def test_failed_job_is_retried_as_a_new_job(tmp_path: Path) -> None:
    async def no_coverage(request: SequenceRequest, progress: ProgressCallback) -> FetchResult:
        raise NoCoverageError

    runner = JobRunner(no_coverage, store_at(tmp_path))
    first = await finished(runner, runner.submit(REQUEST))
    assert first.error == NO_COVERAGE
    assert runner.submit(REQUEST).id != first.id


async def test_archive_outage_reads_as_a_user_message(tmp_path: Path) -> None:
    async def irsa_down(request: SequenceRequest, progress: ProgressCallback) -> FetchResult:
        raise ArchiveError("HTTP 503 from irsa.ipac.caltech.edu", 503)

    runner = JobRunner(irsa_down, store_at(tmp_path))
    job = await finished(runner, runner.submit(REQUEST))
    assert job.error == ARCHIVE_DOWN


async def test_all_downloads_failed_is_an_archive_outage(tmp_path: Path) -> None:
    async def all_failed(request: SequenceRequest, progress: ProgressCallback) -> FetchResult:
        return FetchResult(cutouts=[], failed=[c.meta for c in two_visits()], off_detector=[])

    runner = JobRunner(all_failed, store_at(tmp_path))
    job = await finished(runner, runner.submit(REQUEST))
    assert job.error == ARCHIVE_DOWN


async def test_pipeline_bug_ends_the_job_with_an_error(tmp_path: Path) -> None:
    def broken_build(cutouts: Sequence[Cutout], target: Target, params: SequenceParams) -> SequenceResult:
        raise RuntimeError("boom")

    runner = JobRunner(fetch_synthetic, store_at(tmp_path), build=broken_build)
    job = await finished(runner, runner.submit(REQUEST))
    assert job.error == "Internal error while building the sequence."


async def test_progress_reports_stacking_after_download(tmp_path: Path) -> None:
    runner = JobRunner(fetch_synthetic, store_at(tmp_path))
    job = await finished(runner, runner.submit(REQUEST))
    assert job.progress.stage == "stacking"
    assert job.progress.done == job.progress.total


async def test_hung_collection_discovery_falls_back_to_the_known_list() -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200)

    http = make_http(transport=httpx.MockTransport(hang))
    discovery = CollectionDiscovery(fallback=("spherex_dr1",))
    async with http.client:
        collections = await collections_for_job(http, discovery, wait_s=0.05)
        await discovery.aclose()
    assert collections == ("spherex_dr1",)


def spectrum_of(n: int) -> Spectrum:
    point = SpectrumPoint(
        lambda_um=1.1, flux_ujy=1.0, err_ujy=0.1, mjd=61000.0, detector=3, visit="v1", saturated=False, flags=0
    )
    return Spectrum(points=[point] * n)


def test_target_key_ignores_fov_detectors_and_mode() -> None:
    a = SequenceRequest(target=MOVER, params=SequenceParams(fov_arcmin=3.0, detectors=(5,)))
    b = SequenceRequest(target=MOVER, params=SequenceParams(mode="exposures"))
    assert target_key(a.target) == target_key(b.target)


async def test_job_measures_the_target_spectrum(tmp_path: Path) -> None:
    runner = JobRunner(fetch_synthetic, store_at(tmp_path))
    job = await finished(runner, runner.submit(REQUEST))
    assert job.result is not None
    assert job.result.meta.spectrum == f"/files/{REQUEST.key}/{SPECTRUM}"
    assert (tmp_path / REQUEST.key / SPECTRUM).is_file()
    spectrum = await runner.spectrum(MOVER)
    assert spectrum is not None
    assert len(spectrum.points) == len(two_visits())


async def test_photometry_bug_keeps_the_sequence_without_a_spectrum(tmp_path: Path) -> None:
    def broken_measure(cutouts: Sequence[Cutout], target: Target) -> Spectrum:
        raise RuntimeError("boom")

    runner = JobRunner(fetch_synthetic, store_at(tmp_path), measure=broken_measure)
    job = await finished(runner, runner.submit(REQUEST))
    assert job.state == "done", job.error
    assert job.result is not None
    assert job.result.meta.spectrum is None
    assert await runner.spectrum(MOVER) is None


async def test_spectrum_expires_with_the_ttl(tmp_path: Path) -> None:
    clock = FakeClock()
    runner = JobRunner(fetch_synthetic, store_at(tmp_path, clock=clock), clock=clock)
    await finished(runner, runner.submit(REQUEST))
    clock.now = (tmp_path / SPECTRA_DIR / f"{target_key(MOVER)}.json").stat().st_mtime + 3601
    assert await runner.spectrum(MOVER) is None


def stored_points(processed_dir: Path, target_id: str) -> int:
    text = (processed_dir / SPECTRA_DIR / f"{target_id}.json").read_text(encoding="utf-8")
    return len(Spectrum.model_validate_json(text).points)


def test_per_target_spectrum_keeps_the_fuller_measurement(tmp_path: Path) -> None:
    store_spectrum(tmp_path, "all-detectors", "t", spectrum_of(6), stale_before=0.0)
    store_spectrum(tmp_path, "one-detector", "t", spectrum_of(2), stale_before=0.0)
    assert stored_points(tmp_path, "t") == 6


def test_expired_fuller_spectrum_is_replaced(tmp_path: Path) -> None:
    store_spectrum(tmp_path, "all-detectors", "t", spectrum_of(6), stale_before=0.0)
    expired_at = (tmp_path / SPECTRA_DIR / "t.json").stat().st_mtime + 1
    store_spectrum(tmp_path, "one-detector", "t", spectrum_of(2), stale_before=expired_at)
    assert stored_points(tmp_path, "t") == 2


def test_bundle_keeps_its_own_spectrum(tmp_path: Path) -> None:
    store_spectrum(tmp_path, "all-detectors", "t", spectrum_of(6), stale_before=0.0)
    store_spectrum(tmp_path, "one-detector", "t", spectrum_of(2), stale_before=0.0)
    own = Spectrum.model_validate_json((tmp_path / "one-detector" / SPECTRUM).read_text(encoding="utf-8"))
    assert len(own.points) == 2


def test_parallel_jobs_of_one_target_keep_the_fuller_spectrum(tmp_path: Path) -> None:
    sizes = range(1, 17)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda n: store_spectrum(tmp_path, f"job-{n}", "t", spectrum_of(n), stale_before=0.0),
                sizes,
            )
        )
    assert stored_points(tmp_path, "t") == max(sizes)


def test_atomic_writes_leave_no_temporary_files(tmp_path: Path) -> None:
    store_spectrum(tmp_path, "job", "t", spectrum_of(2), stale_before=0.0)
    assert list(tmp_path.rglob("*.part")) == []


async def test_new_job_replaces_an_expired_spectrum(tmp_path: Path) -> None:
    per_target = tmp_path / SPECTRA_DIR / f"{target_key(MOVER)}.json"
    per_target.parent.mkdir()
    per_target.write_text(spectrum_of(len(two_visits()) + 10).model_dump_json(), encoding="utf-8")
    expired = time.time() - 7200
    os.utime(per_target, (expired, expired))
    runner = JobRunner(fetch_synthetic, store_at(tmp_path))
    assert await runner.spectrum(MOVER) is None
    await finished(runner, runner.submit(REQUEST))
    spectrum = await runner.spectrum(MOVER)
    assert spectrum is not None
    assert len(spectrum.points) == len(two_visits())


async def test_job_runs_build_and_photometry_in_a_process_pool(tmp_path: Path) -> None:
    with ProcessPoolExecutor(max_workers=1) as pool:
        runner = JobRunner(fetch_synthetic, store_at(tmp_path), executor=pool)
        job = await finished(runner, runner.submit(REQUEST))
    assert job.state == "done", job.error
    assert await runner.spectrum(MOVER) is not None
