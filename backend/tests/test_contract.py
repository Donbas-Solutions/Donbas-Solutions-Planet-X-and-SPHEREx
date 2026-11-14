"""Shared files must match the contract (docs/api.md, app/models.py)."""

import json

import numpy as np
from conftest import REPO_ROOT

from app.models import Sequence

MOCK = REPO_ROOT / "frontend" / "public" / "mock"


def test_mock_manifest_matches_contract():
    seq = Sequence.model_validate_json((MOCK / "sequence.json").read_text(encoding="utf-8"))
    assert seq.meta.mock
    assert seq.frames
    for frame in seq.frames:
        ny, nx = frame.shape
        data = np.fromfile(MOCK / frame.data, dtype="<f4")
        assert data.size == ny * nx, frame.id
        flags = np.fromfile(MOCK / frame.flags, dtype="<u4")
        assert flags.size == ny * nx, frame.id
        if frame.expected_px:
            assert 0 <= frame.expected_px.x < nx and 0 <= frame.expected_px.y < ny


def test_targets_file():
    payload = json.loads((REPO_ROOT / "science" / "targets.json").read_text(encoding="utf-8"))
    ids = {t["id"] for t in payload["targets"]}
    assert ids == {"barnard", "eps_ind_b", "wise0855", "rw_aur", "r_dra"}
    for t in payload["targets"]:
        assert 0 <= t["ra"] < 360 and -90 <= t["dec"] <= 90
        assert t["ref_epoch"] == 2000.0
    wise = next(t for t in payload["targets"] if t["id"] == "wise0855")
    # The challenge coordinates are the WISE-epoch position, not J2000.
    assert 2009 < wise["doc_epoch_estimate"] < 2012
