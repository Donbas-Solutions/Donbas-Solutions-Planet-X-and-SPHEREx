"""IRSA cutouts: URL and size, EPSF stripping, and loading a stripped file into a Cutout."""

from __future__ import annotations

import io
import re
import uuid
from pathlib import Path
from typing import Final

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from ..astrometry import DAYS_PER_JULIAN_YEAR, total_proper_motion_arcsec_per_yr
from ..domain import Cutout, ExposureMeta, Target

KEPT_HDUS: Final = ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "WCS-WAVE")
FOV_MARGIN: Final = 1.3
_SIP_KEY = re.compile(r"^(A|B|AP|BP)_(ORDER|DMAX|\d+_\d+)$")
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
_CRPIX_KEY = re.compile(r"^CRPIX[12][A-Z]?$")


def cutout_url(access_url: str, ra_deg: float, dec_deg: float, size_deg: float) -> str:
    return f"{access_url}?center={ra_deg:.6f},{dec_deg:.6f}&size={size_deg:.4f}"


def cutout_size_deg(fov_arcmin: float, target: Target, span_days: float) -> float:
    """Side of the cutout: FOV with a margin for reprojection plus the target's motion over the data span."""
    motion_arcsec = total_proper_motion_arcsec_per_yr(target) * span_days / DAYS_PER_JULIAN_YEAR
    return fov_arcmin * FOV_MARGIN / 60 + motion_arcsec / 3600


def cache_name(meta: ExposureMeta, ra_deg: float, dec_deg: float, size_deg: float) -> str:
    return f"{_UNSAFE.sub('_', meta.key)}__{ra_deg:.4f}_{dec_deg:+.4f}_{size_deg:.4f}.fits"


def strip_to_file(fits_bytes: bytes, path: Path) -> None:
    """Keep only the HDUs the pipeline needs."""
    with fits.open(io.BytesIO(fits_bytes)) as hdul:
        kept = fits.HDUList([fits.PrimaryHDU(header=hdul[0].header)] + [hdul[name].copy() for name in KEPT_HDUS])
        write_atomic(kept, path)


def write_atomic(hdul: fits.HDUList, path: Path) -> None:
    """A crash never leaves a valid-looking file, and concurrent writers of one exposure never share a temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        hdul.writeto(tmp)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def shift_crpix(header: fits.Header, x0: int, y0: int) -> fits.Header:
    """Header of a window starting at 0-based pixel (x0, y0): every CRPIX of every WCS key moves, as IRSA does."""
    shifted = header.copy()
    for key in [k for k in shifted if _CRPIX_KEY.match(k)]:
        shifted[key] = shifted[key] - (x0 if key[5] == "1" else y0)
    return shifted


def _without_sip(header: fits.Header) -> fits.Header:
    # The spectral lookup table is indexed by raw pixels; SIP belongs to the celestial WCS only.
    clean = header.copy()
    for key in [k for k in clean if _SIP_KEY.match(k)]:
        del clean[key]
    return clean


def load_cutout(path: Path, meta: ExposureMeta, visit_id: str) -> Cutout:
    with fits.open(path) as hdul:
        header = hdul["IMAGE"].header.copy()
        image = np.asarray(hdul["IMAGE"].data, dtype=np.float32)
        spectral = WCS(_without_sip(header), fobj=hdul, key="W")
        rows, cols = np.mgrid[0 : image.shape[0], 0 : image.shape[1]]
        wavelength, bandwidth = spectral.pixel_to_world_values(cols, rows)
        return Cutout(
            meta=meta,
            visit_id=visit_id,
            mjd_avg=float(header["MJD-AVG"]),
            image=image,
            variance=np.asarray(hdul["VARIANCE"].data, dtype=np.float32),
            zodi=np.asarray(hdul["ZODI"].data, dtype=np.float32),
            flags=np.asarray(hdul["FLAGS"].data).astype(np.uint32),
            wavelength_um=np.asarray(wavelength, dtype=np.float32),
            bandwidth_um=np.asarray(bandwidth, dtype=np.float32),
            header=header,
        )
