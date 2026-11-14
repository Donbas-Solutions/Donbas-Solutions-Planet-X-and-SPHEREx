"""Proper-motion propagation (SR-3): ICRS throughout, parallax ignored (≤ 0.55″ for the test targets)."""

from __future__ import annotations

import math
import warnings

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from .domain import Target

DAYS_PER_JULIAN_YEAR = 365.25


def position_at(target: Target, mjd: float) -> tuple[float, float]:
    """(ra_deg, dec_deg) of the target at `mjd`; unchanged when the proper motion is unknown."""
    if target.pmra_masyr is None or target.pmdec_masyr is None:
        return target.ra_deg, target.dec_deg
    coord = SkyCoord(
        ra=target.ra_deg * u.deg,
        dec=target.dec_deg * u.deg,
        pm_ra_cosdec=target.pmra_masyr * u.mas / u.yr,
        pm_dec=target.pmdec_masyr * u.mas / u.yr,
        obstime=Time(target.ref_epoch, format="jyear"),
        frame="icrs",
    )
    with warnings.catch_warnings():
        # No distance on purpose (parallax ignored, SR-3); ERFA then substitutes a large one and warns.
        warnings.filterwarnings("ignore", message=".*distance overridden.*")
        moved = coord.apply_space_motion(new_obstime=Time(mjd, format="mjd"))
    return float(moved.ra.deg), float(moved.dec.deg)


def total_proper_motion_arcsec_per_yr(target: Target) -> float:
    if target.pmra_masyr is None or target.pmdec_masyr is None:
        return 0.0
    return math.hypot(target.pmra_masyr, target.pmdec_masyr) / 1000.0
