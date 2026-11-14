"""Grouping exposures into visits and capping them (SR-2)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

import numpy as np

from ..domain import ExposureMeta, Visit

VISIT_GAP_DAYS: Final = 40.0
MAX_VISIT_DAYS: Final = 60.0
BIN_DAYS: Final = 30.0


def _clusters(ordered: list[ExposureMeta], gap_days: float) -> list[list[ExposureMeta]]:
    clusters: list[list[ExposureMeta]] = []
    for exposure in ordered:
        if clusters and exposure.mjd_mid - clusters[-1][-1].mjd_mid <= gap_days:
            clusters[-1].append(exposure)
        else:
            clusters.append([exposure])
    return clusters


def _bins(cluster: list[ExposureMeta], bin_days: float) -> list[list[ExposureMeta]]:
    start = cluster[0].mjd_mid
    bins: dict[int, list[ExposureMeta]] = {}
    for exposure in cluster:
        bins.setdefault(int((exposure.mjd_mid - start) // bin_days), []).append(exposure)
    return [bins[k] for k in sorted(bins)]


def group_visits(
    exposures: Iterable[ExposureMeta],
    gap_days: float = VISIT_GAP_DAYS,
    max_visit_days: float = MAX_VISIT_DAYS,
    bin_days: float = BIN_DAYS,
) -> list[Visit]:
    """Time clusters split by gaps > `gap_days`; deep-field clusters longer than `max_visit_days` → fixed bins."""
    ordered = sorted(exposures, key=lambda e: e.mjd_mid)
    groups: list[tuple[list[ExposureMeta], bool]] = []
    for cluster in _clusters(ordered, gap_days):
        if cluster[-1].mjd_mid - cluster[0].mjd_mid <= max_visit_days:
            groups.append((cluster, False))
        else:
            groups.extend((b, True) for b in _bins(cluster, bin_days))
    return [
        Visit(
            id=f"v{i}",
            mjd_start=min(e.mjd_start for e in group),
            mjd_end=max(e.mjd_end for e in group),
            binned=binned,
            exposures=tuple(group),
        )
        for i, (group, binned) in enumerate(groups, start=1)
    ]


def cap_per_detector(visit: Visit, max_per_detector: int) -> list[ExposureMeta]:
    """At most `max_per_detector` exposures per detector, evenly spaced in time.

    A cap below ~17 per detector leaves part of the LVF band uncovered (SR-1): fine for development samples,
    not for published sequences.
    """
    kept: list[ExposureMeta] = []
    for detector in sorted({e.detector for e in visit.exposures}):
        same = [e for e in visit.exposures if e.detector == detector]
        if len(same) > max_per_detector:
            picks = np.unique(np.linspace(0, len(same) - 1, max_per_detector).round().astype(int))
            same = [same[int(i)] for i in picks]
        kept.extend(same)
    return kept
