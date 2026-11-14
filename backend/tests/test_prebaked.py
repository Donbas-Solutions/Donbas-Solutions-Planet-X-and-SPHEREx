"""The committed static bundles (FR-3, FR-14) must satisfy the contract (docs/api.md → Static bundles)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from conftest import REPO_ROOT

from app.models import Sequence, Spectrum

PREBAKED = REPO_ROOT / "frontend" / "public" / "prebaked"
TARGETS = ("barnard", "eps_ind_b", "wise0855", "rw_aur", "r_dra")


@pytest.mark.parametrize("target_id", TARGETS)
def test_bundle_loads_and_matches_the_contract(target_id: str) -> None:
    bundle = PREBAKED / target_id
    sequence = Sequence.model_validate_json((bundle / "sequence.json").read_text(encoding="utf-8"))
    assert sequence.frames
    assert not sequence.meta.mock
    for frame in sequence.frames:
        ny, nx = frame.shape
        assert np.fromfile(bundle / frame.data, dtype="<f4").size == ny * nx, frame.id
        assert frame.flags is not None
        assert np.fromfile(bundle / frame.flags, dtype="<u4").size == ny * nx, frame.id
    assert sequence.meta.spectrum is not None
    spectrum = Spectrum.model_validate_json((bundle / sequence.meta.spectrum).read_text(encoding="utf-8"))
    assert spectrum.points


@pytest.mark.parametrize("target_id", TARGETS)
def test_saturated_points_carry_no_flux(target_id: str) -> None:
    spectrum = Spectrum.model_validate_json((PREBAKED / target_id / "spectrum.json").read_text(encoding="utf-8"))
    assert all(p.flux_ujy is None for p in spectrum.points if p.saturated)


def test_bundles_stay_small() -> None:
    total_mb = sum(p.stat().st_size for p in Path(PREBAKED).rglob("*") if p.is_file()) / 1e6
    assert total_mb < 25
