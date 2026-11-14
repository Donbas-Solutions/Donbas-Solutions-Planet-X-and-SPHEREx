"""Inverse-variance weighted stacks of grid exposures (SR-1)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .exposure import GridExposure


@dataclass(frozen=True, eq=False)
class Stack:
    data: npt.NDArray[np.float32]
    flags: npt.NDArray[np.uint32]
    exposures: tuple[GridExposure, ...]

    @property
    def lambdas_um(self) -> list[float]:
        return sorted(e.lambda_um for e in self.exposures if np.isfinite(e.lambda_um))


def stack(exposures: Sequence[GridExposure]) -> Stack:
    """Weighted mean where at least one exposure is valid (NaN elsewhere); FLAGS OR-combined over contributors."""
    if not exposures:
        raise ValueError("Cannot stack zero exposures")
    data = np.stack([e.data.astype(np.float64) for e in exposures])
    variance = np.stack([e.variance.astype(np.float64) for e in exposures])
    usable = np.isfinite(data) & np.isfinite(variance) & (variance > 0)
    weights = np.where(usable, 1.0 / np.where(usable, variance, 1.0), 0.0)
    total = weights.sum(axis=0)
    weighted = (np.where(usable, data, 0.0) * weights).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(total > 0, weighted / total, np.nan)

    flags = np.zeros(data.shape[1:], dtype=np.uint32)
    for exposure in exposures:
        flags |= exposure.flags
    return Stack(data=mean.astype(np.float32), flags=flags, exposures=tuple(exposures))
