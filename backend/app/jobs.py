"""Background jobs behind `/api/sequence` (FR-13): one job per request key, bundles cached in `processed/<key>/`.

Each job also measures the target's spectrum (FR-16, FR-17) on the same cutouts: `spectrum.json` in the bundle,
and a copy per target in `processed/spectra/`, which `/api/spectrum` and `/api/lightcurve` serve.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import Executor
from dataclasses import dataclass, field
from pathlib import Path
from statistics import fmean
from typing import Final

import anyio

from .archive.collections import CollectionDiscovery
from .archive.cutouts import cutout_size_deg
from .archive.fetch import FetchResult, fetch_cutouts, query_exposures
from .archive.http import ArchiveError, Http
from .archive.visits import cap_per_detector, group_visits
from .astrometry import position_at
from .config import settings
from .domain import Cutout, ExposureMeta, ProgressCallback, SequenceParams, SequenceResult, Target, Visit
from .models import JobProgress, JobState, JobStatus, Spectrum
from .models import Sequence as SequenceModel
from .pipeline.bundle import MANIFEST, write_bundle
from .pipeline.photometry import measure_spectrum
from .pipeline.sequence import SequenceError, build_sequence

logger = logging.getLogger(__name__)

JOB_RETENTION_S: Final = 3600.0
DISCOVERY_WAIT_S: Final = 30.0
FILES_PREFIX: Final = "/files"
SPECTRUM: Final = "spectrum.json"
SPECTRA_DIR: Final = "spectra"
ARCHIVE_DOWN: Final = (
    "The IRSA archive is unreachable or overloaded right now. Try again in a few minutes or open a preset target."
)

FetchFn = Callable[["SequenceRequest", ProgressCallback], Awaitable[FetchResult]]
BuildFn = Callable[[Sequence[Cutout], Target, SequenceParams], SequenceResult]
MeasureFn = Callable[[Sequence[Cutout], Target], Spectrum]


class JobError(Exception):
    """A job failed for a reason the user should read as is."""


def target_key(target: Target) -> str:
    """Same position, motion and epoch → same key; the spectrum does not depend on FOV, detectors or mode."""
    return _digest(_target_parts(target))


def _target_parts(target: Target) -> tuple[str, ...]:
    return (
        f"{target.ra_deg:.5f}",
        f"{target.dec_deg:.5f}",
        f"{target.ref_epoch:.3f}",
        _pm(target.pmra_masyr),
        _pm(target.pmdec_masyr),
    )


def _digest(parts: Sequence[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class SequenceRequest:
    target: Target
    params: SequenceParams

    @property
    def key(self) -> str:
        """Same sequence → same key. Rounding to 1e-5° (0.04″) is far below the 6.2″ pixel."""
        p = self.params
        return _digest(
            (
                *_target_parts(self.target),
                f"{p.fov_arcmin:.1f}",
                ",".join(str(d) for d in sorted(set(p.detectors))),
                p.mode,
                str(p.include_allwise),
            )
        )


def _pm(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


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
    try:
        async with asyncio.timeout(wait_s):
            return await discovery.collections(http)
    except TimeoutError:
        logger.warning("Collection discovery took over %.0f s; using %s", wait_s, discovery.current)
        return discovery.current


async def fetch_for_request(
    http: Http, discovery: CollectionDiscovery, request: SequenceRequest, progress: ProgressCallback
) -> FetchResult:
    collections = await collections_for_job(http, discovery)
    exposures = await query_exposures(http, request.target, collections)
    plan = plan_exposures(exposures, request.params.detectors, settings.live_cap_per_detector)
    if not plan:
        raise JobError("No SPHEREx coverage at this position for the selected detectors.")
    first = min(meta.mjd_mid for _, meta in plan)
    last = max(meta.mjd_mid for _, meta in plan)
    center = await anyio.to_thread.run_sync(position_at, request.target, fmean((first, last)))
    size_deg = cutout_size_deg(request.params.fov_arcmin, request.target, last - first)
    progress("downloading", 0, len(plan))
    return await fetch_cutouts(
        http, plan, center, size_deg, progress=lambda _stage, done, total: progress("downloading", done, total)
    )


def build_and_measure(
    build: BuildFn, measure: MeasureFn, cutouts: Sequence[Cutout], target: Target, params: SequenceParams
) -> tuple[SequenceResult, Spectrum | None]:
    """One process-pool call for both, so the cutouts are pickled once."""
    result = build(cutouts, target, params)
    try:
        spectrum = measure(cutouts, target)
    except Exception:
        logger.exception("Photometry failed; the sequence is kept without a spectrum")
        spectrum = None
    return result, spectrum


def with_spectrum_link(result: SequenceResult) -> SequenceResult:
    meta = result.sequence.meta.model_copy(update={"spectrum": SPECTRUM})
    return SequenceResult(sequence=result.sequence.model_copy(update={"meta": meta}), arrays=result.arrays)


def with_file_urls(sequence: SequenceModel, key: str) -> SequenceModel:
    """Bundle URLs are relative to the manifest; the API serves them under `/files/<key>/` (docs/api.md)."""
    prefix = f"{FILES_PREFIX}/{key}"
    frames = [
        frame.model_copy(update={"data": f"{prefix}/{frame.data}", "flags": f"{prefix}/{frame.flags}"})
        for frame in sequence.frames
    ]
    meta = sequence.meta
    if meta.spectrum is not None:
        meta = meta.model_copy(update={"spectrum": f"{prefix}/{meta.spectrum}"})
    return sequence.model_copy(update={"frames": frames, "meta": meta})


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def store_spectrum(processed_dir: Path, bundle_key: str, target_id: str, spectrum: Spectrum) -> None:
    """The bundle's copy always; the per-target copy unless an earlier job measured more exposures (all detectors,
    where this job had a selection)."""
    text = spectrum.model_dump_json(indent=1) + "\n"
    _write_atomic(processed_dir / bundle_key / SPECTRUM, text)
    per_target = processed_dir / SPECTRA_DIR / f"{target_id}.json"
    try:
        existing: Spectrum | None = Spectrum.model_validate_json(per_target.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        existing = None
    if existing is None or len(spectrum.points) >= len(existing.points):
        _write_atomic(per_target, text)


@dataclass
class Job:
    id: str
    key: str
    state: JobState = "queued"
    progress: JobProgress = field(default_factory=lambda: JobProgress(stage="queued", done=0, total=0))
    result: SequenceModel | None = None
    error: str | None = None
    finished_at: float | None = None

    def report(self, stage: str, done: int, total: int) -> None:
        self.progress = JobProgress(stage=stage, done=done, total=total)

    def status(self) -> JobStatus:
        return JobStatus(status=self.state, progress=self.progress, result=self.result, error=self.error)


class JobRunner:
    """Owns the job registry. Lives on the event loop only: every method must be called from it."""

    def __init__(
        self,
        fetch: FetchFn,
        processed_dir: Path,
        executor: Executor | None = None,
        build: BuildFn = build_sequence,
        measure: MeasureFn = measure_spectrum,
        max_running: int = settings.max_running_jobs,
        ttl_s: float = settings.processed_ttl_h * 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._fetch = fetch
        self._processed_dir = processed_dir
        self._executor = executor
        self._build = build
        self._measure = measure
        self._running = asyncio.Semaphore(max_running)
        self._ttl_s = ttl_s
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._job_by_key: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def cached(self, request: SequenceRequest) -> SequenceModel | None:
        """The finished bundle of this request, unless it is older than the TTL (new data releases arrive weekly)."""
        return await self._load(request.key, fresh_only=True)

    async def spectrum(self, target: Target) -> Spectrum | None:
        """The target's spectrum from its latest sequence job, unless older than the TTL."""
        path = anyio.Path(self._processed_dir / SPECTRA_DIR / f"{target_key(target)}.json")
        try:
            stat = await path.stat()
            if self._clock() - stat.st_mtime > self._ttl_s:
                return None
            text = await path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return Spectrum.model_validate_json(text)

    def submit(self, request: SequenceRequest) -> Job:
        """The queued, running or finished job of this request; a failed one is retried as a new job."""
        self._prune()
        key = request.key
        existing = self._jobs.get(self._job_by_key.get(key, ""))
        if existing is not None and existing.state != "error":
            return existing
        job = Job(id=uuid.uuid4().hex, key=key)
        self._jobs[job.id] = job
        self._job_by_key[key] = job.id
        task = asyncio.create_task(self._run(job, request), name=f"job-{job.id}")
        self._tasks[job.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job.id, None))
        return job

    async def wait(self, job: Job) -> None:
        task = self._tasks.get(job.id)
        if task is not None:
            await task

    async def aclose(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, job: Job, request: SequenceRequest) -> None:
        try:
            async with self._running:
                job.state = "running"
                job.report("searching", 0, 0)
                job.result = await self._build_bundle(job, request)
            job.state = "done"
        except JobError as exc:
            self._fail(job, str(exc))
        except ArchiveError as exc:
            logger.warning("Job %s: archive failed: %s", job.id, exc)
            self._fail(job, ARCHIVE_DOWN)
        except SequenceError as exc:
            self._fail(job, str(exc))
        except Exception:
            logger.exception("Job %s failed", job.id)
            self._fail(job, "Internal error while building the sequence.")
        finally:
            job.finished_at = self._clock()

    async def _build_bundle(self, job: Job, request: SequenceRequest) -> SequenceModel:
        fetched = await self._fetch(request, job.report)
        if fetched.failed:
            logger.warning("Job %s: %d exposures failed on every source", job.id, len(fetched.failed))
        if not fetched.cutouts:
            if fetched.failed:
                raise JobError(ARCHIVE_DOWN)
            raise JobError("No SPHEREx exposure covers this position on the detector.")
        job.report("stacking", 0, len(fetched.cutouts))
        loop = asyncio.get_running_loop()
        result, spectrum = await loop.run_in_executor(
            self._executor,
            build_and_measure,
            self._build,
            self._measure,
            fetched.cutouts,
            request.target,
            request.params,
        )
        if spectrum is not None:
            await anyio.to_thread.run_sync(
                store_spectrum, self._processed_dir, job.key, target_key(request.target), spectrum
            )
            result = with_spectrum_link(result)
        await anyio.to_thread.run_sync(write_bundle, result, self._processed_dir / job.key)
        job.report("stacking", len(fetched.cutouts), len(fetched.cutouts))
        sequence = await self._load(job.key, fresh_only=False)
        if sequence is None:
            raise JobError("The finished sequence could not be read back.")
        return sequence

    async def _load(self, key: str, *, fresh_only: bool) -> SequenceModel | None:
        manifest = anyio.Path(self._processed_dir / key / MANIFEST)
        try:
            stat = await manifest.stat()
            if fresh_only and self._clock() - stat.st_mtime > self._ttl_s:
                return None
            text = await manifest.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return with_file_urls(SequenceModel.model_validate_json(text), key)

    def _fail(self, job: Job, message: str) -> None:
        job.state = "error"
        job.error = message

    def _prune(self) -> None:
        now = self._clock()
        stale = [
            job
            for job in self._jobs.values()
            if job.finished_at is not None and now - job.finished_at > JOB_RETENTION_S
        ]
        for job in stale:
            del self._jobs[job.id]
            if self._job_by_key.get(job.key) == job.id:
                del self._job_by_key[job.key]
