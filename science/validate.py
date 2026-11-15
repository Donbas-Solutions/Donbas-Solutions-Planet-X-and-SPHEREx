"""Validate the five test targets (docs/spec.md §6.2: T-1 … T-5, FR-16, FR-20) → science/VALIDATION.md + figures.

Usage (from the repo root, after scripts/prebake.py — same fetcher and depth, so cutouts come from cache/raw/):
    uv run --project backend python science/validate.py                 # all targets
    uv run --project backend python science/validate.py barnard eps_ind_b --max-per-detector 4
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import math
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

from app.archive.fetch import FetchResult
from app.archive.http import ArchiveError
from app.config import configure_ssl
from app.domain import SequenceParams, SequenceResult, Target
from app.models import Frame, SpectrumPoint
from app.pipeline.measure import Shift, fit_proper_motion, locate_source
from app.pipeline.photometry import measure_spectrum
from app.pipeline.sequence import build_sequence
from app.pipeline.variability import matched_changes, strongest_per_detector
from preview import load_target, tile, to_diverging, to_gray

ROOT = Path(__file__).resolve().parents[1]
# Same plan, window and cache as the bundles: reuse prebake's fetcher instead of a second copy of it.
sys.path.insert(0, str(ROOT / "scripts"))
from prebake import fetch_target, recorded_exposures  # noqa: E402

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
# FR-16 acceptance star: unsaturated (G 13.9), slow (5 mas/yr), 2.5′ east of ε Indi B, no Gaia star within 40″
# brighter than G + 4. Its IRSA Spectrophotometry Tool table (Tractor forced PSF photometry, point source, DR1+QR3
# wide, run on 2026-11-15) is kept in science/reference/.
FR16_STAR = Target(
    ra_deg=331.1718829420257,
    dec_deg=-56.79333744618183,
    ref_epoch=2016.0,
    pmra_masyr=-0.21665867,
    pmdec_masyr=5.330207,
    name="Gaia DR3 6412593435166417536",
)
IRSA_REFERENCE = ROOT / "science" / "reference" / "irsa_spectrophotometry_gaia6412593435166417536.csv"
FR16_RATIO_RANGE = (0.8, 1.25)
# The tool's FLAGS bits that make a point unusable (its help page): 7 DICHROIC, 33 FIT_ERROR.
IRSA_UNUSABLE_FLAGS = (1 << 7) | (1 << 33)
# Both tables give each exposure's MJD-AVG; consecutive exposures are ~1.5 min (0.001 d) apart.
MJD_MATCH_D = 2e-4
# WISE W2 (4.6 µm) Vega zero point (Jarrett et al. 2011) and WISE 0855's W2 magnitude.
W2_ZERO_POINT_JY, WISE0855_W2_MAG = 171.787, 14.0
MWIR_MIN_UM = 3.82
MOTION_PA_TOLERANCE_DEG = 30.0
MJD_ZERO = datetime(1858, 11, 17, tzinfo=UTC)


@dataclass(frozen=True)
class Data:
    target: Target
    entry: dict[str, object]
    cap: int
    sample: FetchResult
    result: SequenceResult
    points: list[SpectrumPoint]


def load(target_id: str, cap_override: int | None, *, recorded_sia: bool = False) -> Data:
    target, entry = load_target(target_id)
    cap = cap_override or int(str(entry["prebake_cap"]))
    recorded = recorded_exposures(target_id) if recorded_sia else None
    sample = asyncio.run(fetch_target(target, cap, recorded))
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
        "2MASS (epoch 1999) is an independent sanity check; the acceptance test against IRSA's Spectrophotometry Tool "
        "follows. The SPHEREx points sample narrow LVF channels while 2MASS integrates the whole band, so deep T-dwarf "
        "absorption inside a band lowers the SPHEREx median.",
        "",
    ]
    return lines


@dataclass(frozen=True)
class IrsaPoint:
    mjd: float
    detector: int
    flags: int
    lambda_um: float
    flux_ujy: float


def irsa_reference() -> list[IrsaPoint]:
    with IRSA_REFERENCE.open(encoding="utf-8", newline="") as table:
        return [
            IrsaPoint(
                mjd=float(row["mjd"]),
                detector=int(row["det_id"]),
                flags=int(row["flags"]),
                lambda_um=float(row["lambda_um"]),
                flux_ujy=float(row["flux_ujy"]),
            )
            for row in csv.DictReader(table)
        ]


@dataclass(frozen=True)
class FluxPair:
    detector: int
    ours_ujy: float
    irsa_ujy: float


def matched_irsa(points: Sequence[SpectrumPoint], reference: Sequence[IrsaPoint]) -> list[FluxPair]:
    """Our usable points with the tool's flux of the same exposure (detector and MJD), unusable tool rows dropped."""
    pairs = []
    for point in points:
        if point.flux_ujy is None:
            continue
        same = [r for r in reference if r.detector == point.detector and abs(r.mjd - point.mjd) < MJD_MATCH_D]
        if len(same) == 1 and not same[0].flags & IRSA_UNUSABLE_FLAGS and same[0].flux_ujy > 0:
            pairs.append(FluxPair(point.detector, point.flux_ujy, same[0].flux_ujy))
    return pairs


def irsa_section(data: Data) -> list[str]:
    points = measure_spectrum(data.sample.cutouts, FR16_STAR).points
    usable = [p for p in points if p.flux_ujy is not None]
    pairs = matched_irsa(points, irsa_reference())
    ratios = np.array([p.ours_ujy / p.irsa_ujy for p in pairs])
    median = float(np.median(ratios))
    low, high = FR16_RATIO_RANGE
    verdict = "✓" if low <= median <= high else "✗"
    lines = [
        f"## FR-16 — {FR16_STAR.name} vs IRSA's Spectrophotometry Tool",
        "",
        f"Unsaturated field star (G 13.9) 2.5′ east of ε Indi B, measured by our forced aperture photometry on the "
        f"same cutouts: {len(points)} exposures, {len(usable)} usable. Matched to the tool's table "
        f"(`{IRSA_REFERENCE.relative_to(ROOT).as_posix()}`) by detector and MJD: {len(pairs)} pairs.",
        "",
        f"**Median ratio ours / IRSA = {median:.3f}** (16–84 %: {np.percentile(ratios, 16):.3f}–"
        f"{np.percentile(ratios, 84):.3f}); acceptance {low}–{high}: {verdict}",
        "",
        "| Detector | Pairs | Ours, median (µJy) | IRSA, median (µJy) | Median ratio |",
        "|---|---|---|---|---|",
    ]
    for detector in range(1, 7):
        selected = [p for p in pairs if p.detector == detector]
        if not selected:
            continue
        ours = np.median([p.ours_ujy for p in selected])
        theirs = np.median([p.irsa_ujy for p in selected])
        ratio = np.median([p.ours_ujy / p.irsa_ujy for p in selected])
        lines.append(f"| D{detector} | {len(selected)} | {ours:.0f} | {theirs:.0f} | {ratio:.3f} |")
    lines += [
        "",
        "The tool fits the PSF (The Tractor) with a simultaneous local background and uses the per-pixel solid angle "
        "map; we sum a 3-px aperture after subtracting ZODI and an annulus median, with the solid angle from the WCS "
        "and no aperture correction.",
        "",
    ]
    return lines


def motion_check(data: Data, suffix: str) -> tuple[Shift, Shift] | None:
    """Measured and expected first→last shift of the source in the `suffix` frames (e.g. `D6`)."""
    marked = [(f, f.expected_px) for f in data.result.sequence.frames if f.id.endswith(f"-{suffix}")]
    frames = [(f, e) for f, e in marked if e is not None]
    if len(frames) < 2:
        return None
    (first, e0), (last, e1) = frames[0], frames[-1]
    a = locate_source(data.result.arrays[first.id].data, e0.x, e0.y)
    b = locate_source(data.result.arrays[last.id].data, e1.x, e1.y)
    if a is None or b is None:
        return None
    pixscale = data.result.sequence.grid.pixscale_arcsec
    expected = Shift(e1.x - e0.x, e1.y - e0.y, pixscale)
    return Shift(b[0] - a[0], b[1] - a[1], pixscale), expected


def wise0855_section(data: Data) -> list[str]:
    """WISE 0855 is invisible below ~3 µm (J ≈ 25), so flux there means a field source shares the aperture."""
    lines = [*header("T-3", data)]
    expected_ujy = W2_ZERO_POINT_JY * 10 ** (-WISE0855_W2_MAG / 2.5) * 1e6
    rows = [
        ("λ < 1.6 µm (D1–D2)", 0.0, 1.6),
        ("1.6–3.8 µm (D3–D4)", 1.6, MWIR_MIN_UM),
        ("λ ≥ 3.8 µm (D5–D6)", MWIR_MIN_UM, 9.9),
    ]
    fluxes: dict[str, tuple[float, float] | None] = {}
    lines += [
        "Forced aperture photometry (r = 3 px = 18.6″) at the position propagated from SIMBAD J2000 + proper motion "
        "(the challenge coordinates are epoch ≈2010.5).",
        "",
        "| Wavelengths | Exposures | Flux (µJy) | S/N |",
        "|---|---|---|---|",
    ]
    for label, lo, hi in rows:
        points = [p for p in data.points if lo <= p.lambda_um < hi]
        fluxes[label] = mean = weighted_mean(points)
        cell = f"{mean[0]:.0f} ± {mean[1]:.0f} | {mean[0] / mean[1]:.1f}" if mean else "— | —"
        lines.append(f"| {label} | {len(points)} | {cell} |")

    short = fluxes[rows[0][0]]
    contaminated = short is not None and short[0] / short[1] >= DETECTION_SIGMA
    lines += ["", "| Frames | Measured shift | Expected shift (proper motion) |", "|---|---|---|"]
    moving: list[str] = []
    for suffix in ("D5", "D6", "all"):
        check = motion_check(data, suffix)
        if check is None:
            lines.append(f"| {suffix} | source not found | — |")
            continue
        measured, expected = check
        lines.append(
            f"| {suffix} | {measured.length_px:.2f} px @ PA {measured.position_angle_deg:.0f}° | "
            f"{expected.length_px:.2f} px @ PA {expected.position_angle_deg:.0f}° |"
        )
        along = pa_error(measured.position_angle_deg, expected.position_angle_deg) <= MOTION_PA_TOLERANCE_DEG
        if suffix != "all" and along and measured.length_px >= 0.5 * expected.length_px:
            moving.append(suffix)

    mwir = fluxes[rows[2][0]]
    verdict = []
    if moving:
        verdict.append(
            f"**Motion of WISE 0855 detected** in {' and '.join(moving)}: the source shifts in the predicted "
            "direction where WISE 0855 is bright and the field source is faint."
        )
    if contaminated and short is not None and mwir is not None:
        verdict.append(
            f"**The flux is contaminated**: {short[0]:.0f} µJy at λ < 1.6 µm (S/N {short[0] / short[1]:.0f}) can only "
            f"come from a field source in the aperture, so {mwir[0]:.0f} ± {mwir[1]:.0f} µJy at λ ≥ 3.8 µm is an "
            "upper bound for WISE 0855, not its flux. The blend also shortens the measured shift."
        )
    elif mwir is not None:
        snr = mwir[0] / mwir[1]
        verdict.append(
            f"D5–D6 flux {mwir[0]:.0f} ± {mwir[1]:.0f} µJy (S/N {snr:.1f})"
            + (
                ""
                if snr >= DETECTION_SIGMA
                else f"; {DETECTION_SIGMA:.0f}σ upper limit {DETECTION_SIGMA * mwir[1]:.0f} µJy"
            )
            + "."
        )
    for paragraph in verdict:
        lines += ["", paragraph]
    lines += [
        "",
        f"For reference, WISE W2 = {WISE0855_W2_MAG} corresponds to ≈ {expected_ujy:.0f} µJy at 4.6 µm.",
    ]
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
        "",
        *matched_lambda_lines(data.points),
    ]
    return [*lines, ""]


def matched_lambda_lines(points: Sequence[SpectrumPoint]) -> list[str]:
    """The visit pair with the largest change at matched λ per detector (`pipeline.variability`)."""
    best = strongest_per_detector(matched_changes(points))
    first_mjd: dict[str, float] = {}
    for p in points:
        first_mjd[p.visit] = min(first_mjd.get(p.visit, p.mjd), p.mjd)
    month = {v: f"{MJD_ZERO + timedelta(days=mjd):%Y-%m}" for v, mjd in first_mjd.items()}
    if not best:
        return [
            "Matched λ: no comparison — no two visits have measured (unsaturated, unmasked) exposures within one "
            "LVF channel."
        ]
    lines = [
        "Matched λ: each exposure is paired with the nearest-λ exposure of another visit (≤ 1 LVF channel apart); "
        "errors include a 5 % floor per exposure and the local spectral slope times the λ offset. The strongest "
        "visit pair per detector (the largest of several looks, so judge it against 5σ):",
        "",
        "| Detector | Visits | Later / earlier | Significance (σ) | Pairs | λ (µm) |",
        "|---|---|---|---|---|---|",
    ]
    for detector, change in sorted(best.items()):
        lo, hi = change.lambda_um
        lines.append(
            f"| D{detector} | {month[change.earlier]} → {month[change.later]} | {change.ratio:.2f} | "
            f"{change.significance:.1f} | {change.n_pairs} | {lo:.3f}–{hi:.3f} |"
        )
    return lines


CAVEATS = """## Caveats

- Positions come from a 2D Gaussian fit with masked pixels excluded (Barnard's saturated core is left out).
  Flux-weighted centroids lock onto pixel centres of the undersampled PSF and shortened the shifts by 10-20 %.
- Proper-motion errors come from the scatter of 3–4 epochs around a line; parallax (0.27–0.55″) is ignored
  (SR-3) and contributes to that scatter. With 3 epochs the error rests on one degree of freedom and can be
  accidentally tiny (Barnard D2: σ = 24 mas/yr → Δ/σ = 24 although the shift and PA agree); trust the 4-epoch
  ε Indi B errors more.
- ε Indi B D4 misses the last visit (no D4 exposures in it), so its first→last baseline and shift are shorter;
  the 0.7 px threshold assumes the full baseline.
- ε Indi A (V 4.7) lies 6.7′ west of ε Indi B: its halo leaves residuals at the western edge of the difference.
- D1 (0.75–1.1 µm) barely detects the T dwarfs ε Indi Ba/Bb, so its shift is noise-dominated.
- Photometry uses the pixel solid angle from the WCS; IRSA's per-pixel SAPM map would refine it by the small
  distortion term. Aperture r = 3 px without an aperture correction.
"""

Section = Callable[[Data], list[str]]
HEADINGS = {
    "barnard": ("T-1",),
    "eps_ind_b": ("T-2", "FR-16"),
    "wise0855": ("T-3",),
    "rw_aur": ("T-4",),
    "r_dra": ("T-5",),
}
SECTIONS: dict[str, list[Section]] = {
    "barnard": [lambda d: motion_section("barnard", MOTION_TARGETS["barnard"], d)],
    "eps_ind_b": [
        lambda d: motion_section("eps_ind_b", MOTION_TARGETS["eps_ind_b"], d),
        spectrum_section,
        irsa_section,
    ],
    "wise0855": [wise0855_section],
    "rw_aur": [lambda d: light_curve_section("T-4", d, "T Tauri star with irregular dimming.")],
    "r_dra": [lambda d: light_curve_section("T-5", d, "Mira variable in the deep field; 30-day bins.")],
}


def previous_sections(target_id: str) -> list[str]:
    """This target's sections from the last report, so one archive outage does not wipe the other targets' run."""
    if not REPORT.exists():
        return []
    kept: list[str] = []
    is_kept = False
    for line in REPORT.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            is_kept = line.removeprefix("## ").startswith(HEADINGS[target_id])
        if is_kept:
            kept.append(line)
    return kept


def load_or_none(target_id: str, cap_override: int | None, *, recorded_sia: bool = False) -> Data | None:
    """None when IRSA fails for this target (the fetcher's task group wraps the error)."""
    try:
        return load(target_id, cap_override, recorded_sia=recorded_sia)
    except ArchiveError as exc:
        print(f"\n{target_id}: archive failed ({exc})")
    except ExceptionGroup as group:
        if group.subgroup(ArchiveError) is None:
            raise
        print(f"\n{target_id}: archive failed ({group.exceptions[0]})")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="ids from science/targets.json (default: all)")
    parser.add_argument("--max-per-detector", type=int, default=None, help="override prebake_cap (dev samples)")
    parser.add_argument(
        "--recorded-sia", action="store_true", help="exposure lists from backend/tests/fixtures/sia/, as in prebake"
    )
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
        data = load_or_none(target_id, args.max_per_detector, recorded_sia=args.recorded_sia)
        if data is None:
            kept = previous_sections(target_id)
            print(f"{target_id}: kept {len(kept)} lines of the last report")
            lines += kept
            continue
        for section in SECTIONS[target_id]:
            lines += section(data)
        print(f"validated {target_id}")
    lines.append(CAVEATS)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
