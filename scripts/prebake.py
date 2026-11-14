"""Build the static bundles of the test targets (FR-3, FR-14) into frontend/public/prebaked/<target>/.

Usage (from the repo root):
    uv run --project backend python scripts/prebake.py                    # all five targets
    uv run --project backend python scripts/prebake.py barnard --max-per-detector 20

Full depth is ~17 exposures per detector and visit (one per LVF channel); at the IRSA speed measured on 2026-11-14
(~4-6 s per cutout) a target takes 10-30 min, so run it unattended. Cutouts are cached in cache/raw/, so a re-run
only downloads what is missing. Depth per target is `prebake_cap` in science/targets.json (R Dra: smaller,
per 30-day bin). Writes spectrum.json (Spectrum model: one photometry point per exposure) next to sequence.json.
Also writes blink.gif (the all-detector visit stacks, 1 frame per second) next to each bundle for the pitch.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
from PIL import Image

from app.archive.naive import fetch_sample
from app.config import configure_ssl
from app.domain import SequenceParams, SequenceResult, Target
from app.pipeline.bundle import write_bundle
from app.pipeline.photometry import measure_spectrum
from app.pipeline.sequence import build_sequence

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "prebaked"
SPECTRUM = "spectrum.json"
GIF_ZOOM = 4
GIF_FRAME_MS = 1000


def load_targets() -> dict[str, tuple[Target, int]]:
    """Target and its depth cap (`prebake_cap`: exposures per detector and visit or 30-day bin)."""
    payload = json.loads((ROOT / "science" / "targets.json").read_text(encoding="utf-8"))
    return {
        t["id"]: (
            Target(
                ra_deg=t["ra"],
                dec_deg=t["dec"],
                ref_epoch=t["ref_epoch"],
                pmra_masyr=t["pmra"],
                pmdec_masyr=t["pmdec"],
                name=t["name"],
            ),
            int(t["prebake_cap"]),
        )
        for t in payload["targets"]
    }


def write_gif(result: SequenceResult, path: Path) -> None:
    stretch = result.sequence.stretch
    frames = []
    for frame in result.sequence.frames:
        if not frame.id.endswith("-all"):
            continue
        data = result.arrays[frame.id].data
        t = np.clip((np.nan_to_num(data, nan=stretch.vmin) - stretch.vmin) / (stretch.vmax - stretch.vmin), 0, 1)
        gray = (np.flipud(np.arcsinh(t / stretch.a) / np.arcsinh(1 / stretch.a)) * 255).astype(np.uint8)
        img = Image.fromarray(gray, "L")
        frames.append(img.resize((img.width * GIF_ZOOM, img.height * GIF_ZOOM), Image.Resampling.NEAREST))
    if frames:
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=GIF_FRAME_MS, loop=0)


def show_progress(stage: str, done: int, total: int) -> None:
    print(f"\r  {stage} {done}/{total}", end="", flush=True)


def prebake(target_id: str, target: Target, cap: int) -> None:
    started = time.monotonic()
    print(f"{target_id} (cap {cap} per detector and visit):")
    sample = fetch_sample(target, max_per_detector=cap, progress=show_progress)
    print(f"\r  {len(sample.cutouts)} cutouts, {len(sample.failed)} failed, {time.monotonic() - started:.0f} s")
    if sample.failed:
        print("  re-run later to fill the failed exposures (finished cutouts are cached)")
    result = build_sequence(sample.cutouts, target, SequenceParams(), progress=show_progress)
    out = OUT / target_id
    manifest = write_bundle(result, out)
    spectrum = measure_spectrum(sample.cutouts, target)
    (out / SPECTRUM).write_text(spectrum.model_dump_json(indent=1) + "\n", encoding="utf-8")
    write_gif(result, out / "blink.gif")
    size_kb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1024
    print(f"\r  {len(result.sequence.frames)} frames → {manifest.relative_to(ROOT)} ({size_kb:.0f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="ids from science/targets.json (default: all)")
    parser.add_argument("--max-per-detector", type=int, default=None, help="override prebake_cap from targets.json")
    args = parser.parse_args()
    logging.getLogger("astropy").setLevel(logging.ERROR)
    configure_ssl()
    targets = load_targets()
    for target_id in args.targets or list(targets):
        target, cap = targets[target_id]
        prebake(target_id, target, args.max_per_detector or cap)


if __name__ == "__main__":
    main()
