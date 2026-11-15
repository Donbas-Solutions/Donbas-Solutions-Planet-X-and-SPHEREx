from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..jobs import JobRunner
from ..models import Spectrum
from .deps import Runner
from .params import Dec, Pm, Ra, RefEpoch, target_of

router = APIRouter(prefix="/api")


async def _target_spectrum(
    runner: JobRunner, ra: float, dec: float, pmra: float | None, pmdec: float | None, ref_epoch: float
) -> Spectrum:
    found = await runner.spectrum(target_of(ra, dec, pmra, pmdec, ref_epoch))
    if found is None:
        raise HTTPException(
            status_code=404, detail="No live spectrum for this target yet: it is measured when its sequence is built."
        )
    return found


@router.get("/spectrum", response_model=Spectrum)
async def spectrum(
    runner: Runner, ra: Ra, dec: Dec, pmra: Pm = None, pmdec: Pm = None, ref_epoch: RefEpoch = 2000.0
) -> Spectrum:
    """Forced photometry of the target on every exposure of its latest sequence (FR-16)."""
    return await _target_spectrum(runner, ra, dec, pmra, pmdec, ref_epoch)


@router.get("/lightcurve", response_model=Spectrum)
async def lightcurve(
    runner: Runner, ra: Ra, dec: Dec, pmra: Pm = None, pmdec: Pm = None, ref_epoch: RefEpoch = 2000.0
) -> Spectrum:
    """The same points as `/api/spectrum`; the client groups them by detector or λ bin (FR-17, docs/api.md)."""
    return await _target_spectrum(runner, ra, dec, pmra, pmdec, ref_epoch)
