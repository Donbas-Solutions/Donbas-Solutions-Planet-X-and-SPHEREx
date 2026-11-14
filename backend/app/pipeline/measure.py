"""Positions measured on grid frames: centroids and the shift between two epochs."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class Shift:
    """Motion between two frames on a north-up, east-left grid."""

    dx_px: float
    dy_px: float
    pixscale_arcsec: float

    @property
    def length_px(self) -> float:
        return math.hypot(self.dx_px, self.dy_px)

    @property
    def length_arcsec(self) -> float:
        return self.length_px * self.pixscale_arcsec

    @property
    def position_angle_deg(self) -> float:
        """East of north; x grows to the west on the grid, so east = −dx."""
        return math.degrees(math.atan2(-self.dx_px, self.dy_px)) % 360


def centroid(data: npt.NDArray[np.float32], x0: float, y0: float, radius_px: float) -> tuple[float, float] | None:
    """Flux-weighted centroid of positive pixels within `radius_px` of (x0, y0); None if nothing is there."""
    rows, cols = np.mgrid[0 : data.shape[0], 0 : data.shape[1]]
    inside = (np.hypot(cols - x0, rows - y0) <= radius_px) & np.isfinite(data) & (data > 0)
    weights = np.where(inside, data, 0.0).astype(np.float64)
    total = float(weights.sum())
    if total <= 0:
        return None
    return float((weights * cols).sum() / total), float((weights * rows).sum() / total)
