"""Generate a synthetic sequence bundle in frontend/public/mock/ (contract: docs/api.md).

Run from the repo root with the backend venv:  python scripts/make_mock.py

Scene (3 visits x detectors D1, D5, all):
  * ~25 static stars with per-star colors (brightness differs between detectors, not visits)
  * a cold "brown dwarf" mover: faint in D1, bright in D5, moves ~1.7 px north over 3 visits
  * a variable star: x1.0, x0.4, x1.3
  * a saturated star: core = NaN with OVERFLOW/NONLINEAR flags, ghost (not masked) in visit 2
  * a snowball in visit 2 / D1 (masked: NaN + SNOWBALL flag)
  * SOURCE flag on all star pixels (informational, never masked)

spectrum.json (linked from meta.spectrum): the mover's spectrum, 3 visits x 6 detectors x 17 LVF channels, shaped
like a cold T/Y dwarf (faint at 1 µm, CH4 absorption at 3.3 µm, peak near 4.3 µm). Two v1 points are marked
saturated and one v2 point carries SNOWBALL only to exercise the UI: a real dwarf this faint never saturates.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
from astropy.time import Time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.flags import DEFAULT_FLAG_BITS  # noqa: E402
from app.grid import make_grid  # noqa: E402
from app.models import (  # noqa: E402
    Frame,
    FrameWarning,
    PixelPos,
    Sequence,
    SequenceMeta,
    Spectrum,
    SpectrumPoint,
    Stretch,
)

OUT = ROOT / "frontend" / "public" / "mock"
BIT = {b.name: 1 << b.bit for b in DEFAULT_FLAG_BITS}
PSF_SIGMA = 0.75  # px: SPHEREx PSF is undersampled
RNG = np.random.default_rng(20261114)
SPECTRUM_SEED = 20261115  # separate stream: adding the spectrum must not change the frames
CHANNELS_PER_DETECTOR = 17
DETECTOR_BANDS_UM = {
    1: (0.75, 1.11),
    2: (1.11, 1.64),
    3: (1.64, 2.42),
    4: (2.42, 3.82),
    5: (3.82, 4.42),
    6: (4.42, 5.0),
}

VISITS = [  # (id, first day, last day) — shaped like Barnard's real visits
    ("v1", "2025-08-15", "2025-10-01"),
    ("v2", "2026-03-11", "2026-05-05"),
    ("v3", "2026-08-16", "2026-09-22"),
]
DETECTORS = {  # key: (detector list, lambda range um)
    "D1": ([1], (0.75, 1.11)),
    "D5": ([5], (3.82, 4.42)),
    "all": ([1, 2, 3, 4, 5, 6], (0.75, 5.0)),
}


def gaussian(
    shape: tuple[int, int], x: float, y: float, flux: float, sigma: float = PSF_SIGMA
) -> npt.NDArray[np.float64]:
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    return flux / (2 * np.pi * sigma**2) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2))


def _bump(lam: float, centre: float, width: float) -> float:
    return float(np.exp(-0.5 * ((lam - centre) / width) ** 2))


def cold_dwarf_flux_ujy(lam: float) -> float:
    emission = 2.0 + 20 * _bump(lam, 1.27, 0.08) + 8 * _bump(lam, 1.58, 0.06) + 120 * _bump(lam, 4.3, 0.35)
    return emission * (1 - 0.8 * _bump(lam, 3.3, 0.15))


def mock_spectrum() -> Spectrum:
    rng = np.random.default_rng(SPECTRUM_SEED)
    points: list[SpectrumPoint] = []
    for vid, first, last in VISITS:
        t0, t1 = Time(first).mjd, Time(last).mjd
        for detector, (lo, hi) in DETECTOR_BANDS_UM.items():
            for ch in range(CHANNELS_PER_DETECTOR):
                lam = lo + (hi - lo) * (ch + 0.5) / CHANNELS_PER_DETECTOR
                mjd = t0 + (t1 - t0) * (ch + rng.uniform(0, 1)) / CHANNELS_PER_DETECTOR
                saturated = vid == "v1" and detector == 5 and ch in (7, 8)
                flags = BIT["OVERFLOW"] | BIT["NONLINEAR"] if saturated else 0
                if vid == "v2" and detector == 1 and ch == 4:
                    flags |= BIT["SNOWBALL"]
                err = 1.5 + 0.05 * cold_dwarf_flux_ujy(lam)
                flux = cold_dwarf_flux_ujy(lam) + rng.normal(0, err)
                points.append(
                    SpectrumPoint(
                        lambda_um=round(lam, 4),
                        flux_ujy=None if saturated else round(float(flux), 3),
                        err_ujy=None if saturated else round(err, 3),
                        mjd=round(float(mjd), 4),
                        detector=detector,
                        visit=vid,
                        saturated=saturated,
                        flags=flags,
                    )
                )
    return Spectrum(points=sorted(points, key=lambda p: p.mjd))


def main() -> None:
    _, grid = make_grid(269.452077, 4.693365, fov_arcmin=10.0)
    n = grid.npix
    shape = (n, n)
    c = (n - 1) / 2

    stars = [
        (RNG.uniform(3, n - 4), RNG.uniform(3, n - 4), float(RNG.pareto(1.5) * 30 + 15), float(RNG.uniform(-1, 1)))
        for _ in range(25)
    ]
    mover_start = (c + 6.0, c - 8.0)
    mover_step = 0.85  # px per visit, northward (+y)
    variable = (c - 20.0, c + 15.0, 120.0)
    saturated = (c - 25.0, c - 25.0)

    frames_dir = OUT / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*"):
        old.unlink()

    frames: list[Frame] = []
    arrays: list[np.ndarray] = []
    for vi, (vid, first, last) in enumerate(VISITS):
        t0, t1 = Time(first), Time(last)
        mjd_mid = float((t0.mjd + t1.mjd) / 2)
        for dkey, (dets, lam) in DETECTORS.items():
            color_scale = {"D1": -1.0, "D5": 1.0, "all": 0.0}[dkey]
            noise_sigma = {"D1": 1.0, "D5": 1.4, "all": 0.5}[dkey]
            img = RNG.normal(0.0, noise_sigma, shape)
            flags = np.zeros(shape, dtype=np.uint32)

            for x, y, flux, color in stars:
                psf = gaussian(shape, x, y, flux * 10 ** (0.3 * color * color_scale))
                img += psf
                flags[psf > 3 * noise_sigma] |= BIT["SOURCE"]

            mover_flux = {"D1": 4.0, "D5": 60.0, "all": 25.0}[dkey]
            mx, my = mover_start[0], mover_start[1] + mover_step * vi
            psf = gaussian(shape, mx, my, mover_flux)
            img += psf

            vx, vy, vflux = variable
            img += gaussian(shape, vx, vy, vflux * (1.0, 0.4, 1.3)[vi])

            sx, sy = saturated
            img += gaussian(shape, sx, sy, 5000.0, sigma=1.2)
            yy, xx = np.mgrid[0:n, 0:n]
            r = np.hypot(xx - sx, yy - sy)
            flags[r < 4.0] |= BIT["NONLINEAR"]
            flags[r < 2.0] |= BIT["OVERFLOW"]
            img[r < 2.0] = np.nan  # masked in the stack -> "black centre"

            warnings: list[FrameWarning] = []
            if vi == 1:
                ghost = gaussian(shape, sx + 10, sy + 12, 80.0, sigma=2.5)
                img += ghost
                flags[ghost > 1.0] |= BIT["GHOST"]
                if dkey == "D1":
                    snow = np.hypot(xx - (c + 18), yy - (c + 20)) < 2.5
                    img[snow] = np.nan
                    flags[snow] |= BIT["SNOWBALL"]
            if vi == 0 and dkey == "D5":
                warnings.append(
                    FrameWarning(code="incomplete_lambda", message="incomplete λ coverage: 12 of 17 channels")
                )

            fid = f"{vid}-{dkey}"
            img.astype("<f4").tofile(frames_dir / f"{fid}.f32")
            flags.astype("<u4").tofile(frames_dir / f"{fid}.flags.u32")
            arrays.append(img)
            frames.append(
                Frame(
                    id=fid,
                    kind="visit_stack",
                    label=f"{first[:7]} · {dkey}",
                    mjd_mid=round(mjd_mid, 3),
                    date_range=(first, last),
                    detectors=dets,
                    lambda_um=lam,
                    n_exposures={"D1": 20, "D5": 20, "all": 120}[dkey] - (8 if warnings else 0),
                    data=f"frames/{fid}.f32",
                    flags=f"frames/{fid}.flags.u32",
                    shape=shape,
                    expected_px=PixelPos(x=round(mx, 2), y=round(my, 2)),
                    warnings=warnings,
                )
            )

    stack = np.concatenate([a[np.isfinite(a)] for a in arrays])
    vmin, vmax = np.percentile(stack, [1.0, 99.7])
    seq = Sequence(
        grid=grid,
        stretch=Stretch(kind="asinh", vmin=round(float(vmin), 3), vmax=round(float(vmax), 3), a=0.1),
        flag_bits=list(DEFAULT_FLAG_BITS),
        frames=frames,
        meta=SequenceMeta(
            target_name="MOCK (synthetic scene)",
            collections=["mock"],
            n_exposures_total=sum(f.n_exposures for f in frames if f.detectors != [1, 2, 3, 4, 5, 6]),
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            pipeline_tags=["mock"],
            mock=True,
            spectrum="spectrum.json",
        ),
    )
    (OUT / "spectrum.json").write_text(mock_spectrum().model_dump_json(indent=1) + "\n", encoding="utf-8", newline="\n")
    (OUT / "sequence.json").write_text(
        json.dumps(seq.model_dump(mode="json"), indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    size_kb = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1024
    print(f"wrote {len(frames)} frames ({n}x{n}) to {OUT.relative_to(ROOT)} — {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
