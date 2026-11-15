"""Background jobs behind `/api/sequence` (FR-13): one job per request key, bundles kept by `storage.BundleStore`.

Each job also measures the target's spectrum (FR-16, FR-17) on the same cutouts.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import Executor
from dataclasses import dataclass, field
from functools import partial
from typing import Final

import anyio

from ..archive.fetch import FetchResult
from ..archive.http import ArchiveError
from ..archive.plan import NoCoverageError
from ..config import settings
from ..domain import Cutout, ProgressCallback, SequenceParams, SequenceResult, Target
from ..models import JobProgress, JobState, JobStatus, Spectrum
from ..models import Sequence as SequenceModel
from ..pipeline.photometry import measure_spectrum
from ..pipeline.sequence import SequenceError, build_sequence
from ..storage import SPECTRUM, BundleStore
from .keys import SequenceRequest, target_key

logger = logging.getLogger(__name__)

JOB_RETENTION_S: Final = 3600.0
ARCHIVE_DOWN: Final = (
    "The IRSA archive is unreachable or overloaded right now. Try again in a few minutes or open a preset target."
)

FetchFn = Callable[[SequenceRequest, ProgressCallback], Awaitable[FetchResult]]
BuildFn = Callable[[Sequence[Cutout], Target, SequenceParams], SequenceResult]
MeasureFn = Callable[[Sequence[Cutout], Target], Spectrum]


class JobError(Exception):
    """A job failed for a reason the user should read as is."""


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
        store: BundleStore,
        executor: Executor | None = None,
        build: BuildFn = build_sequence,
        measure: MeasureFn = measure_spectrum,
        max_running: int = settings.max_running_jobs,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._fetch = fetch
        self._store = store
        self._executor = executor
        self._build = build
        self._measure = measure
        self._running = asyncio.Semaphore(max_running)
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._job_by_key: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def cached(self, request: SequenceRequest) -> SequenceModel | None:
        """The finished bundle of this request, unless it is older than the TTL (new data releases arrive weekly)."""
        return await self._store.load(request.key, fresh_only=True)

    async def spectrum(self, target: Target) -> Spectrum | None:
        """The target's spectrum from its latest sequence job, unless older than the TTL."""
        return await self._store.spectrum(target_key(target))

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
        except (JobError, NoCoverageError) as exc:
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
            store = partial(self._store.store_spectrum, job.key, target_key(request.target), spectrum)
            await anyio.to_thread.run_sync(store)
            result = with_spectrum_link(result)
        await anyio.to_thread.run_sync(self._store.write_bundle, result, job.key)
        job.report("stacking", len(fetched.cutouts), len(fetched.cutouts))
        sequence = await self._store.load(job.key, fresh_only=False)
        if sequence is None:
            raise JobError("The finished sequence could not be read back.")
        return sequence

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
