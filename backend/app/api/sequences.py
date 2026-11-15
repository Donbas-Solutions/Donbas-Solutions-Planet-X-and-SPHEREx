from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response

from ..domain import DETECTORS, SequenceParams
from ..jobs import SequenceRequest
from ..models import JobAccepted, JobStatus, Sequence
from .deps import Runner
from .params import Dec, Fov, JobId, Pm, Ra, RefEpoch, target_of

router = APIRouter(prefix="/api")


def _detectors(det: str) -> tuple[int, ...]:
    return DETECTORS if det == "all" else tuple(sorted({int(d) for d in det.split(",")}))


@router.get("/sequence", response_model=Sequence | JobAccepted)
async def sequence(
    runner: Runner,
    response: Response,
    ra: Ra,
    dec: Dec,
    fov: Fov = 10.0,
    det: Annotated[str, Query(pattern=r"^(all|[1-6](,[1-6])*)$")] = "all",
    mode: Annotated[Literal["visit_stack", "exposures"], Query()] = "visit_stack",
    pmra: Pm = None,
    pmdec: Pm = None,
    ref_epoch: RefEpoch = 2000.0,
) -> Sequence | JobAccepted:
    """200 with the cached sequence, or 202 with a job to poll at `/api/jobs/{job_id}`."""
    request = SequenceRequest(
        target=target_of(ra, dec, pmra, pmdec, ref_epoch),
        params=SequenceParams(fov_arcmin=fov, detectors=_detectors(det), mode=mode),
    )
    cached = await runner.cached(request)
    if cached is not None:
        return cached
    job = runner.submit(request)
    response.status_code = 202
    return JobAccepted(job_id=job.id)


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def job(runner: Runner, job_id: JobId) -> JobStatus:
    found = runner.get(job_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return found.status()
