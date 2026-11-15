"""Proper-motion propagation (SR-3): ICRS throughout, parallax ignored (≤ 0.55″ for the test targets)."""

from __future__ import annotations

import math
import warnings

import numpy as np
import numpy.typing as npt
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from .domain import Target

DAYS_PER_JULIAN_YEAR = 365.25

FloatArray = npt.NDArray[np.float64]


def positions_at(
    ra_deg: FloatArray,
    dec_deg: FloatArray,
    pmra_masyr: FloatArray,
    pmdec_masyr: FloatArray,
    ref_epoch: float,
    mjd: float,
) -> tuple[FloatArray, FloatArray]:
    """(ra_deg, dec_deg) at `mjd` of positions given at Julian year `ref_epoch`; `pmra_masyr` includes cos(dec)."""
    coord = SkyCoord(
        ra=ra_deg * u.deg,
        dec=dec_deg * u.deg,
        pm_ra_cosdec=pmra_masyr * u.mas / u.yr,
        pm_dec=pmdec_masyr * u.mas / u.yr,
        obstime=Time(ref_epoch, format="jyear"),
        frame="icrs",
    )
    with warnings.catch_warnings():
        # No distance on purpose (parallax ignored, SR-3); ERFA then substitutes a large one and warns.
        warnings.filterwarnings("ignore", message=".*distance overridden.*")
        moved = coord.apply_space_motion(new_obstime=Time(mjd, format="mjd"))
    return np.asarray(moved.ra.deg, dtype=np.float64), np.asarray(moved.dec.deg, dtype=np.float64)


def position_at(target: Target, mjd: float) -> tuple[float, float]:
    """(ra_deg, dec_deg) of the target at `mjd`; unchanged when the proper motion is unknown."""
    if target.pmra_masyr is None or target.pmdec_masyr is None:
        return target.ra_deg, target.dec_deg
    ra_deg, dec_deg = positions_at(
        np.array([target.ra_deg]),
        np.array([target.dec_deg]),
        np.array([target.pmra_masyr]),
        np.array([target.pmdec_masyr]),
        target.ref_epoch,
        mjd,
    )
    return float(ra_deg[0]), float(dec_deg[0])


def total_proper_motion_arcsec_per_yr(target: Target) -> float:
    if target.pmra_masyr is None or target.pmdec_masyr is None:
        return 0.0
    return math.hypot(target.pmra_masyr, target.pmdec_masyr) / 1000.0
