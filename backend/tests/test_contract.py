"""Shared files must match the contract (docs/api.md, app/models.py)."""

import json

import numpy as np
from conftest import REPO_ROOT

from app.models import Sequence, Spectrum

MOCK = REPO_ROOT / "frontend" / "public" / "mock"


def mock_spectrum() -> Spectrum:
    seq = Sequence.model_validate_json((MOCK / "sequence.json").read_text(encoding="utf-8"))
    assert seq.meta.spectrum is not None
    return Spectrum.model_validate_json((MOCK / seq.meta.spectrum).read_text(encoding="utf-8"))


def test_mock_spectrum_matches_contract() -> None:
    points = mock_spectrum().points
    assert {p.detector for p in points} == {1, 2, 3, 4, 5, 6}
    assert all(0.7 < p.lambda_um < 5.1 for p in points)
    assert [p.mjd for p in points] == sorted(p.mjd for p in points)


def test_saturated_spectrum_points_carry_no_numbers() -> None:
    saturated = [p for p in mock_spectrum().points if p.saturated]
    assert saturated
    assert all(p.flux_ujy is None and p.err_ujy is None for p in saturated)


def test_mock_manifest_matches_contract() -> None:
    seq = Sequence.model_validate_json((MOCK / "sequence.json").read_text(encoding="utf-8"))
    assert seq.meta.mock
    assert seq.frames
    for frame in seq.frames:
        ny, nx = frame.shape
        data = np.fromfile(MOCK / frame.data, dtype="<f4")
        assert data.size == ny * nx, frame.id
        assert frame.flags is not None, frame.id
        flags = np.fromfile(MOCK / frame.flags, dtype="<u4")
        assert flags.size == ny * nx, frame.id
        if frame.expected_px:
            assert 0 <= frame.expected_px.x < nx
            assert 0 <= frame.expected_px.y < ny


def test_targets_file() -> None:
    payload = json.loads((REPO_ROOT / "science" / "targets.json").read_text(encoding="utf-8"))
    ids = {t["id"] for t in payload["targets"]}
    assert ids == {"barnard", "eps_ind_b", "wise0855", "rw_aur", "r_dra"}
    for t in payload["targets"]:
        assert 0 <= t["ra"] < 360
        assert -90 <= t["dec"] <= 90
        assert t["ref_epoch"] == 2000.0
    wise = next(t for t in payload["targets"] if t["id"] == "wise0855")
    # The challenge coordinates are the WISE-epoch position, not J2000.
    assert 2009 < wise["doc_epoch_estimate"] < 2012
