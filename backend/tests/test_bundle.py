"""Static bundle writer: output must satisfy the contract (docs/api.md)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.domain import FrameArrays, SequenceResult
from app.flags import DEFAULT_FLAG_BITS
from app.grid import make_grid
from app.models import Frame, Sequence, SequenceMeta, Stretch
from app.pipeline.bundle import BundleError, write_bundle

SHAPE = (5, 7)


def make_result(frame_id: str = "v1-D3", shape: tuple[int, int] = SHAPE) -> SequenceResult:
    _, grid = make_grid(269.45, 4.69, fov_arcmin=2.0)
    frame = Frame(
        id=frame_id,
        kind="visit_stack",
        label="2025-08 · D3",
        mjd_mid=60950.0,
        date_range=("2025-08-15", "2025-10-01"),
        detectors=[3],
        lambda_um=(1.64, 2.42),
        n_exposures=20,
        data="",
        shape=SHAPE,
    )
    sequence = Sequence(
        grid=grid,
        stretch=Stretch(vmin=0.0, vmax=1.0),
        flag_bits=list(DEFAULT_FLAG_BITS),
        frames=[frame],
        meta=SequenceMeta(
            collections=["spherex_dr1"],
            n_exposures_total=20,
            generated_at="2026-11-14T00:00:00+00:00",
            pipeline_tags=[],
        ),
    )
    data = np.arange(shape[0] * shape[1], dtype=np.float32).reshape(shape)
    flags = np.full(shape, 1 << 21, dtype=np.uint32)
    return SequenceResult(sequence=sequence, arrays={frame_id: FrameArrays(data=data, flags=flags)})


def test_bundle_round_trips_through_the_contract(tmp_path: Path) -> None:
    manifest = write_bundle(make_result(), tmp_path)
    sequence = Sequence.model_validate_json(manifest.read_text(encoding="utf-8"))
    frame = sequence.frames[0]
    assert (frame.data, frame.flags) == ("frames/v1-D3.f32", "frames/v1-D3.flags.u32")
    data = np.fromfile(tmp_path / frame.data, dtype="<f4").reshape(SHAPE)
    np.testing.assert_array_equal(data, make_result().arrays["v1-D3"].data)
    assert (np.fromfile(tmp_path / "frames/v1-D3.flags.u32", dtype="<u4") == 1 << 21).all()


def test_unsafe_frame_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(BundleError):
        write_bundle(make_result(frame_id="../escape"), tmp_path)


def test_shape_mismatch_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(BundleError):
        write_bundle(make_result(shape=(4, 4)), tmp_path)
