"""Query and path parameters shared by several endpoints; the limits come from docs/api.md."""

from __future__ import annotations

from typing import Annotated

from fastapi import Path, Query

from ..domain import Target

Ra = Annotated[float, Query(ge=0, lt=360, description="ICRS degrees")]
Dec = Annotated[float, Query(ge=-90, le=90, description="ICRS degrees")]
Pm = Annotated[float | None, Query(description="mas/yr; pmra includes cos(dec)")]
RefEpoch = Annotated[float, Query(description="Julian year of ra/dec")]
Fov = Annotated[float, Query(ge=2, le=30, description="arcmin")]
Mjd = Annotated[float, Query(ge=40000, le=90000, description="MJD (UTC) of the frame")]
JobId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def target_of(ra: float, dec: float, pmra: float | None, pmdec: float | None, ref_epoch: float) -> Target:
    return Target(ra_deg=ra, dec_deg=dec, ref_epoch=ref_epoch, pmra_masyr=pmra, pmdec_masyr=pmdec)
