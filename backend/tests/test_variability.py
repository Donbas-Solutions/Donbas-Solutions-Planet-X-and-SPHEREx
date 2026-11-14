"""Matched-λ brightness changes between visits (FR-17, T-4) on synthetic spectra with known truth."""

from __future__ import annotations

import math

import pytest

from app.models import SpectrumPoint
from app.pipeline.variability import channel_width, matched_changes, strongest_per_detector

D1_LO_UM = 0.75


def point(lambda_um: float, flux: float, visit: str, mjd: float, *, saturated: bool = False) -> SpectrumPoint:
    return SpectrumPoint(
        lambda_um=lambda_um,
        flux_ujy=None if saturated else flux,
        err_ujy=None if saturated else flux / 200,
        mjd=mjd,
        detector=1,
        visit=visit,
        saturated=saturated,
        flags=0,
    )


def steep(lambda_um: float) -> float:
    """A red continuum, F ∝ λ^4: neighbouring channels differ by ~10 %."""
    return 1000 * (lambda_um / D1_LO_UM) ** 4


def visit(name: str, mjd: float, lambdas: list[float], scale: float = 1.0) -> list[SpectrumPoint]:
    return [point(lam, scale * steep(lam), name, mjd + i) for i, lam in enumerate(lambdas)]


def offset_by(lambda_um: float, channels: float) -> float:
    return lambda_um * math.exp(channels * channel_width(1))


def test_a_constant_steep_spectrum_is_not_called_variable() -> None:
    first = [0.76, 0.85, 0.95, 1.05]
    second = [offset_by(lam, 0.5) for lam in first]
    best = strongest_per_detector(matched_changes(visit("v1", 61000, first) + visit("v2", 61180, second)))[1]
    assert best.n_pairs == 4
    assert best.significance < 3


def test_a_doubling_at_matched_lambda_is_significant() -> None:
    first = [0.76, 0.85, 0.95]
    second = [offset_by(lam, 0.3) for lam in first]
    best = strongest_per_detector(matched_changes(visit("v1", 61000, first) + visit("v2", 61180, second, 2.0)))[1]
    assert (best.earlier, best.later) == ("v1", "v2")
    assert best.ratio == pytest.approx(2.0, rel=0.1)
    assert best.significance > 5


def test_exposures_more_than_one_channel_apart_are_not_paired() -> None:
    first = [0.76, 0.95]
    second = [offset_by(lam, 1.5) for lam in first]
    assert matched_changes(visit("v1", 61000, first) + visit("v2", 61180, second)) == []


def test_saturated_points_take_no_part() -> None:
    points = [point(0.8, 0, "v1", 61000, saturated=True), point(0.8, 500, "v2", 61180)]
    assert matched_changes(points) == []


def test_visits_are_ordered_by_time_not_by_name() -> None:
    points = visit("v10", 61000, [0.8]) + visit("v2", 61180, [0.8], 3.0)
    change = matched_changes(points)[0]
    assert (change.earlier, change.later) == ("v10", "v2")
    assert change.ratio == pytest.approx(3.0)
