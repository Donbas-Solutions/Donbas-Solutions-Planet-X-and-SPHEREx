"""Build a sequence from the cached development sample and show it as a PNG strip + numbers (Checkpoint C1).

Usage (from the repo root; run scripts/fetch_sample.py first):
    uv run --project backend python science/preview.py barnard eps_ind_b

Writes cache/preview/<target>/ (bundle + preview.png): one row per detector set, one column per visit, and the
difference last − first visit (blue = earlier position, orange = later).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from app.archive.naive import fetch_sample
from app.config import configure_ssl, settings
from app.domain import FrameArrays, SequenceParams, SequenceResult, Target
from app.models import Frame
from app.pipeline.bundle import write_bundle
from app.pipeline.measure import Shift, locate_source
from app.pipeline.sequence import build_sequence

ROOT = Path(__file__).resolve().parents[1]
ZOOM = 4


def load_target(target_id: str) -> tuple[Target, dict[str, object]]:
    payload = json.loads((ROOT / "science" / "targets.json").read_text(encoding="utf-8"))
    entry = next(t for t in payload["targets"] if t["id"] == target_id)
    target = Target(
        ra_deg=entry["ra"],
        dec_deg=entry["dec"],
        ref_epoch=entry["ref_epoch"],
        pmra_masyr=entry["pmra"],
        pmdec_masyr=entry["pmdec"],
        name=entry["name"],
    )
    return target, entry


def to_gray(data: npt.NDArray[np.float32], vmin: float, vmax: float) -> Image.Image:
    t = np.clip((np.nan_to_num(data, nan=vmin) - vmin) / (vmax - vmin), 0, 1)
    stretched = np.arcsinh(t / 0.1) / np.arcsinh(1 / 0.1)
    img = (np.flipud(stretched) * 255).astype(np.uint8)
    return Image.fromarray(img, "L").convert("RGB")


def to_diverging(diff: npt.NDArray[np.float32], limit: float) -> Image.Image:
    t = np.clip(np.nan_to_num(diff) / limit, -1, 1)
    rgb = np.zeros((*diff.shape, 3))
    orange, blue = np.array([1.0, 0.55, 0.1]), np.array([0.15, 0.45, 1.0])
    rgb += np.where(t[..., None] > 0, t[..., None] * orange, 0)
    rgb += np.where(t[..., None] < 0, -t[..., None] * blue, 0)
    return Image.fromarray((np.flipud(rgb) * 255).astype(np.uint8), "RGB")


def tile(img: Image.Image, label: str) -> Image.Image:
    big = img.resize((img.width * ZOOM, img.height * ZOOM), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (big.width, big.height + 14), "black")
    canvas.paste(big, (0, 14))
    ImageDraw.Draw(canvas).text((2, 1), label, fill="white")
    return canvas


def rows_by_set(result: SequenceResult) -> dict[str, list[Frame]]:
    rows: dict[str, list[Frame]] = {}
    for frame in result.sequence.frames:
        rows.setdefault(frame.id.split("-", 1)[1], []).append(frame)
    return rows


def report_shift(name: str, first: Frame, last: Frame, arrays: dict[str, FrameArrays], pixscale: float) -> None:
    if first.expected_px is None or last.expected_px is None:
        return
    expected = Shift(last.expected_px.x - first.expected_px.x, last.expected_px.y - first.expected_px.y, pixscale)
    a = locate_source(arrays[first.id].data, first.expected_px.x, first.expected_px.y)
    b = locate_source(arrays[last.id].data, last.expected_px.x, last.expected_px.y)
    if a is None or b is None:
        print(f"  {name}: no source found near the expected position")
        return
    measured = Shift(b[0] - a[0], b[1] - a[1], pixscale)
    print(
        f"  {name}: measured {measured.length_px:.2f} px @ PA {measured.position_angle_deg:.0f}°, "
        f"expected {expected.length_px:.2f} px @ PA {expected.position_angle_deg:.0f}°"
    )


def preview(target_id: str, max_per_detector: int) -> None:
    target, _ = load_target(target_id)
    sample = fetch_sample(target, max_per_detector=max_per_detector)
    result = build_sequence(sample.cutouts, target, SequenceParams())
    out = settings.cache_dir / "preview" / target_id
    write_bundle(result, out)
    seq = result.sequence
    arrays = dict(result.arrays)
    print(f"{target_id}: {len(sample.cutouts)} cutouts → {len(seq.frames)} frames, grid {seq.grid.npix}px")

    rows = []
    for name, frames in rows_by_set(result).items():
        first, last = frames[0], frames[-1]
        diff = arrays[last.id].data - arrays[first.id].data
        finite = diff[np.isfinite(diff)]
        limit = float(np.percentile(np.abs(finite), 99.5)) if finite.size else 1.0
        tiles = [tile(to_gray(arrays[f.id].data, seq.stretch.vmin, seq.stretch.vmax), f.label) for f in frames]
        tiles.append(tile(to_diverging(diff, limit or 1.0), f"{name}: last-first"))
        row = Image.new("RGB", (sum(t.width for t in tiles), max(t.height for t in tiles)), "black")
        x = 0
        for t in tiles:
            row.paste(t, (x, 0))
            x += t.width
        rows.append(row)
        report_shift(name, first, last, arrays, seq.grid.pixscale_arcsec)
        for f in frames:
            if f.warnings:
                print(f"    {f.id}: {'; '.join(w.message for w in f.warnings)}")
    sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), "black")
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(out / "preview.png")
    print(f"  wrote {out / 'preview.png'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="+")
    parser.add_argument("--max-per-detector", type=int, default=4)
    args = parser.parse_args()
    logging.getLogger("astropy").setLevel(logging.ERROR)
    configure_ssl()
    for target_id in args.targets:
        preview(target_id, args.max_per_detector)


if __name__ == "__main__":
    main()
