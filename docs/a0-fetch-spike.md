# A0 fetch spike: how to get SPHEREx pixels fast

Track A, 2026-11-14. Decides OD-4 (fetch strategy) and informs OD-5 (latency budget) in `docs/spec.md`.
Short facts are also in `CLAUDE.md` → Verified data facts; this file has the measurements behind them.

## Setup

- Target: Barnard's Star, 10′ FOV → 128 px window (`cutouts.cutout_size_deg`, margin 1.3 plus proper motion).
- Each method ran on its own random set of real exposures (5–16 per configuration, 60 in total), with the same retry
  policy: up to 5 attempts, exponential backoff with jitter, `Retry-After` honoured.
- Measured from a developer machine over a home connection, not from a server. Absolute times depend on the network
  and on IRSA's load; the ratios between methods are what matters.

## Results

| Method | Workers | Bytes per exposure | Seconds per exposure (wall) | Median / max latency | 503 / errors | `Retry-After` |
|---|---|---|---|---|---|---|
| IRSA cutout service | 1 | 4.2 MB | 4.47 | 3.7 / 9.0 s | 0 % / 0 | — |
| IRSA cutout service | **2** | 4.2 MB | **3.11** | 4.6 / 9.7 s | 0 % / 0 | — |
| IRSA cutout service | 3 | 4.2 MB | 3.48 | 10.3 / 16.9 s | **18 %** / 0 after retries | yes, `Retry-After: 5`; honouring it helps |
| S3 `nasa-irsa-spherex`, range of whole rows | 1 | 3.9 MB | 3.58 | 3.6 / 4.4 s | 0 % / 0 | no 503 seen |
| S3, range of whole rows | 4 | 3.9 MB | 1.11 | 3.7 / 6.3 s | 0 % / 0 | no 503 seen |
| S3, range of whole rows | **8** | 3.7 MB | **0.63** | 4.4 / 7.7 s | 0 % / 0 | no 503 seen |
| IRSA `ibe` multi-range | 1 | **0.96 MB** | 6.05 | 6.1 / 6.8 s | 0 % / 0 | no 503 seen |
| IRSA `ibe` multi-range | 3 | **0.97 MB** | 2.01 | 5.5 / 6.8 s | 0 % / 0 | no 503 seen |

Estimated full depth of Barnard (≈360 exposures):

| Method | Time | Data |
|---|---|---|
| Cutout service, 2 workers | ≈19 min | 1.5 GB |
| **S3, 8 workers** | **≈4 min** | **1.35 GB** |
| ibe, 3 workers | ≈12 min | 0.35 GB |

The cutout service depends heavily on load: on the morning of 2026-11-14 it took ~6 s per cutout at 2 workers with
many 503s, in the afternoon ~3 s with none.

**After A2** (the real implementation, `archive/fetch.py`): Barnard with a cap of 2 per (detector, visit) gave
36/36 exposures in 27.4 s (0.76 s per exposure) through S3 at 8 workers, 0 errors, 0.33 MB per exposure on disk,
and no event-loop blocking under asyncio debug.

**Correctness:** on exposure `2025W35_2A_0611_2_D1`, the `IMAGE`, `VARIANCE`, `ZODI` and `FLAGS` pixels read from S3
and from ibe are bit-identical to the cutout service on the 128×128 overlap. Through `load_cutout`, the per-pixel
`wavelength_um` / `bandwidth_um` maps are identical too.

**Not measured:** `fits.open(..., use_fsspec=True)` + `.section`. The fsspec HTTP backend needs `aiohttp`, which is not
a dependency. The `httpx` range reads used instead read exactly the bytes `.section` would, with control over retries
and concurrency.

## What the measurements revealed

- **EPSF cannot be dropped server-side.** The cutout service accepts only `center` and `size`. EPSF (8752×451,
  3.9 MB) is never cut, which is why every cutout weighs ~4 MB regardless of its size.
- **Layout of a full L2 file** (62 MB):

  | HDU | Storage | Size |
  |---|---|---|
  | `IMAGE`, `VARIANCE`, `ZODI` | float32 2040×2040, uncompressed (8160 B per row) | 16.6 MB each |
  | `FLAGS` | int32, RICE_1 tile-compressed, one tile per image row (~3.9 KB) | 8.0 MB |
  | `EPSF` | binary table | 3.9 MB |
  | `WCS-WAVE` | binary table, LVF lookup | 2.9 KB |

- **S3 ignores multi-range requests** and answers `200` with the whole 62 MB file. Send one range per request.
- **IRSA `ibe` accepts up to 100 ranges per request** (`multipart/byteranges`). With 101 or more it also answers
  `200` with the whole file.
- Every range response must be streamed and aborted unread when the status is not `206`.
- **What the cutout service changes in headers:** every `CRPIX*` of every WCS key (`CRPIX1/2`, `CRPIX1A/2A`,
  `CRPIX1W/2W`) moves by the window origin, and `FLAGS` is decompressed into an `IMAGE` HDU that keeps the `MSKN`
  bit-name cards. `archive/ranges.py` reproduces both, so `load_cutout` reads files from every source the same way.
- The S3 bucket is in **us-east-1**. Per-request latency from elsewhere is ~0.3 s; throughput comes from parallelism.
- The TAP query that lists collections takes **10–33 s**: cache it and warm it up at startup, never per request.

## Decision (OD-4)

1. **Primary: S3 range reads, 8 workers** (`settings.max_concurrency`, env `IRSA_MAX_CONCURRENCY`).
2. Fallback: IRSA `ibe` multi-range (≤100 ranges per request), up to 3 workers.
3. Last resort: the cutout service, at most 2 workers.

Still open with the team: the exposure cap per group (proposed 20 per (detector, visit) for wide fields, 10 per
30-day deep-field bin), the OD-5 budget, and whether NFR-5's limit applies to S3 (see `docs/spec.md`).

## How to use it (e.g. for prebake)

Per exposure, `fetch_cutouts` tries S3 → ibe → cutout service. Exposures that fail on every source go to
`FetchResult.failed`; exposures whose window misses the detector go to `FetchResult.off_detector`. Neither fails the
sequence.

```python
import asyncio

from app.archive.collections import CollectionDiscovery
from app.archive.cutouts import cutout_size_deg
from app.archive.fetch import FetchResult, fetch_cutouts, query_exposures
from app.archive.http import make_http
from app.archive.visits import cap_per_detector, group_visits
from app.astrometry import position_at
from app.config import configure_ssl
from app.domain import Target


def print_progress(stage: str, done: int, total: int) -> None:
    print(f"\r  {stage} {done}/{total}", end="", flush=True)


async def fetch_target(target: Target, fov_arcmin: float = 10.0, cap: int = 20) -> FetchResult:
    http = make_http()
    async with http.client:
        collections = await CollectionDiscovery().collections(http)
        exposures = await query_exposures(http, target, collections)
        plan = [(v, m) for v in group_visits(exposures) for m in cap_per_detector(v, cap)]
        first, last = min(m.mjd_mid for _, m in plan), max(m.mjd_mid for _, m in plan)
        center = position_at(target, (first + last) / 2)
        size_deg = cutout_size_deg(fov_arcmin, target, last - first)
        return await fetch_cutouts(http, plan, center, size_deg, progress=print_progress)


configure_ssl()
result = asyncio.run(fetch_target(target))
```

- The raw cache is shared with `archive/naive.py`: same file names (`cutouts.cache_name`) and format, so cutouts
  that are already downloaded are reused, and a rerun fetches only what is missing.
- To measure or force one source: `fetch_one(http, meta, visit_id, center, size_deg, raw_dir, sources=("s3",))`
  (`"s3"`, `"ibe"` or `"cutout"`). The throwaway spike scripts were not kept; this is the way to re-measure.
