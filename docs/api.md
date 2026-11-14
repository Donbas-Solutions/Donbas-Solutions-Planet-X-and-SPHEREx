# SPHEREx Blink — API contract

Shared by all tracks. Machine-readable twins: `backend/app/models.py` (pydantic) and `frontend/src/api/types.ts`.
`backend/tests/test_contract.py` validates the mock bundle against the models. **Changing the contract = update all
three + tell the team.**

## Conventions

| Topic | Rule |
|---|---|
| Coordinates | ICRS, degrees. Proper motion `pmra` includes cos(dec); mas/yr. Parallax mas. Epochs as Julian years (`2000.0`). |
| Times | `mjd_mid` = MJD (UTC); `date_range` = ISO dates. |
| Grid | North up, east left, TAN, native 6.2″/px, odd `npix` (target on the central pixel). `grid.wcs` = FITS header cards. |
| Arrays | Row-major `[ny, nx]`, **row 0 = south** (FITS order), x grows to the west. The frontend flips rows when drawing. |
| Pixel positions | `expected_px` = 0-based `(x=column, y=row)` in the array convention above. |
| Frame data | Raw **float32 little-endian**, background-subtracted surface brightness (MJy/sr). Masked pixels = `NaN`. |
| Flags | Raw **uint32 little-endian**, same shape; for stacks = bitwise OR of contributing exposures. |
| URLs | `data` / `flags` are relative to the manifest URL (static bundles) or absolute paths (`/files/...`). |
| Stretch | One shared stretch per sequence (`vmin`, `vmax` from percentiles over all frames). Applied client-side. |

## FLAGS bits (SPHEREx l2b-v27, read from the FLAGS header `MSKNnnnn`/`MSKDnnnn`)

Every `Sequence` carries `flag_bits`. Policy (`backend/app/flags.py`):

| Group | Bits | In stacks | UI |
|---|---|---|---|
| `bad` | TRANSIENT 0, SUR_ERROR 2, NONFUNC 6, MISSING_DATA 9, HOT 10, COLD 11, PERSIST 17, OUTLIER 19, SNOWBALL 27 | masked | "bad data" overlay |
| `saturation` | OVERFLOW 1, NONLINEAR 15 | masked | "saturated" overlay; no photometry |
| `artifact` | PHANMISS 14, CROSSTALK 20, GHOST 22, GHOST_FPA 23, GHOST_EXT 24, STREAK 25, BLOOM 26, HALO 28 | kept | "artifact" overlay |
| `info` | DICHROIC 7, FULLSAMPLE 12, **SOURCE 21** | kept | hidden by default |

`SOURCE` marks every pixel of a known source: masking it would erase all stars. There is no dedicated "saturated"
bit — saturation shows up as `OVERFLOW` / `NONLINEAR`.

## Endpoints

| Method & path | Response | Notes |
|---|---|---|
| `GET /api/health` | `Health` | `{status, collections, cache:{raw_mb, processed_items}}` |
| `GET /api/resolve?name=` | `ResolveResult` | SIMBAD with mirror fallback (`simbad.harvard.edu`); 404 if unknown |
| `GET /api/sequence?ra=&dec=&fov=&det=&mode=&pmra=&pmdec=&ref_epoch=&allwise=` | `200 Sequence` or `202 JobAccepted` | `fov` arcmin (2–30, default 10); `det` = `all` or `1..6` (comma list); `mode` = `visit_stack` (default) \| `exposures` |
| `GET /api/jobs/{job_id}` | `JobStatus` | poll every 1–2 s; `result` present when `done` |
| `GET /api/spectrum?ra=&dec=&pmra=&pmdec=&ref_epoch=` | `Spectrum` | P1 |
| `GET /api/lightcurve?…same…` | `Spectrum` | P1; client groups by detector / λ bin |
| `GET /api/overlays?ra=&dec=&fov=&mjd=` | `Overlays` | P1; failed sources listed in `unavailable` |
| `GET /files/...` | binary | processed frames |

Diff frames are computed client-side from two `visit_stack` frames; the API does not need to send them.
Errors: FastAPI default `{"detail": "..."}`; `501` = not implemented yet.

## Models (abridged; see `backend/app/models.py`)

```jsonc
// Sequence
{
  "grid": {"ra": 269.452077, "dec": 4.693365, "fov_arcmin": 10, "npix": 97, "pixscale_arcsec": 6.2, "wcs": {"CTYPE1": "RA---TAN", "...": "..."}},
  "stretch": {"kind": "asinh", "vmin": -2.7, "vmax": 34.0, "a": 0.1},
  "flag_bits": [{"bit": 1, "name": "OVERFLOW", "description": "...", "group": "saturation", "mask_in_stack": true}],
  "frames": [{
    "id": "v2-D5", "kind": "visit_stack", "label": "2026-03 · D5",
    "mjd_mid": 61139.0, "date_range": ["2026-03-11", "2026-05-05"],
    "detectors": [5], "lambda_um": [3.82, 4.42], "n_exposures": 20,
    "data": "frames/v2-D5.f32", "flags": "frames/v2-D5.flags.u32", "shape": [97, 97],
    "expected_px": {"x": 54.0, "y": 40.85}, "warnings": []
  }],
  "meta": {"target_name": "Barnard's Star", "collections": ["spherex_dr1", "spherex_qr3"], "n_exposures_total": 363,
           "generated_at": "2026-11-14T12:00:00+00:00", "pipeline_tags": ["l2b-v27"], "mock": false}
}
```

## Static bundles (prebaked targets, mock)

```
frontend/public/<bundle>/
  sequence.json          # a Sequence, URLs relative to this file
  frames/<id>.f32
  frames/<id>.flags.u32
```

`frontend/public/mock/` is synthetic (`scripts/make_mock.py`). Prebaked real targets go to
`frontend/public/prebaked/<target_id>/` (`scripts/prebake.py`, Track C). The viewer loads any bundle via
`?manifest=/prebaked/barnard/sequence.json`.
