"""Download a development sample of real SPHEREx cutouts (EPSF stripped) into cache/raw/ with the naive fetcher.

Usage (from the repo root):
    uv run --project backend python scripts/fetch_sample.py barnard eps_ind_b --max-per-detector 4

Each cutout is ~4 MB to download (~10 KB-0.3 MB on disk after stripping). The cap leaves part of the LVF band
uncovered (SR-1): samples are for developing the pipeline, not for published sequences.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from app.archive.naive import fetch_sample
from app.config import configure_ssl
from app.domain import Cutout, Target

TARGETS_FILE = Path(__file__).resolve().parents[1] / "science" / "targets.json"


def load_targets() -> dict[str, Target]:
    payload = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    return {
        t["id"]: Target(
            ra_deg=t["ra"],
            dec_deg=t["dec"],
            ref_epoch=t["ref_epoch"],
            pmra_masyr=t["pmra"],
            pmdec_masyr=t["pmdec"],
            name=t["name"],
        )
        for t in payload["targets"]
    }


def show_progress(stage: str, done: int, total: int) -> None:
    print(f"\r  {stage} {done}/{total}", end="", flush=True)


def summarize(cutouts: list[Cutout]) -> None:
    by_visit: dict[str, list[Cutout]] = defaultdict(list)
    for cutout in cutouts:
        by_visit[cutout.visit_id].append(cutout)
    for visit_id, items in by_visit.items():
        detectors = sorted({c.meta.detector for c in items})
        centre_lambda = [
            float(c.wavelength_um[c.wavelength_um.shape[0] // 2, c.wavelength_um.shape[1] // 2]) for c in items
        ]
        mjds = [c.mjd_avg for c in items]
        print(
            f"  {visit_id}: {len(items):3d} cutouts, MJD {min(mjds):.1f}-{max(mjds):.1f}, "
            f"detectors {detectors}, λ at centre {min(centre_lambda):.2f}-{max(centre_lambda):.2f} µm, "
            f"shape {items[0].image.shape}, NaN {np.mean([np.isnan(c.image).mean() for c in items]):.1%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="+", help="ids from science/targets.json, e.g. barnard eps_ind_b")
    parser.add_argument("--max-per-detector", type=int, default=4, help="cap per detector and visit (default 4)")
    parser.add_argument("--fov", type=float, default=10.0, help="field of view in arcmin (default 10)")
    args = parser.parse_args()

    configure_ssl()
    targets = load_targets()
    for target_id in args.targets:
        print(f"{target_id}:")
        started = time.monotonic()
        sample = fetch_sample(
            targets[target_id], fov_arcmin=args.fov, max_per_detector=args.max_per_detector, progress=show_progress
        )
        print(f"\r  {len(sample.cutouts)} cutouts in {time.monotonic() - started:.0f} s, {len(sample.failed)} failed")
        for meta in sample.failed:
            print(f"  failed: {meta.key} (re-run to retry; finished cutouts are cached)")
        summarize(sample.cutouts)


if __name__ == "__main__":
    main()
