"""Entry point of the science pipeline (Track C).

`build_sequence` is pure and synchronous: it may run in a process pool, so arguments and results must stay
picklable (pass `progress=None` there). Rules: SR-1 … SR-6 in docs/spec.md; output contract: docs/api.md.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from statistics import fmean
from typing import Final

import numpy as np
from astropy.time import Time
from astropy.wcs import WCS

from ..astrometry import position_at
from ..domain import Cutout, FrameArrays, ProgressCallback, SequenceParams, SequenceResult, Target
from ..flags import DEFAULT_FLAG_BITS, stack_mask_bits
from ..grid import make_grid
from ..models import Frame, FrameWarning, PixelPos, SequenceMeta, Stretch
from ..models import Sequence as SequenceModel
from .exposure import GridExposure, to_grid
from .stack import Stack, stack

COVERAGE_WARNING_FRACTION: Final = 0.8
LVF_CHANNELS: Final = 17
MONTH_LENGTH: Final = len("2026-11")
DETECTOR_BANDS_UM: Final = {
    1: (0.75, 1.11),
    2: (1.11, 1.64),
    3: (1.64, 2.42),
    4: (2.42, 3.82),
    5: (3.82, 4.42),
    6: (4.42, 5.0),
}
STRETCH_PERCENTILES: Final = (1.0, 99.7)
STRETCH_ASINH_A: Final = 0.1
_PIPELINE_TAG = re.compile(r"l2b-v\d+")
_SATURATION_BITS: Final = sum(1 << b.bit for b in DEFAULT_FLAG_BITS if b.group == "saturation")


class SequenceError(ValueError):
    pass


def _date(mjd: float) -> str:
    return str(Time(mjd, format="mjd").isot)[:10]


def _expected_px(target: Target, mjd: float, grid_wcs: WCS) -> PixelPos | None:
    if not target.has_proper_motion:
        return None
    ra_deg, dec_deg = position_at(target, mjd)
    x, y = grid_wcs.world_to_pixel_values(ra_deg, dec_deg)
    return PixelPos(x=round(float(x), 2), y=round(float(y), 2))


def _target_saturated(stacked: Stack, expected: PixelPos | None, npix: int) -> bool:
    col = round(expected.x) if expected else npix // 2
    row = round(expected.y) if expected else npix // 2
    if not (0 <= row < npix and 0 <= col < npix):
        return False
    return bool(int(stacked.flags[row, col]) & _SATURATION_BITS)


def _lambda_range(stacked: Stack) -> tuple[float, float]:
    lambdas = stacked.lambdas_um
    if lambdas:
        return round(lambdas[0], 3), round(lambdas[-1], 3)
    metas = [e.cutout.meta for e in stacked.exposures]
    return round(min(m.lambda_min_um for m in metas), 3), round(max(m.lambda_max_um for m in metas), 3)


def _frame(
    frame_id: str, suffix: str, stacked: Stack, target: Target, grid_wcs: WCS, npix: int
) -> tuple[Frame, FrameArrays]:
    mjds = [e.cutout.mjd_avg for e in stacked.exposures]
    mjd_mid = fmean(mjds)
    expected = _expected_px(target, mjd_mid, grid_wcs)
    warnings = (
        [FrameWarning(code="saturated", message="target pixel saturated (OVERFLOW/NONLINEAR)")]
        if _target_saturated(stacked, expected, npix)
        else []
    )
    first, last = _date(min(mjds)), _date(max(mjds))
    frame = Frame(
        id=frame_id,
        kind="visit_stack" if len(stacked.exposures) > 1 or suffix == "all" else "exposure",
        label=f"{first[:MONTH_LENGTH]} · {suffix}",
        mjd_mid=round(mjd_mid, 4),
        date_range=(first, last),
        detectors=sorted({e.cutout.meta.detector for e in stacked.exposures}),
        lambda_um=_lambda_range(stacked),
        n_exposures=len(stacked.exposures),
        data="",
        shape=(npix, npix),
        expected_px=expected,
        warnings=warnings,
    )
    return frame, FrameArrays(data=stacked.data, flags=stacked.flags)


def lvf_channel(detector: int, lambda_um: float) -> int:
    """SPHEREx channels have a constant resolving power within a band, so they are equal steps in log λ."""
    lo, hi = DETECTOR_BANDS_UM[detector]
    position = math.log(lambda_um / lo) / math.log(hi / lo)
    return min(LVF_CHANNELS - 1, max(0, math.floor(position * LVF_CHANNELS)))


def channels_hit(stacked: Stack) -> int:
    return len(
        {
            (e.cutout.meta.detector, lvf_channel(e.cutout.meta.detector, e.lambda_um))
            for e in stacked.exposures
            if np.isfinite(e.lambda_um)
        }
    )


def _lambda_warning(frame: Frame, stacked: Stack, n_detectors: int, best_span: float) -> FrameWarning | None:
    """Absolute: a capped live stack samples few LVF channels even when every visit is capped alike, so comparing
    visits alone would miss it. Relative: a visit whose λ span falls short of the best visit's."""
    expected = LVF_CHANNELS * n_detectors
    hit = channels_hit(stacked)
    if hit < COVERAGE_WARNING_FRACTION * expected:
        return FrameWarning(
            code="incomplete_lambda", message=f"incomplete λ coverage: {hit} of {expected} LVF channels"
        )
    span = frame.lambda_um[1] - frame.lambda_um[0]
    if len(stacked.lambdas_um) > 1 and span < COVERAGE_WARNING_FRACTION * best_span:
        return FrameWarning(
            code="incomplete_lambda", message=f"incomplete λ coverage: {span:.2f} of {best_span:.2f} µm"
        )
    return None


def _coverage_warnings(frames: list[Frame], stacks: dict[str, Stack], params: SequenceParams) -> None:
    """SR-1: flag a visit with < 80 % of the exposures or λ span of the best visit of the same stack type (`D3`,
    `all`, ...; a visit missing whole detectors is compared with the full ones), or a stack that samples < 80 % of
    the LVF channels of its detectors (`all` counts every requested detector)."""
    by_kind: dict[str, list[Frame]] = defaultdict(list)
    for frame in frames:
        by_kind[frame.id.split("-", 1)[1]].append(frame)
    for kind, group in by_kind.items():
        best_n = max(f.n_exposures for f in group)
        best_span = max(f.lambda_um[1] - f.lambda_um[0] for f in group)
        n_detectors = len(set(params.detectors)) if kind == "all" else 1
        for frame in group:
            if frame.n_exposures < COVERAGE_WARNING_FRACTION * best_n:
                frame.warnings.append(
                    FrameWarning(code="few_exposures", message=f"few exposures: {frame.n_exposures} of up to {best_n}")
                )
            if params.mode == "visit_stack" and (
                warning := _lambda_warning(frame, stacks[frame.id], n_detectors, best_span)
            ):
                frame.warnings.append(warning)


def unique_labels(frames: Sequence[Frame]) -> None:
    """Deep-field bins are 30 d long, so two of them can start in the same month: those are named by the day."""
    counts = Counter(frame.label for frame in frames)
    for frame in frames:
        if counts[frame.label] > 1:
            frame.label = frame.date_range[0] + frame.label[MONTH_LENGTH:]


def _stretch(arrays: Sequence[FrameArrays]) -> Stretch:
    values = np.concatenate([a.data[np.isfinite(a.data)] for a in arrays])
    if values.size == 0:
        return Stretch(vmin=0.0, vmax=1.0, a=STRETCH_ASINH_A)
    vmin, vmax = np.percentile(values, STRETCH_PERCENTILES)
    return Stretch(vmin=round(float(vmin), 4), vmax=round(float(max(vmax, vmin + 1e-6)), 4), a=STRETCH_ASINH_A)


def _visits(exposures: Sequence[GridExposure]) -> list[list[GridExposure]]:
    by_visit: dict[str, list[GridExposure]] = defaultdict(list)
    for exposure in exposures:
        by_visit[exposure.cutout.visit_id].append(exposure)
    return sorted(by_visit.values(), key=lambda group: fmean(e.cutout.mjd_avg for e in group))


def build_sequence(
    cutouts: Sequence[Cutout],
    target: Target,
    params: SequenceParams,
    progress: ProgressCallback | None = None,
) -> SequenceResult:
    selected = [c for c in cutouts if c.meta.detector in params.detectors]
    if not selected:
        raise SequenceError("No cutouts for the requested detectors")
    center = position_at(target, fmean(c.mjd_avg for c in selected))
    grid_wcs, grid = make_grid(center[0], center[1], params.fov_arcmin)
    shape = (grid.npix, grid.npix)
    mask_bits = stack_mask_bits(DEFAULT_FLAG_BITS)

    exposures: list[GridExposure] = []
    for done, cutout in enumerate(selected, start=1):
        exposures.append(to_grid(cutout, target, grid_wcs, shape, mask_bits))
        if progress is not None:
            progress("process", done, len(selected))

    frames: list[Frame] = []
    arrays: dict[str, FrameArrays] = {}
    stacks: dict[str, Stack] = {}
    display: list[FrameArrays] = []
    for n, group in enumerate(_visits(exposures), start=1):
        visit = f"v{n}"
        if params.mode == "exposures":
            parts = [(f"{visit}-{e.cutout.meta.key}", f"D{e.cutout.meta.detector}", [e]) for e in group]
        else:
            parts = [
                (f"{visit}-D{d}", f"D{d}", [e for e in group if e.cutout.meta.detector == d])
                for d in sorted({e.cutout.meta.detector for e in group})
            ]
            parts.append((f"{visit}-all", "all", group))
        for frame_id, suffix, members in parts:
            stacks[frame_id] = stack(members)
            frame, frame_arrays = _frame(frame_id, suffix, stacks[frame_id], target, grid_wcs, grid.npix)
            frames.append(frame)
            arrays[frame_id] = frame_arrays
            if suffix == "all" or params.mode == "exposures":
                display.append(frame_arrays)

    _coverage_warnings(frames, stacks, params)
    unique_labels(frames)
    sequence = SequenceModel(
        grid=grid,
        stretch=_stretch(display or list(arrays.values())),
        flag_bits=list(DEFAULT_FLAG_BITS),
        frames=frames,
        meta=SequenceMeta(
            target_name=target.name,
            collections=sorted({c.meta.collection for c in selected}),
            n_exposures_total=len(selected),
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            pipeline_tags=sorted({m.group(0) for c in selected if (m := _PIPELINE_TAG.search(c.meta.access_url))}),
        ),
    )
    return SequenceResult(sequence=sequence, arrays=arrays)
