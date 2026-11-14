"""One exposure → background-subtracted, masked arrays on the common grid (SR-4, SR-5, SR-6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from astropy.stats import SigmaClip, sigma_clipped_stats
from astropy.wcs import WCS
from photutils.background import Background2D, MedianBackground
from reproject import reproject_interp

from ..astrometry import position_at
from ..domain import Cutout, Target

logger = logging.getLogger(__name__)

# Fraction of valid input that a grid pixel needs; below it the pixel is NaN (masked or off the cutout).
MIN_COVERAGE: Final = 0.99
MIN_BACKGROUND_PIXELS: Final = 50
BACKGROUND_BOX_PX: Final = 24


@dataclass(frozen=True, eq=False)
class GridExposure:
    """A cutout resampled onto the sequence grid. `lambda_um` is the LVF wavelength at the target (NaN if the
    target falls outside the cutout)."""

    cutout: Cutout
    data: npt.NDArray[np.float32]
    variance: npt.NDArray[np.float32]
    flags: npt.NDArray[np.uint32]
    lambda_um: float


def celestial_wcs(cutout: Cutout) -> WCS:
    return WCS(cutout.header).celestial


def subtract_background(cutout: Cutout, valid: npt.NDArray[np.bool_]) -> npt.NDArray[np.float64]:
    """ZODI model first (the pipeline does not subtract it), then a local 2D background.

    A single median leaves the halos of bright neighbours (ε Indi A sits 6.7′ from ε Indi B) and they differ
    between visits; boxes remove them. Cutouts truncated below two boxes fall back to a global median.
    """
    data = cutout.image.astype(np.float64) - cutout.zodi
    if int(valid.sum()) < MIN_BACKGROUND_PIXELS:
        return data
    if min(data.shape) >= 2 * BACKGROUND_BOX_PX:
        try:
            background = Background2D(
                data,
                (BACKGROUND_BOX_PX, BACKGROUND_BOX_PX),
                # A 3x3 median over the box grid flattens gradients near the edges (residual ~2 on a 0-20 ramp).
                filter_size=(1, 1),
                mask=~valid,
                sigma_clip=SigmaClip(sigma=3.0),
                bkg_estimator=MedianBackground(),
                exclude_percentile=50.0,
            )
            return data - np.asarray(background.background, dtype=np.float64)
        except ValueError as exc:
            logger.info("2D background failed for %s, using a median: %s", cutout.meta.key, exc)
    _, median, _ = sigma_clipped_stats(data[valid], sigma=3.0)
    return data - float(median)


def _lambda_at(cutout: Cutout, wcs: WCS, ra_deg: float, dec_deg: float) -> float:
    x, y = wcs.world_to_pixel_values(ra_deg, dec_deg)
    col, row = round(float(x)), round(float(y))
    ny, nx = cutout.wavelength_um.shape
    if 0 <= row < ny and 0 <= col < nx:
        return float(cutout.wavelength_um[row, col])
    return float("nan")


def to_grid(cutout: Cutout, target: Target, grid_wcs: WCS, shape: tuple[int, int], mask_bits: int) -> GridExposure:
    wcs = celestial_wcs(cutout)
    valid = ((cutout.flags & np.uint32(mask_bits)) == 0) & np.isfinite(cutout.image) & np.isfinite(cutout.zodi)
    valid &= np.isfinite(cutout.variance) & (cutout.variance > 0)
    data = np.where(valid, subtract_background(cutout, valid), 0.0)
    variance = np.where(valid, cutout.variance.astype(np.float64), 0.0)

    # A single NaN makes a bicubic spline return NaN everywhere, so holes are filled with the background level
    # (0 after subtraction) and re-masked from a bilinearly resampled validity map.
    def resample(array: npt.NDArray[np.float64], order: str) -> npt.NDArray[np.float64]:
        out: npt.NDArray[np.float64] = reproject_interp(
            (array, wcs), grid_wcs, shape_out=shape, order=order, return_footprint=False
        )
        return out

    coverage = resample(valid.astype(np.float64), "bilinear")
    usable = np.isfinite(coverage) & (coverage >= MIN_COVERAGE)
    grid_data = np.where(usable, resample(data, "bicubic"), np.nan)
    grid_variance = np.where(usable, resample(variance, "bilinear"), np.nan)
    grid_flags = resample(cutout.flags.astype(np.float64), "nearest-neighbor")

    ra_deg, dec_deg = position_at(target, cutout.mjd_avg)
    return GridExposure(
        cutout=cutout,
        data=grid_data.astype(np.float32),
        variance=grid_variance.astype(np.float32),
        flags=np.nan_to_num(grid_flags, nan=0.0).astype(np.uint32),
        lambda_um=_lambda_at(cutout, wcs, ra_deg, dec_deg),
    )
