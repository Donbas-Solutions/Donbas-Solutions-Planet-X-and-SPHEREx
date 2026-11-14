"""Science pipeline on synthetic cutouts with known truth (SR-1, SR-3 … SR-6)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from app.astrometry import position_at
from app.domain import Cutout, ExposureMeta, SequenceParams, Target
from app.models import Sequence
from app.pipeline.bundle import write_bundle
from app.pipeline.measure import Shift, centroid, masked_core_center
from app.pipeline.sequence import SequenceError, build_sequence

PIXSCALE_DEG = 6.2 / 3600
ZODI_LEVEL = 5.0
SIGMA_PX = 0.8
OVERFLOW = 1 << 1
SOURCE = 1 << 21
MJD_V1, MJD_V2 = 61000.0, 61365.25
MOVER = Target(ra_deg=150.0, dec_deg=10.0, ref_epoch=2025.0, pmra_masyr=0.0, pmdec_masyr=12400.0, name="mover")


def make_cutout(
    mjd: float,
    visit_id: str,
    detector: int,
    target: Target = MOVER,
    *,
    npix: int = 60,
    rotation_deg: float = 8.0,
    flux: float = 500.0,
    flag_core: int = 0,
) -> Cutout:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [target.ra_deg, target.dec_deg]
    wcs.wcs.crpix = [npix / 2 + 0.3, npix / 2 - 0.2]
    c, s = math.cos(math.radians(rotation_deg)), math.sin(math.radians(rotation_deg))
    wcs.wcs.cd = PIXSCALE_DEG * np.array([[-c, s], [s, c]])
    x, y = wcs.world_to_pixel_values(*position_at(target, mjd))
    rows, cols = np.mgrid[0:npix, 0:npix]
    r2 = (cols - float(x)) ** 2 + (rows - float(y)) ** 2
    rng = np.random.default_rng(int(mjd) + detector)
    source = flux / (2 * math.pi * SIGMA_PX**2) * np.exp(-r2 / (2 * SIGMA_PX**2))
    image = (ZODI_LEVEL + source + rng.normal(0, 0.1, (npix, npix))).astype(np.float32)
    flags = np.where(source > 1, SOURCE, 0).astype(np.uint32)
    if flag_core:
        flags[r2 < 1.0] |= np.uint32(flag_core)
    header = wcs.to_header()
    header["MJD-AVG"] = mjd
    meta = ExposureMeta(
        obs_id=f"obs{mjd:.2f}".replace(".", "_"),
        detector=detector,
        collection="spherex_dr1",
        access_url="https://example.invalid/level2_l2b-v27-test.fits",
        mjd_start=mjd,
        mjd_end=mjd + 0.001,
        lambda_min_um=1.0,
        lambda_max_um=1.2,
    )
    return Cutout(
        meta=meta,
        visit_id=visit_id,
        mjd_avg=mjd,
        image=image,
        variance=np.full((npix, npix), 0.01, dtype=np.float32),
        zodi=np.full((npix, npix), ZODI_LEVEL, dtype=np.float32),
        flags=flags,
        wavelength_um=np.tile(np.linspace(1.0, 1.2, npix, dtype=np.float32), (npix, 1)),
        bandwidth_um=np.full((npix, npix), 0.02, dtype=np.float32),
        header=header,
    )


def two_visits() -> list[Cutout]:
    return [
        make_cutout(MJD_V1, "v1", 3),
        make_cutout(MJD_V1 + 1, "v1", 3),
        make_cutout(MJD_V1 + 2, "v1", 5),
        make_cutout(MJD_V2, "v2", 3),
        make_cutout(MJD_V2 + 1, "v2", 3),
        make_cutout(MJD_V2 + 2, "v2", 5),
    ]


def test_frames_per_visit_detector_and_all_in_time_order() -> None:
    result = build_sequence(two_visits(), MOVER, SequenceParams(fov_arcmin=4.0))
    assert [f.id for f in result.sequence.frames] == ["v1-D3", "v1-D5", "v1-all", "v2-D3", "v2-D5", "v2-all"]
    assert result.sequence.frames[0].n_exposures == 2
    assert result.sequence.meta.pipeline_tags == ["l2b-v27"]


def test_output_satisfies_the_contract(tmp_path: Path) -> None:
    manifest = write_bundle(build_sequence(two_visits(), MOVER, SequenceParams(fov_arcmin=4.0)), tmp_path)
    assert len(Sequence.model_validate_json(manifest.read_text(encoding="utf-8")).frames) == 6


def test_zodi_and_background_are_removed() -> None:
    result = build_sequence(two_visits(), MOVER, SequenceParams(fov_arcmin=4.0))
    data = result.arrays["v1-D3"].data
    assert float(np.nanmedian(data)) == pytest.approx(0.0, abs=0.05)


def test_measured_motion_matches_proper_motion() -> None:
    result = build_sequence(two_visits(), MOVER, SequenceParams(fov_arcmin=4.0))
    first, last = result.sequence.frames[0], result.sequence.frames[3]
    assert first.expected_px is not None
    assert last.expected_px is not None
    a = centroid(result.arrays[first.id].data, first.expected_px.x, first.expected_px.y, 3.0)
    b = centroid(result.arrays[last.id].data, last.expected_px.x, last.expected_px.y, 3.0)
    assert a is not None
    assert b is not None
    shift = Shift(b[0] - a[0], b[1] - a[1], 6.2)
    assert shift.length_arcsec == pytest.approx(12.4, abs=1.0)
    assert min(shift.position_angle_deg, 360 - shift.position_angle_deg) < 10


def test_saturated_core_is_masked_but_source_flag_is_not() -> None:
    cutouts = [make_cutout(MJD_V1, "v1", 3, flag_core=OVERFLOW), make_cutout(MJD_V2, "v2", 3)]
    result = build_sequence(cutouts, MOVER, SequenceParams(fov_arcmin=4.0))
    saturated, clean = result.sequence.frames[0], result.sequence.frames[2]
    assert saturated.expected_px is not None
    assert clean.expected_px is not None
    core = result.arrays[saturated.id].data[round(saturated.expected_px.y), round(saturated.expected_px.x)]
    assert np.isnan(core)
    assert "target pixel saturated (OVERFLOW/NONLINEAR)" in saturated.warnings
    assert np.isfinite(result.arrays[clean.id].data[round(clean.expected_px.y), round(clean.expected_px.x)])


def test_masked_core_centre_tracks_a_saturated_mover() -> None:
    cutouts = [make_cutout(MJD_V1, "v1", 3, flag_core=OVERFLOW), make_cutout(MJD_V2, "v2", 3, flag_core=OVERFLOW)]
    result = build_sequence(cutouts, MOVER, SequenceParams(fov_arcmin=4.0))
    first, last = result.sequence.frames[0], result.sequence.frames[2]
    assert first.expected_px is not None
    assert last.expected_px is not None
    a = masked_core_center(result.arrays[first.id].data, first.expected_px.x, first.expected_px.y, 3.0)
    b = masked_core_center(result.arrays[last.id].data, last.expected_px.x, last.expected_px.y, 3.0)
    assert a is not None
    assert b is not None
    assert Shift(b[0] - a[0], b[1] - a[1], 6.2).length_arcsec == pytest.approx(12.4, abs=1.5)


def test_detector_selection_and_few_exposure_warning() -> None:
    cutouts = [*two_visits(), make_cutout(MJD_V2 + 3, "v2", 3), make_cutout(MJD_V2 + 4, "v2", 3)]
    result = build_sequence(cutouts, MOVER, SequenceParams(fov_arcmin=4.0, detectors=(3,)))
    frames = {f.id: f for f in result.sequence.frames}
    assert set(frames) == {"v1-D3", "v1-all", "v2-D3", "v2-all"}
    assert any(w.startswith("few exposures") for w in frames["v1-D3"].warnings)


def test_no_matching_detector_is_an_error() -> None:
    with pytest.raises(SequenceError):
        build_sequence(two_visits(), MOVER, SequenceParams(detectors=(1,)))
