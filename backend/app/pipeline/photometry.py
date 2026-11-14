"""Forced aperture photometry on native cutouts → spectrum and light curve points (FR-16, FR-17).

Measured on the original pixels (no resampling), at the target position propagated to each exposure. The pixel
solid angle comes from the celestial WCS; the per-pixel SAPM calibration map (on S3) would refine it by the
small distortion term.
"""

from __future__ import annotations

import functools
import math
import operator
from collections.abc import Sequence
from typing import Final

import numpy as np
from astropy.wcs.utils import proj_plane_pixel_area
from photutils.aperture import ApertureStats, CircularAnnulus, CircularAperture

from ..astrometry import position_at
from ..domain import Cutout, Target
from ..flags import DEFAULT_FLAG_BITS
from ..models import Spectrum, SpectrumPoint
from .exposure import celestial_wcs

APERTURE_RADIUS_PX: Final = 3.0
ANNULUS_PX: Final = (5.0, 8.0)
_MJY_SR_TO_UJY_PER_DEG2: Final = 1e12 * (math.pi / 180) ** 2
_SATURATION: Final = sum(1 << b.bit for b in DEFAULT_FLAG_BITS if b.group == "saturation")
_BAD: Final = sum(1 << b.bit for b in DEFAULT_FLAG_BITS if b.group == "bad")


def _point(cutout: Cutout, target: Target) -> SpectrumPoint | None:
    wcs = celestial_wcs(cutout)
    ra_deg, dec_deg = position_at(target, cutout.mjd_avg)
    x, y = (float(v) for v in wcs.world_to_pixel_values(ra_deg, dec_deg))
    ny, nx = cutout.image.shape
    outer = ANNULUS_PX[1]
    if not (outer <= x < nx - outer and outer <= y < ny - outer):
        return None

    aperture = CircularAperture((x, y), r=APERTURE_RADIUS_PX)
    flag_mask = aperture.to_mask(method="center")
    aperture_flags = np.asarray(flag_mask.get_values(cutout.flags.astype(np.int64)), dtype=np.int64)
    flags = functools.reduce(operator.or_, (int(v) for v in aperture_flags.ravel()), 0)
    saturated = bool(flags & _SATURATION)

    data = (cutout.image - cutout.zodi).astype(np.float64)
    invalid = ~np.isfinite(data) | ((cutout.flags & np.uint32(_BAD)) != 0)
    background = ApertureStats(data, CircularAnnulus((x, y), *ANNULUS_PX), mask=invalid).median
    source = ApertureStats(data - background, aperture, error=np.sqrt(np.clip(cutout.variance, 0, None)), mask=invalid)

    to_ujy = proj_plane_pixel_area(wcs) * _MJY_SR_TO_UJY_PER_DEG2
    usable = not saturated and not (flags & _BAD) and np.isfinite(source.sum)
    return SpectrumPoint(
        lambda_um=round(float(cutout.wavelength_um[round(y), round(x)]), 4),
        flux_ujy=round(float(source.sum) * to_ujy, 3) if usable else None,
        err_ujy=round(float(source.sum_err) * to_ujy, 3) if usable else None,
        mjd=round(cutout.mjd_avg, 5),
        detector=cutout.meta.detector,
        visit=cutout.visit_id,
        saturated=saturated,
        flags=flags,
    )


def measure_spectrum(cutouts: Sequence[Cutout], target: Target) -> Spectrum:
    """One point per exposure whose aperture and annulus fit on the cutout, sorted by wavelength."""
    points = [p for c in cutouts if (p := _point(c, target)) is not None]
    return Spectrum(points=sorted(points, key=lambda p: (p.lambda_um, p.mjd)))
