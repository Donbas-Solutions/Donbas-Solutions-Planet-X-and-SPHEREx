"""Archive layer: SIA parsing, visit grouping, caps, cutout files."""

from __future__ import annotations

import gzip
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from app.archive.cutouts import KEPT_HDUS, cache_name, cutout_size_deg, load_cutout, strip_to_file
from app.archive.sia import parse_sia_csv
from app.archive.visits import cap_per_detector, group_visits
from app.domain import ExposureMeta, Target

FIXTURES = Path(__file__).parent / "fixtures"
CUTOUT_FIXTURE = FIXTURES / "cutout_barnard_qr3_d3.fits"


def exposures_of(target_id: str) -> list[ExposureMeta]:
    raw = gzip.decompress((FIXTURES / "sia" / f"{target_id}.csv.gz").read_bytes())
    return parse_sia_csv(raw.decode("utf-8"))


def fixture_meta() -> ExposureMeta:
    return ExposureMeta(
        obs_id="2026W33_2A_0594_4",
        detector=3,
        collection="spherex_qr3",
        access_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/level2/2026W33_2A/l2b-v27-2026-241/3/level2_2026W33_2A_0594_4D3_spx_l2b-v27-2026-241.fits",
        mjd_start=61268.630,
        mjd_end=61268.633,
        lambda_min_um=1.6,
        lambda_max_um=2.5,
    )


@pytest.mark.parametrize(
    ("target_id", "n_exposures"),
    [("barnard", 363), ("eps_ind_b", 468), ("wise0855", 258), ("rw_aur", 336), ("r_dra", 2514)],
)
def test_parse_keeps_both_detectors_of_an_exposure(target_id: str, n_exposures: int) -> None:
    assert len(exposures_of(target_id)) == n_exposures


def test_parse_reads_detectors_and_wavelengths_in_um() -> None:
    exposures = exposures_of("barnard")
    assert {e.detector for e in exposures} == {1, 2, 3, 4, 5, 6}
    assert all(0.7 < e.lambda_min_um < e.lambda_max_um < 5.1 for e in exposures)


@pytest.mark.parametrize(("target_id", "n_visits"), [("barnard", 3), ("eps_ind_b", 4), ("wise0855", 3), ("rw_aur", 3)])
def test_survey_passes_become_visits(target_id: str, n_visits: int) -> None:
    visits = group_visits(exposures_of(target_id))
    assert [v.id for v in visits] == [f"v{i}" for i in range(1, n_visits + 1)]
    assert not any(v.binned for v in visits)


def test_wise0855_first_visit_is_short() -> None:
    assert len(group_visits(exposures_of("wise0855"))[0].exposures) == 30


def test_deep_field_is_split_into_30_day_bins() -> None:
    visits = group_visits(exposures_of("r_dra"))
    assert all(v.binned for v in visits)
    assert all(v.exposures[-1].mjd_mid - v.exposures[0].mjd_mid <= 30 for v in visits)
    assert sum(len(v.exposures) for v in visits) == 2514


def test_cap_per_detector_keeps_first_and_last() -> None:
    visit = group_visits(exposures_of("barnard"))[0]
    capped = cap_per_detector(visit, 4)
    assert max(Counter(e.detector for e in capped).values()) == 4
    for detector in {e.detector for e in visit.exposures}:
        same = [e for e in visit.exposures if e.detector == detector]
        kept = [e for e in capped if e.detector == detector]
        assert (kept[0], kept[-1]) == (same[0], same[-1])


def test_cutout_size_grows_with_proper_motion() -> None:
    barnard = Target(ra_deg=269.452, dec_deg=4.693, pmra_masyr=-801.551, pmdec_masyr=10362.394)
    static = Target(ra_deg=269.452, dec_deg=4.693)
    motion_deg = 10.393 / 3600
    assert cutout_size_deg(10, barnard, 365.25) == pytest.approx(
        cutout_size_deg(10, static, 365.25) + motion_deg, rel=1e-3
    )


def test_cache_name_is_a_safe_file_name() -> None:
    meta = fixture_meta()
    unsafe = ExposureMeta(**{**meta.__dict__, "obs_id": "../x/y z"})
    assert "/" not in cache_name(unsafe, 1.0, -2.0, 0.2)


def test_strip_keeps_only_needed_hdus(tmp_path: Path) -> None:
    out = tmp_path / "stripped.fits"
    strip_to_file(CUTOUT_FIXTURE.read_bytes(), out)
    with fits.open(out) as hdul:
        assert [h.name for h in hdul][1:] == list(KEPT_HDUS)


def test_load_cutout_gives_aligned_arrays_and_wavelengths() -> None:
    cutout = load_cutout(CUTOUT_FIXTURE, fixture_meta(), "v3")
    shape = cutout.image.shape
    assert shape == (29, 29)
    for array in (cutout.variance, cutout.zodi, cutout.flags, cutout.wavelength_um, cutout.bandwidth_um):
        assert array.shape == shape
    assert cutout.flags.dtype == np.uint32
    assert np.isfinite(cutout.wavelength_um).all()
    assert 1.5 < float(cutout.wavelength_um.mean()) < 2.5
    assert cutout.mjd_avg == pytest.approx(61268.6315, abs=1e-3)
