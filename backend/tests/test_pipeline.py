"""Science pipeline on synthetic cutouts with known truth (SR-1, SR-3 … SR-6)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import pytest
from astropy.wcs import WCS

from app.astrometry import position_at
from app.domain import Cutout, ExposureMeta, SequenceParams, Target
from app.models import Sequence
from app.pipeline.bundle import write_bundle
from app.pipeline.measure import Shift, centroid, fit_position, fit_proper_motion, masked_core_center
from app.pipeline.photometry import measure_spectrum
from app.pipeline.sequence import DETECTOR_BANDS_UM, LVF_CHANNELS, SequenceError, build_sequence, lvf_channel

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


def test_bins_starting_in_one_month_are_named_by_the_day() -> None:
    bins = [
        make_cutout(60828.0, "v1", 3),
        make_cutout(60851.0, "v2", 3),
        make_cutout(60890.0, "v3", 3),
    ]
    result = build_sequence(bins, MOVER, SequenceParams(fov_arcmin=4.0))
    labels = {f.id: f.label for f in result.sequence.frames}
    assert (labels["v1-all"], labels["v2-all"], labels["v3-all"]) == (
        "2025-06-02 · all",
        "2025-06-25 · all",
        "2025-08 · all",
    )
    assert len(set(labels.values())) == len(labels)


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
    assert "saturated" in {w.code for w in saturated.warnings}
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
    assert "few_exposures" in {w.code for w in frames["v1-D3"].warnings}


def test_visit_missing_a_detector_gets_a_warning_on_its_all_stack() -> None:
    cutouts = [c for c in two_visits() if not (c.visit_id == "v2" and c.meta.detector == 5)]
    frames = {f.id: f for f in build_sequence(cutouts, MOVER, SequenceParams(fov_arcmin=4.0)).sequence.frames}
    assert "few_exposures" in {w.code for w in frames["v2-all"].warnings}


def at_lambda(cutout: Cutout, lambda_um: float) -> Cutout:
    return Cutout(**{**cutout.__dict__, "wavelength_um": np.full_like(cutout.wavelength_um, lambda_um)})


def channel_centre_um(detector: int, channel: int) -> float:
    lo, hi = DETECTOR_BANDS_UM[detector]
    return float(lo * (hi / lo) ** ((channel + 0.5) / LVF_CHANNELS))


def lambda_codes(
    cutouts: list[Cutout], mode: Literal["visit_stack", "exposures"] = "visit_stack"
) -> dict[str, list[str]]:
    result = build_sequence(cutouts, MOVER, SequenceParams(fov_arcmin=4.0, detectors=(3,), mode=mode))
    return {f.id: [w.message for w in f.warnings if w.code == "incomplete_lambda"] for f in result.sequence.frames}


def test_lvf_channels_are_equal_steps_in_log_lambda() -> None:
    assert lvf_channel(3, 1.64) == 0
    assert lvf_channel(3, 2.4199) == LVF_CHANNELS - 1
    assert [lvf_channel(3, channel_centre_um(3, c)) for c in range(LVF_CHANNELS)] == list(range(LVF_CHANNELS))
    assert lvf_channel(3, 5.0) == LVF_CHANNELS - 1


def test_equally_capped_visits_still_warn_about_few_lvf_channels() -> None:
    cutouts = [
        at_lambda(make_cutout(mjd + i, visit, 3), channel_centre_um(3, 2 * i))
        for mjd, visit in ((MJD_V1, "v1"), (MJD_V2, "v2"))
        for i in range(8)
    ]
    codes = lambda_codes(cutouts)
    assert codes["v1-D3"] == codes["v2-D3"] == ["incomplete λ coverage: 8 of 17 LVF channels"]


def test_full_lvf_coverage_has_no_lambda_warning() -> None:
    cutouts = [
        at_lambda(make_cutout(mjd + i / 10, visit, 3), channel_centre_um(3, i))
        for mjd, visit in ((MJD_V1, "v1"), (MJD_V2, "v2"))
        for i in range(LVF_CHANNELS)
    ]
    assert lambda_codes(cutouts) == {"v1-D3": [], "v1-all": [], "v2-D3": [], "v2-all": []}


def test_single_exposures_get_no_lambda_warning() -> None:
    cutouts = [at_lambda(make_cutout(MJD_V1, "v1", 3), 2.0), at_lambda(make_cutout(MJD_V2, "v2", 3), 2.0)]
    assert all(not messages for messages in lambda_codes(cutouts, mode="exposures").values())


def test_background_gradient_is_removed() -> None:
    cutout = make_cutout(MJD_V1, "v1", 3, npix=80)
    ramp = np.tile(np.linspace(0, 20, 80, dtype=np.float32), (80, 1))
    halo = Cutout(**{**cutout.__dict__, "image": cutout.image + ramp})
    data = build_sequence([halo], MOVER, SequenceParams(fov_arcmin=6.0)).arrays["v1-D3"].data
    left, right = np.nanmedian(data[:, :15]), np.nanmedian(data[:, -15:])
    assert abs(float(right - left)) < 0.5


@pytest.mark.parametrize("true_dx", [0.3, 0.5, 0.7])
def test_gaussian_fit_beats_centroid_on_subpixel_shifts(true_dx: float) -> None:
    rows, cols = np.mgrid[0:21, 0:21]

    def star(x: float) -> npt.NDArray[np.float32]:
        r2 = (cols - x) ** 2 + (rows - 10.0) ** 2
        image: npt.NDArray[np.float32] = (100 * np.exp(-r2 / (2 * 0.6**2))).astype(np.float32)
        return image

    fit_a, fit_b = fit_position(star(10.0), 10, 10), fit_position(star(10.0 + true_dx), 10, 10)
    com_a, com_b = centroid(star(10.0), 10, 10, 3.0), centroid(star(10.0 + true_dx), 10, 10, 3.0)
    assert fit_a is not None
    assert fit_b is not None
    assert com_a is not None
    assert com_b is not None
    assert abs((fit_b[0] - fit_a[0]) - true_dx) < 0.02
    assert abs((fit_b[0] - fit_a[0]) - true_dx) <= abs((com_b[0] - com_a[0]) - true_dx)


def test_proper_motion_fit_recovers_a_known_motion() -> None:
    mjds = [61000.0, 61182.6, 61365.25]
    # 2 px/yr north and 1 px/yr east (x grows west) at 6.2″/px, plus small centroid noise.
    xs = [50.0 - (m - mjds[0]) / 365.25 + n for m, n in zip(mjds, (0.01, -0.02, 0.01), strict=True)]
    ys = [50.0 + 2 * (m - mjds[0]) / 365.25 + n for m, n in zip(mjds, (-0.01, 0.02, -0.01), strict=True)]
    fit = fit_proper_motion(mjds, xs, ys, 6.2)
    assert fit.pmra_masyr == pytest.approx(6200, abs=150)
    assert fit.pmdec_masyr == pytest.approx(12400, abs=150)
    assert fit.pmra_err_masyr is not None
    assert fit.pmra_err_masyr > 0


def test_proper_motion_fit_has_no_error_with_two_epochs() -> None:
    fit = fit_proper_motion([61000.0, 61365.25], [50.0, 49.0], [50.0, 52.0], 6.2)
    assert fit.pmdec_err_masyr is None
    assert fit.offset_sigma(6200, 12400) is None


def test_photometry_recovers_flux_and_flags_saturation() -> None:
    clean = make_cutout(MJD_V1, "v1", 3, flux=500.0)
    saturated = make_cutout(MJD_V2, "v2", 3, flux=500.0, flag_core=OVERFLOW)
    points = {p.visit: p for p in measure_spectrum([clean, saturated], MOVER).points}
    pixel_sr = (6.2 / 206265) ** 2
    expected_ujy = 500.0 * pixel_sr * 1e12  # 500 MJy/sr summed over pixels → µJy
    assert points["v1"].flux_ujy == pytest.approx(expected_ujy, rel=0.05)
    assert points["v1"].err_ujy is not None
    assert 1.0 <= points["v1"].lambda_um <= 1.2
    assert points["v2"].saturated
    assert points["v2"].flux_ujy is None


def test_no_matching_detector_is_an_error() -> None:
    with pytest.raises(SequenceError):
        build_sequence(two_visits(), MOVER, SequenceParams(detectors=(1,)))
