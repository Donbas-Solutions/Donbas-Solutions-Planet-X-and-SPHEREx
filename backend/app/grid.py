"""Common north-up TAN grid that every frame of a sequence is reprojected onto."""

from __future__ import annotations

from astropy.wcs import WCS

from .models import Grid

SPHEREX_PIXSCALE_ARCSEC = 6.2


def make_grid(ra: float, dec: float, fov_arcmin: float, pixscale_arcsec: float = SPHEREX_PIXSCALE_ARCSEC) -> tuple[WCS, Grid]:
    """North up, east left. Array row 0 = south (FITS order); x grows to the west."""
    npix = max(3, int(round(fov_arcmin * 60 / pixscale_arcsec)))
    if npix % 2 == 0:
        npix += 1  # odd size: the target sits on the central pixel
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [(npix + 1) / 2, (npix + 1) / 2]  # FITS 1-based
    wcs.wcs.cdelt = [-pixscale_arcsec / 3600, pixscale_arcsec / 3600]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.radesys = "ICRS"
    wcs.pixel_shape = (npix, npix)

    header = wcs.to_header()
    header["NAXIS1"] = npix
    header["NAXIS2"] = npix
    cards = {k: header[k] for k in header if k not in ("COMMENT", "HISTORY", "")}
    grid = Grid(
        ra=ra, dec=dec, fov_arcmin=fov_arcmin, npix=npix, pixscale_arcsec=pixscale_arcsec, wcs=cards
    )
    return wcs, grid
