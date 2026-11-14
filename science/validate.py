"""Validate the five test targets (docs/spec.md §6.2: T-1 … T-5, FR-16, FR-20) → science/VALIDATION.md + figures.

Usage (from the repo root, after scripts/prebake.py — it uses the same depth, so cutouts come from cache/raw/):
    uv run --project backend python science/validate.py                 # all targets
    uv run --project backend python science/validate.py barnard eps_ind_b --max-per-detector 4
"""

from __future__ import annotations

import argparse
import logging
import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean

import numpy as np
from PIL import Image

from app.archive.naive import Sample, fetch_sample
from app.config import configure_ssl
from app.domain import SequenceParams, SequenceResult, Target
from app.models import Frame, SpectrumPoint
from app.pipeline.measure import Shift, fit_proper_motion, locate_source
from app.pipeline.photometry import measure_spectrum
from app.pipeline.sequence import build_sequence
from preview import load_target, tile, to_diverging, to_gray

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "science" / "figures"
REPORT = ROOT / "science" / "VALIDATION.md"
CROP_HALF_PX = 20
DETECTION_SIGMA = 5.0


@dataclass(frozen=True)
class Criteria:
    test_id: str
    pa_deg: float
    pa_tolerance_deg: float
    min_px: float
    max_px: float


@dataclass(frozen=True)
class Band:
    name: str
    lo_um: float
    hi_um: float
    zero_point_jy: float


MOTION_TARGETS = {
    "barnard": Criteria("T-1", 356.0, 30.0, 1.3, 2.3),
    "eps_ind_b": Criteria("T-2", 122.0, 30.0, 0.7, 1.5),
}
# 2MASS bands and Vega zero points (Cohen et al. 2003); the windows select SPHEREx points inside each band.
TWO_MASS = (Band("J", 1.15, 1.32, 1594.0), Band("H", 1.55, 1.77, 1024.0), Band("Ks", 2.03, 2.30, 666.7))
EPS_IND_B_2MASS_MAG = {"J": 11.91, "H": 11.31, "Ks": 11.21}
# WISE W2 (4.6 µm) Vega zero point (Jarrett et al. 2011) and WISE 0855's W2 magnitude.
W2_ZERO_POINT_JY, WISE0855_W2_MAG = 171.787, 14.0
MWIR_MIN_UM = 3.82


@dataclass(frozen=True)
class Data:
    target: Target
    entry: dict[str, object]
    cap: int
    sample: Sample
    result: SequenceResult
    points: list[SpectrumPoint]


def load(target_id: str, cap_override: int | None) -> Data:
    target, entry = load_target(target_id)
    cap = cap_override or int(str(entry["prebake_cap"]))
    sample = fetch_sample(target, max_per_detector=cap)
    result = build_sequence(sample.cutouts, target, SequenceParams())
    points = measure_spectrum(sample.cutouts, target).points
    return Data(target, entry, cap, sample, result, points)


def header(test_id: str, data: Data) -> list[str]:
    visits = len({f.id.split("-")[0] for f in data.result.sequence.frames})
    failed = f", {len(data.sample.failed)} failed downloads" if data.sample.failed else ""
    return [
        f"## {test_id} — {data.target.name}",
        "",
        f"Data: {len(data.sample.cutouts)} cutouts (≤ {data.cap} per detector and visit or bin), {visits} "
        f"visits/bins{failed}.",
        "",
    ]


def frame_sets(result: SequenceResult) -> dict[str, list[Frame]]:
    sets: dict[str, list[Frame]] = {}
    for frame in result.sequence.frames:
        sets.setdefault(frame.id.split("-", 1)[1], []).append(frame)
    return sets


def pa_error(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def weighted_mean(points: Sequence[SpectrumPoint]) -> tuple[float, float] | None:
    """Inverse-variance mean flux and its error (µJy) of the usable points; None if there are none."""
    usable = [(p.flux_ujy, p.err_ujy) for p in points if p.flux_ujy is not None and p.err_ujy]
    if not usable:
        return None
    weights = [1 / e**2 for _, e in usable]
    return sum(f * w for (f, _), w in zip(usable, weights, strict=True)) / sum(weights), 1 / math.sqrt(sum(weights))


def motion_figure(target_id: str, result: SequenceResult, frames: list[Frame]) -> Path:
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


def motion_section(target_id: str, criteria: Criteria, data: Data) -> list[str]:
    pixscale = data.result.sequence.grid.pixscale_arcsec
    cat_pmra, cat_pmdec = float(data.target.pmra_masyr or 0), float(data.target.pmdec_masyr or 0)
    lines = [
        *header(criteria.test_id, data),
        f"Catalog proper motion (SIMBAD): ({cat_pmra:+.0f}, {cat_pmdec:+.0f}) mas/yr.",
        "",
        "| Frames | Epochs | Shift first→last | PA | Measured PM (mas/yr) | Δ/σ vs catalog | Criteria |",
        "|---|---|---|---|---|---|---|",
    ]
    all_frames: list[Frame] = []
    for name, frames in frame_sets(data.result).items():
        located = [
            (f, locate_source(data.result.arrays[f.id].data, f.expected_px.x, f.expected_px.y))
            for f in frames
            if f.expected_px is not None
        ]
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
    lines += [
        "",
        f"Criteria ({criteria.test_id}): shift {criteria.min_px}–{criteria.max_px} px toward PA "
        f"{criteria.pa_deg:.0f}° ± {criteria.pa_tolerance_deg:.0f}° (docs/spec.md §6.2).",
    ]
    if all_frames:
        fig = motion_figure(target_id, data.result, all_frames)
        lines += ["", f"![{data.target.name}: all-detector visit stacks and difference](figures/{fig.name})"]
    return [*lines, ""]


def spectrum_section(data: Data) -> list[str]:
    measured = [p for p in data.points if p.flux_ujy is not None]
    lines = [
        "## FR-16 — spectrum of ε Indi B vs 2MASS",
        "",
        f"{len(data.points)} exposures measured by forced aperture photometry (r = 3 px) at the propagated position; "
        f"{len(measured)} usable, {sum(p.saturated for p in data.points)} saturated.",
        "",
        "| 2MASS band | 2MASS (mJy) | SPHEREx median in band (mJy) | Points | Ratio |",
        "|---|---|---|---|---|",
    ]
    for band in TWO_MASS:
        reference = band.zero_point_jy * 10 ** (-EPS_IND_B_2MASS_MAG[band.name] / 2.5) * 1000
        in_band = [p for p in measured if band.lo_um <= p.lambda_um < band.hi_um]
        inside = [p.flux_ujy / 1000 for p in in_band if p.flux_ujy is not None]
        if inside:
            median = float(np.median(inside))
            lines.append(f"| {band.name} | {reference:.1f} | {median:.1f} | {len(inside)} | {median / reference:.2f} |")
        else:
            lines.append(f"| {band.name} | {reference:.1f} | — | 0 | — |")
    lines += [
        "",
        "Acceptance (FR-16) asks for a ratio within 0.8–1.25 against IRSA's Spectrophotometry Tool; 2MASS (epoch 1999) "
        "is an independent sanity check, not that test. The SPHEREx points sample narrow LVF channels while 2MASS "
        "integrates the whole band, so deep T-dwarf absorption inside a band lowers the SPHEREx median.",
        "",
    ]
    return lines


def wise0855_section(data: Data) -> list[str]:
    mwir = [p for p in data.points if p.lambda_um >= MWIR_MIN_UM]
    expected_ujy = W2_ZERO_POINT_JY * 10 ** (-WISE0855_W2_MAG / 2.5) * 1e6
    lines = [*header("T-3", data)]
    combined = weighted_mean(mwir)
    if combined is None:
        lines.append("No usable D5–D6 photometry at the expected position.")
        return [*lines, ""]
    flux, err = combined
    snr = flux / err
    verdict = (
        f"**detected** at S/N = {snr:.1f}"
        if snr >= DETECTION_SIGMA
        else f"**not detected** (S/N = {snr:.1f}); {DETECTION_SIGMA:.0f}σ upper limit = {DETECTION_SIGMA * err:.0f} µJy"
    )
    by_visit = defaultdict(list)
    for p in mwir:
        by_visit[p.visit].append(p)
    lines += [
        f"Forced aperture photometry at the position propagated from SIMBAD J2000 + proper motion (the challenge "
        f"coordinates are epoch ≈2010.5). {len(mwir)} exposures at λ ≥ {MWIR_MIN_UM} µm (D5–D6) combined by inverse "
        f"variance: {flux:.0f} ± {err:.0f} µJy → {verdict}. For reference, WISE W2 = {WISE0855_W2_MAG} corresponds "
        f"to ≈ {expected_ujy:.0f} µJy at 4.6 µm.",
        "",
        "| Visit | Exposures | Flux (µJy) | S/N |",
        "|---|---|---|---|",
    ]
    for visit, points in sorted(by_visit.items(), key=lambda kv: fmean(p.mjd for p in kv[1])):
        mean = weighted_mean(points)
        cell = f"{mean[0]:.0f} ± {mean[1]:.0f} | {mean[0] / mean[1]:.1f}" if mean else "— | —"
        lines.append(f"| {visit} | {len(points)} | {cell} |")
    return [*lines, ""]


def light_curve_section(test_id: str, data: Data, note: str) -> list[str]:
    lines = [*header(test_id, data)]
    saturated = sum(p.saturated for p in data.points)
    lines += [
        f"{len(data.points)} exposures measured; {saturated} saturated (reported as saturated, no flux). {note}",
        "",
        "| Detector | Visits with flux | Min (mJy) | Max (mJy) | Max/min | Significance (σ) | Saturated points |",
        "|---|---|---|---|---|---|---|",
    ]
    by_detector: dict[int, dict[str, list[SpectrumPoint]]] = defaultdict(lambda: defaultdict(list))
    for p in data.points:
        by_detector[p.detector][p.visit].append(p)
    for detector in sorted(by_detector):
        visits = by_detector[detector]
        means = [m for m in (weighted_mean(points) for points in visits.values()) if m is not None]
        n_sat = sum(p.saturated for points in visits.values() for p in points)
        if len(means) < 2:
            lines.append(f"| D{detector} | {len(means)} | — | — | — | — | {n_sat} |")
            continue
        low, high = min(means), max(means)
        significance = (high[0] - low[0]) / math.hypot(high[1], low[1])
        lines.append(
            f"| D{detector} | {len(means)} | {low[0] / 1000:.2f} | {high[0] / 1000:.2f} | {high[0] / low[0]:.2f} | "
            f"{significance:.0f} | {n_sat} |"
        )
    lines += [
        "",
        "Fluxes are per detector, averaged over each visit's exposures; the LVF wavelength differs between "
        "exposures, so changes in λ coverage between visits add to the apparent variability.",
    ]
    return [*lines, ""]


CAVEATS = """## Caveats

- Positions come from a 2D Gaussian fit with masked pixels excluded (Barnard's saturated core is left out).
  Flux-weighted centroids lock onto pixel centres of the undersampled PSF and shortened the shifts by 10-20 %.
- Proper-motion errors come from the scatter of 3–4 epochs around a line; parallax (0.27–0.55″) is ignored
  (SR-3) and contributes to that scatter.
- ε Indi A (V 4.7) lies 6.7′ west of ε Indi B: its halo leaves residuals at the western edge of the difference.
- D1 (0.75–1.1 µm) barely detects the T dwarfs ε Indi Ba/Bb, so its shift is noise-dominated.
- Photometry uses the pixel solid angle from the WCS; IRSA's per-pixel SAPM map would refine it by the small
  distortion term. Aperture r = 3 px without an aperture correction.
"""

Section = Callable[[Data], list[str]]
SECTIONS: dict[str, list[Section]] = {
    "barnard": [lambda d: motion_section("barnard", MOTION_TARGETS["barnard"], d)],
    "eps_ind_b": [lambda d: motion_section("eps_ind_b", MOTION_TARGETS["eps_ind_b"], d), spectrum_section],
    "wise0855": [wise0855_section],
    "rw_aur": [lambda d: light_curve_section("T-4", d, "T Tauri star with irregular dimming.")],
    "r_dra": [lambda d: light_curve_section("T-5", d, "Mira variable in the deep field; 30-day bins.")],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="ids from science/targets.json (default: all)")
    parser.add_argument("--max-per-detector", type=int, default=None, help="override prebake_cap (dev samples)")
    args = parser.parse_args()
    logging.getLogger("astropy").setLevel(logging.ERROR)
    configure_ssl()
    lines = [
        "# Validation of the test targets",
        "",
        f"Generated by `science/validate.py` on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Acceptance criteria: "
        "`docs/spec.md` §6.2.",
        "",
    ]
    for target_id in args.targets or list(SECTIONS):
        data = load(target_id, args.max_per_detector)
        for section in SECTIONS[target_id]:
            lines += section(data)
        print(f"validated {target_id}")
    lines.append(CAVEATS)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
