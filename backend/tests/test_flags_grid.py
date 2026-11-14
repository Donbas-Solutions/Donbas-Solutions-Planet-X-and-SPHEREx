import numpy as np
from astropy.io.fits import Header

from app.flags import DEFAULT_FLAG_BITS, flag_bits_from_header, stack_mask_bits
from app.grid import make_grid


def test_flags_from_header_and_policy() -> None:
    header = Header()
    header["MSKN0001"] = "OVERFLOW"
    header["MSKD0001"] = "Overflow detected during SUR"
    header["MSKN0021"] = "SOURCE"
    header["MSKN0030"] = "NEWTHING"
    bits = {b.name: b for b in flag_bits_from_header(header)}
    assert bits["OVERFLOW"].mask_in_stack
    assert bits["OVERFLOW"].group == "saturation"
    assert not bits["SOURCE"].mask_in_stack  # masking SOURCE would erase every star
    assert bits["NEWTHING"].group == "artifact"
    assert not bits["NEWTHING"].mask_in_stack


def test_stack_mask_never_includes_source() -> None:
    mask = stack_mask_bits(DEFAULT_FLAG_BITS)
    assert mask & (1 << 21) == 0
    assert mask & (1 << 1)  # OVERFLOW


def test_grid_is_north_up_east_left_and_centred() -> None:
    wcs, grid = make_grid(269.45, 4.69, fov_arcmin=10.0)
    assert grid.npix % 2 == 1
    c = (grid.npix - 1) / 2
    ra, dec = wcs.pixel_to_world_values(c, c)
    assert np.isclose(ra, 269.45)
    assert np.isclose(dec, 4.69)
    _, dec_up = wcs.pixel_to_world_values(c, c + 1)
    ra_right, _ = wcs.pixel_to_world_values(c + 1, c)
    assert dec_up > dec  # row + 1 = north
    assert ra_right < ra  # column + 1 = west
