"""Brightness changes between visits at matched wavelength (FR-17, T-4).

Within a visit every exposure samples its own LVF wavelength, so visit means mix the spectrum with variability.
Here each exposure of one visit is paired with the nearest-λ exposure of another visit, at most one LVF channel
away, and only the flux ratios of those pairs are compared.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Final

from ..models import SpectrumPoint
from .sequence import DETECTOR_BANDS_UM, LVF_CHANNELS

# Per exposure, added in quadrature: repeatability and aperture systematics that the formal errors leave out.
CALIBRATION_FLOOR: Final = 0.05
# |d ln F / d ln λ| assumed for a point with no neighbour in its own visit; a steep stellar continuum.
DEFAULT_LOG_SLOPE: Final = 4.0


@dataclass(frozen=True)
class MatchedChange:
    detector: int
    earlier: str
    later: str
    ratio: float
    """Later / earlier flux at matched λ (inverse-variance mean of the pairs' log ratios)."""
    significance: float
    """|ln ratio| over its error, in σ."""
    n_pairs: int
    lambda_um: tuple[float, float]


@dataclass(frozen=True)
class _Sample:
    log_lambda: float
    flux: float
    err: float


def channel_width(detector: int) -> float:
    """One LVF channel in ln λ (channels are equal steps in log λ)."""
    lo, hi = DETECTOR_BANDS_UM[detector]
    return math.log(hi / lo) / LVF_CHANNELS


def _sample(p: SpectrumPoint) -> _Sample | None:
    """Ratios need a positive measured flux: saturated, masked and ≤ 0 points take no part."""
    if p.saturated or p.flux_ujy is None or p.err_ujy is None or p.err_ujy <= 0 or p.flux_ujy <= 0:
        return None
    return _Sample(math.log(p.lambda_um), p.flux_ujy, p.err_ujy)


def _local_slope(samples: Sequence[_Sample], i: int) -> float | None:
    """Steepest |d ln F / d ln λ| towards the λ-neighbours in the same visit: the spectrum near this point."""
    slopes = [
        abs(math.log(samples[j].flux / samples[i].flux) / (samples[j].log_lambda - samples[i].log_lambda))
        for j in (i - 1, i + 1)
        if 0 <= j < len(samples) and samples[j].log_lambda != samples[i].log_lambda
    ]
    return max(slopes) if slopes else None


def _compare(detector: int, earlier: list[_Sample], later: list[_Sample]) -> tuple[float, float, int, float, float]:
    width = channel_width(detector)
    terms: list[tuple[float, float, float]] = []
    for i, a in enumerate(earlier):
        j = min(range(len(later)), key=lambda k: abs(later[k].log_lambda - a.log_lambda))
        b = later[j]
        offset = abs(b.log_lambda - a.log_lambda)
        if offset > width:
            continue
        slopes = [s for s in (_local_slope(earlier, i), _local_slope(later, j)) if s is not None]
        slope = max(slopes) if slopes else DEFAULT_LOG_SLOPE
        variance = (a.err / a.flux) ** 2 + (b.err / b.flux) ** 2 + 2 * CALIBRATION_FLOOR**2 + (slope * offset) ** 2
        terms.append((math.log(b.flux / a.flux), 1 / variance, a.log_lambda))
    if not terms:
        return 0.0, 0.0, 0, 0.0, 0.0
    weight = sum(w for _, w, _ in terms)
    mean = sum(r * w for r, w, _ in terms) / weight
    lambdas = [math.exp(x) for _, _, x in terms]
    return mean, abs(mean) * math.sqrt(weight), len(terms), min(lambdas), max(lambdas)


def matched_changes(points: Sequence[SpectrumPoint]) -> list[MatchedChange]:
    """Every pair of visits per detector that shares at least one matched-λ pair of measured exposures."""
    by_detector: dict[int, dict[str, list[_Sample]]] = defaultdict(lambda: defaultdict(list))
    first_mjd: dict[str, float] = {}
    for p in points:
        first_mjd[p.visit] = min(first_mjd.get(p.visit, p.mjd), p.mjd)
        if (sample := _sample(p)) is not None:
            by_detector[p.detector][p.visit].append(sample)
    changes: list[MatchedChange] = []
    for detector, visits in sorted(by_detector.items()):
        ordered = sorted(visits, key=lambda v: first_mjd[v])
        for earlier, later in combinations(ordered, 2):
            a = sorted(visits[earlier], key=lambda s: s.log_lambda)
            b = sorted(visits[later], key=lambda s: s.log_lambda)
            log_ratio, significance, n_pairs, lo, hi = _compare(detector, a, b)
            if n_pairs:
                changes.append(
                    MatchedChange(detector, earlier, later, math.exp(log_ratio), significance, n_pairs, (lo, hi))
                )
    return changes


def strongest_per_detector(changes: Sequence[MatchedChange]) -> dict[int, MatchedChange]:
    """The most significant visit pair of each detector (the largest of several looks: judge it against 5σ)."""
    best: dict[int, MatchedChange] = {}
    for change in changes:
        if change.detector not in best or change.significance > best[change.detector].significance:
            best[change.detector] = change
    return best
