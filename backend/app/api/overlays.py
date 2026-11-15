from __future__ import annotations

import anyio
from fastapi import APIRouter

from ..archive.gaia import GaiaError, stars_at
from ..models import Overlays
from .deps import Gaia, SharedHttp
from .params import Dec, Fov, Mjd, Ra

router = APIRouter(prefix="/api")


@router.get("/overlays", response_model=Overlays)
async def overlays(http: SharedHttp, gaia: Gaia, ra: Ra, dec: Dec, fov: Fov, mjd: Mjd) -> Overlays:
    """Gaia DR3 stars of the field at their positions on `mjd` (FR-18)."""
    try:
        sources = await gaia.sources(http, ra, dec, fov)
    except GaiaError:
        return Overlays(gaia=[], unavailable=["gaia"])
    stars = await anyio.to_thread.run_sync(stars_at, sources, ra, dec, fov, mjd)
    return Overlays(gaia=stars, unavailable=[])
