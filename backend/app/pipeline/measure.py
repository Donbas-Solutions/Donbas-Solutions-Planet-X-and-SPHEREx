"""Positions measured on grid frames: centroids and the shift between two epochs."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from photutils.centroids import centroid_2dg

from ..astrometry import DAYS_PER_JULIAN_YEAR

MIN_FIT_PIXELS: Final = 12
FALLBACK_RADIUS_PX: Final = 3.0


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


@dataclass(frozen=True)
class ProperMotionFit:
    """Linear fit of positions over time; errors from the fit residuals (None with only two epochs)."""

    pmra_masyr: float
    pmdec_masyr: float
    pmra_err_masyr: float | None
    pmdec_err_masyr: float | None
    n_epochs: int

    def offset_sigma(self, pmra_masyr: float, pmdec_masyr: float) -> float | None:
        """Largest |measured − reference| / σ over the two components; None when σ is unknown or zero."""
        if not self.pmra_err_masyr or not self.pmdec_err_masyr:
            return None
        return max(
            abs(self.pmra_masyr - pmra_masyr) / self.pmra_err_masyr,
            abs(self.pmdec_masyr - pmdec_masyr) / self.pmdec_err_masyr,
        )


def _slope(t: npt.NDArray[np.float64], v: npt.NDArray[np.float64]) -> tuple[float, float | None]:
    dt = t - t.mean()
    sxx = float((dt**2).sum())
    slope = float((dt * (v - v.mean())).sum() / sxx)
    if t.size < 3:
        return slope, None
    residuals = v - (v.mean() + slope * dt)
    return slope, math.sqrt(float((residuals**2).sum()) / (t.size - 2) / sxx)


def fit_proper_motion(
    mjds: list[float], xs_px: list[float], ys_px: list[float], pixscale_arcsec: float
) -> ProperMotionFit:
    """Proper motion from grid positions (north up, x grows west) at `mjds`; pmra includes cos(dec)."""
    if len(mjds) < 2:
        raise ValueError("Need at least two epochs")
    t = np.asarray(mjds, dtype=np.float64)
    to_masyr = pixscale_arcsec * 1000 * DAYS_PER_JULIAN_YEAR
    sx, ex = _slope(t, np.asarray(xs_px, dtype=np.float64))
    sy, ey = _slope(t, np.asarray(ys_px, dtype=np.float64))
    return ProperMotionFit(
        pmra_masyr=-sx * to_masyr,
        pmdec_masyr=sy * to_masyr,
        pmra_err_masyr=None if ex is None else ex * to_masyr,
        pmdec_err_masyr=None if ey is None else ey * to_masyr,
        n_epochs=len(mjds),
    )


def fit_position(
    data: npt.NDArray[np.float32], x0: float, y0: float, half_box_px: int = 5
) -> tuple[float, float] | None:
    """Source position from a 2D Gaussian fit in a box around (x0, y0); NaNs (e.g. a masked saturated core) are
    excluded. Flux-weighted centroids of the undersampled SPHEREx PSF lock onto pixel centres and shortened
    sub-pixel shifts by 10-20 % on ε Indi B; the fit does not."""
    cx, cy = round(x0), round(y0)
    ny, nx = data.shape
    if not (half_box_px <= cx < nx - half_box_px and half_box_px <= cy < ny - half_box_px):
        return None
    box = data[cy - half_box_px : cy + half_box_px + 1, cx - half_box_px : cx + half_box_px + 1].astype(np.float64)
    masked = ~np.isfinite(box)
    if int((~masked).sum()) < MIN_FIT_PIXELS:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gx, gy = centroid_2dg(np.where(masked, 0.0, box), mask=masked)
    except (ValueError, RuntimeError):
        return None
    if not (np.isfinite(gx) and np.isfinite(gy) and 0 <= gx <= 2 * half_box_px and 0 <= gy <= 2 * half_box_px):
        return None
    return float(gx) + cx - half_box_px, float(gy) + cy - half_box_px


def locate_source(data: npt.NDArray[np.float32], x0: float, y0: float) -> tuple[float, float] | None:
    """Best available position: Gaussian fit, else the masked-core centre, else the flux-weighted centroid."""
    return (
        fit_position(data, x0, y0)
        or masked_core_center(data, x0, y0, FALLBACK_RADIUS_PX)
        or centroid(data, x0, y0, FALLBACK_RADIUS_PX)
    )


def masked_core_center(
    data: npt.NDArray[np.float32], x0: float, y0: float, radius_px: float, min_pixels: int = 3
) -> tuple[float, float] | None:
    """Centre of the NaN hole a saturated (masked) core leaves near (x0, y0); None if there is no such hole."""
    rows, cols = np.mgrid[0 : data.shape[0], 0 : data.shape[1]]
    hole = (np.hypot(cols - x0, rows - y0) <= radius_px) & np.isnan(data)
    if int(hole.sum()) < min_pixels:
        return None
    return float(cols[hole].mean()), float(rows[hole].mean())


def centroid(data: npt.NDArray[np.float32], x0: float, y0: float, radius_px: float) -> tuple[float, float] | None:
    """Flux-weighted centroid of positive pixels within `radius_px` of (x0, y0); None if nothing is there."""
    rows, cols = np.mgrid[0 : data.shape[0], 0 : data.shape[1]]
    inside = (np.hypot(cols - x0, rows - y0) <= radius_px) & np.isfinite(data) & (data > 0)
    weights = np.where(inside, data, 0.0).astype(np.float64)
    total = float(weights.sum())
    if total <= 0:
        return None
    return float((weights * cols).sum() / total), float((weights * rows).sum() / total)
