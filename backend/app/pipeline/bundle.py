"""Static bundle writer (docs/api.md → Static bundles): sequence.json + frames/<id>.f32 + frames/<id>.flags.u32."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from ..domain import SequenceResult
from ..models import Frame

MANIFEST: Final = "sequence.json"
_FRAME_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_FRAME_SUFFIXES: Final = (".f32", ".u32")


class BundleError(ValueError):
    pass


def _check(result: SequenceResult, frame: Frame) -> None:
    if not _FRAME_ID.fullmatch(frame.id):
        raise BundleError(f"Frame id {frame.id!r} is not a safe file name")
    arrays = result.arrays.get(frame.id)
    if arrays is None:
        raise BundleError(f"No arrays for frame {frame.id!r}")
    if arrays.data.shape != frame.shape or arrays.flags.shape != frame.shape:
        raise BundleError(f"Arrays of frame {frame.id!r} do not match shape {frame.shape}")


def write_bundle(result: SequenceResult, out_dir: Path) -> Path:
    """Write the bundle and return the manifest path. The manifest is written last: its presence marks a
    complete bundle."""
    for frame in result.sequence.frames:
        _check(result, frame)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in frames_dir.iterdir():
        if stale.suffix in _FRAME_SUFFIXES:
            stale.unlink()

    frames: list[Frame] = []
    for frame in result.sequence.frames:
        arrays = result.arrays[frame.id]
        data_path, flags_path = f"frames/{frame.id}.f32", f"frames/{frame.id}.flags.u32"
        arrays.data.astype("<f4").tofile(out_dir / data_path)
        arrays.flags.astype("<u4").tofile(out_dir / flags_path)
        frames.append(frame.model_copy(update={"data": data_path, "flags": flags_path}))

    manifest = out_dir / MANIFEST
    sequence = result.sequence.model_copy(update={"frames": frames})
    manifest.write_text(sequence.model_dump_json(indent=1) + "\n", encoding="utf-8")
    return manifest
