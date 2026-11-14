"""Validate the motion targets (T-1, T-2, FR-20) and write science/VALIDATION.md with figures.

Usage (from the repo root; run scripts/fetch_sample.py first — cutouts come from cache/raw/):
    uv run --project backend python science/validate.py --max-per-detector 4
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from app.archive.naive import fetch_sample
from app.config import configure_ssl
from app.domain import SequenceParams, SequenceResult
from app.models import Frame
from app.pipeline.measure import Shift, fit_proper_motion, locate_source
from app.pipeline.sequence import build_sequence
from preview import load_target, tile, to_diverging, to_gray

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "science" / "figures"
REPORT = ROOT / "science" / "VALIDATION.md"
CROP_HALF_PX = 20


@dataclass(frozen=True)
class Criteria:
    test_id: str
    pa_deg: float
    pa_tolerance_deg: float
    min_px: float
    max_px: float


MOTION_TARGETS = {
    "barnard": Criteria("T-1", 356.0, 30.0, 1.3, 2.3),
    "eps_ind_b": Criteria("T-2", 122.0, 30.0, 0.7, 1.5),
}


def frame_sets(result: SequenceResult) -> dict[str, list[Frame]]:
    sets: dict[str, list[Frame]] = {}
    for frame in result.sequence.frames:
        sets.setdefault(frame.id.split("-", 1)[1], []).append(frame)
    return sets


def locate(result: SequenceResult, frame: Frame) -> tuple[float, float] | None:
    if frame.expected_px is None:
        return None
    return locate_source(result.arrays[frame.id].data, frame.expected_px.x, frame.expected_px.y)


def pa_error(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def figure(target_id: str, result: SequenceResult, frames: list[Frame]) -> Path:
    seq = result.sequence
    first = frames[0].expected_px
    cx, cy = (round(first.x), round(first.y)) if first else (seq.grid.npix // 2, seq.grid.npix // 2)
    rows, cols = slice(cy - CROP_HALF_PX, cy + CROP_HALF_PX + 1), slice(cx - CROP_HALF_PX, cx + CROP_HALF_PX + 1)
    crops = [result.arrays[f.id].data[rows, cols] for f in frames]
    diff = crops[-1] - crops[0]
    finite = np.abs(diff[np.isfinite(diff)])
    limit = float(np.percentile(finite, 99.5)) if finite.size else 1.0
    tiles = [tile(to_gray(c, seq.stretch.vmin, seq.stretch.vmax), f.label) for c, f in zip(crops, frames, strict=True)]
    tiles.append(tile(to_diverging(diff, limit or 1.0), "last - first"))
    sheet = Image.new("RGB", (sum(t.width for t in tiles), tiles[0].height), "black")
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / f"{target_id}_motion.png"
    sheet.save(path)
    return path


def validate(target_id: str, criteria: Criteria, cap: int) -> list[str]:
    target, entry = load_target(target_id)
    sample = fetch_sample(target, max_per_detector=cap)
    result = build_sequence(sample.cutouts, target, SequenceParams())
    pixscale = result.sequence.grid.pixscale_arcsec
    cat_pmra, cat_pmdec = float(entry["pmra"]), float(entry["pmdec"])  # type: ignore[arg-type]  # JSON numbers
    lines = [
        f"## {criteria.test_id} — {target.name}",
        "",
        f"Sample: {len(sample.cutouts)} cutouts (≤ {cap} per detector and visit), "
        f"{len({f.id.split('-')[0] for f in result.sequence.frames})} visits. "
        f"Catalog PM (SIMBAD): ({cat_pmra:+.0f}, {cat_pmdec:+.0f}) mas/yr.",
        "",
        "| Frames | Epochs | Shift first→last | PA | Measured PM (mas/yr) | Δ/σ vs catalog | Criteria |",
        "|---|---|---|---|---|---|---|",
    ]
    all_frames: list[Frame] = []
    for name, frames in frame_sets(result).items():
        located = [(f, locate(result, f)) for f in frames]
        points = [(f, p) for f, p in located if p is not None]
        if len(points) < 2:
            lines.append(f"| {name} | {len(points)} | — | — | source not found | — | ✗ |")
            continue
        p0, p1 = points[0][1], points[-1][1]
        shift = Shift(p1[0] - p0[0], p1[1] - p0[1], pixscale)
        mjds = [f.mjd_mid for f, _ in points]
        fit = fit_proper_motion(mjds, [p[0] for _, p in points], [p[1] for _, p in points], pixscale)
        err = (
            f" ± ({fit.pmra_err_masyr:.0f}, {fit.pmdec_err_masyr:.0f})"
            if fit.pmra_err_masyr is not None and fit.pmdec_err_masyr is not None
            else ""
        )
        sigma = fit.offset_sigma(cat_pmra, cat_pmdec)
        ok = (
            criteria.min_px <= shift.length_px <= criteria.max_px
            and pa_error(shift.position_angle_deg, criteria.pa_deg) <= criteria.pa_tolerance_deg
        )
        lines.append(
            f"| {name} | {fit.n_epochs} | {shift.length_px:.2f} px ({shift.length_arcsec:.1f}″) | "
            f"{shift.position_angle_deg:.0f}° | ({fit.pmra_masyr:+.0f}, {fit.pmdec_masyr:+.0f}){err} | "
            f"{'—' if sigma is None else f'{sigma:.1f}'} | {'✓' if ok else '✗'} |"
        )
        if name == "all":
            all_frames = frames
    fig = figure(target_id, result, all_frames) if all_frames else None
    lines += [
        "",
        f"Criteria ({criteria.test_id}): shift {criteria.min_px}–{criteria.max_px} px toward PA "
        f"{criteria.pa_deg:.0f}° ± {criteria.pa_tolerance_deg:.0f}° (docs/spec.md §6.2).",
    ]
    if fig is not None:
        lines += ["", f"![{target.name}: all-detector visit stacks and difference](figures/{fig.name})"]
    return [*lines, ""]


CAVEATS = """## Caveats

- Development sample, not full depth: λ coverage per visit is partial, so some frames carry "incomplete λ
  coverage" warnings. Numbers will be refreshed from the full-depth prebake.
- Positions come from a 2D Gaussian fit with masked pixels excluded (Barnard's saturated core is left out).
  Flux-weighted centroids lock onto pixel centres of the undersampled PSF and shortened the shifts by 10-20 %.
- Proper-motion errors come from the scatter of 3–4 epochs around a line; parallax (0.27–0.55″) is ignored
  (SR-3) and contributes to that scatter, so Δ/σ can exceed 3 even when the motion is clearly right.
- ε Indi A (V 4.7) lies 6.7′ west of ε Indi B: its halo leaves residuals at the western edge of the difference.
- D1 (0.75–1.1 µm) barely detects the T dwarfs ε Indi Ba/Bb, so its shift is noise-dominated.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-per-detector", type=int, default=4)
    args = parser.parse_args()
    logging.getLogger("astropy").setLevel(logging.ERROR)
    configure_ssl()
    lines = [
        "# Validation of the test targets",
        "",
        f"Generated by `science/validate.py` on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Acceptance criteria: "
        "`docs/spec.md` §6.2. Status: **draft** — motion targets only (T-1, T-2); T-3 … T-5 follow.",
        "",
    ]
    for target_id, criteria in MOTION_TARGETS.items():
        lines += validate(target_id, criteria, args.max_per_detector)
    lines.append(CAVEATS)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
