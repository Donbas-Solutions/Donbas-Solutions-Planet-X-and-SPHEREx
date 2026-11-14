"""Proper-motion propagation (SR-3)."""

from __future__ import annotations

import math

import pytest

from app.astrometry import position_at
from app.domain import Target

J2000_MJD = 51544.5
BARNARD = Target(ra_deg=269.452077, dec_deg=4.693365, pmra_masyr=-801.551, pmdec_masyr=10362.394)


def test_barnard_moves_about_ten_arcsec_north_per_year() -> None:
    ra_deg, dec_deg = position_at(BARNARD, J2000_MJD + 365.25)
    north_arcsec = (dec_deg - BARNARD.dec_deg) * 3600
    east_arcsec = (ra_deg - BARNARD.ra_deg) * 3600 * math.cos(math.radians(BARNARD.dec_deg))
    assert north_arcsec == pytest.approx(10.362, abs=0.02)
    assert east_arcsec == pytest.approx(-0.802, abs=0.02)


def test_unknown_proper_motion_means_no_motion() -> None:
    static = Target(ra_deg=10.0, dec_deg=-5.0)
    assert position_at(static, 61000.0) == (10.0, -5.0)
