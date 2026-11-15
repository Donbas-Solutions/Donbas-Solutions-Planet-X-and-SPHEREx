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
| `GET /api/spectrum?ra=&dec=&pmra=&pmdec=&ref_epoch=` | `Spectrum` | P1; the target of a sequence: measured by its sequence job, `404` until one has finished (or after the 24 h cache TTL); offline fallback: `meta.spectrum` of the bundle |
| `GET /api/lightcurve?…same…` | `Spectrum` | P1; the same points as `/api/spectrum`; client groups by detector / λ bin |
| `GET /api/overlays?ra=&dec=&fov=&mjd=` | `Overlays` | P1; Gaia DR3 stars of the field at their positions on `mjd`; sources without data are listed in `unavailable` (see Overlays) |
| `GET /files/...` | binary | processed frames |

Diff frames are computed client-side from two `visit_stack` frames; the API does not need to send them.
Errors: FastAPI default `{"detail": "..."}`; `501` = not implemented yet.

## Overlays (FR-18)

`ra`, `dec`, `fov` are the grid centre and field of a sequence (`grid.ra`, `grid.dec`, `grid.fov_arcmin`); `mjd`
(40000–90000) is the epoch the positions are wanted for, usually a frame's `mjd_mid`.

```jsonc
{
  "gaia": [{"source_id": "4472832130942575872", "ra": 269.446237, "dec": 4.768603, "g": 8.19,
            "pmra": -801.55, "pmdec": 10362.39}],
  "asteroids": [],
  "unavailable": ["skybot"]
}
```

- `gaia`: Gaia DR3 stars with G ≤ 19 inside the square field at `mjd`, brightest first, at most the 500 brightest
  of the query circle. `ra`/`dec` are propagated from Gaia's epoch 2016.0 to `mjd` with the catalog proper motion
  (ICRS, parallax ignored, SR-3). `pmra`/`pmdec` are `null` for stars without a measured proper motion; those stay
  at their 2016.0 position. With `pmra`/`pmdec` a client can step linearly to nearby epochs instead of asking
  again (< 0.001″ off within a year).
- `source_id` is a **string**: Gaia ids exceed 2^53 and would be rounded by JavaScript's JSON parser.
- `unavailable` lists the sources that have no data in this answer: `gaia` when no Gaia server answered (the
  response is still `200`, with `gaia: []`), `skybot` always for now (asteroids, FR-25, are not implemented), so
  an empty list is never read as "nothing there".
- Gaia servers, in order: MAST, GAVO, ESA (15 s each; the one that answered last is tried first). The stars of a
  field are cached, so the frames of one sequence cost one catalog query.

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
    "expected_px": {"x": 54.0, "y": 40.85},
    "warnings": [{"code": "incomplete_lambda", "message": "incomplete λ coverage: 0.28 of 0.51 µm"}]
  }],
  "meta": {"target_name": "Barnard's Star", "collections": ["spherex_dr1", "spherex_qr3"], "n_exposures_total": 363,
           "generated_at": "2026-11-14T12:00:00+00:00", "pipeline_tags": ["l2b-v27"], "mock": false,
           "spectrum": "spectrum.json"}
}
```

## Frame warnings

`Frame.warnings` is a list of `{code, message}`. Clients group and count by `code`; `message` is display text and
may change.

| `code` | Meaning | Partial data? |
|---|---|---|
| `few_exposures` | the visit has < 80 % of the exposures of the best visit of the same stack type (SR-1) | yes |
| `incomplete_lambda` | the stack samples < 80 % of the 17 LVF channels per detector (`all`: of every requested detector), or its λ span at the target is < 80 % of the best visit's (SR-1). Capped live stacks (8 per detector) always get it | yes |
| `saturated` | the target pixel carries `OVERFLOW`/`NONLINEAR`: shown as saturated, never measured | no — a property of the source |

Only the "partial data" codes mean the frame's data is incomplete (spec §5.2). New codes are a contract change.

## Static bundles (prebaked targets, mock)

```
frontend/public/<bundle>/
  sequence.json          # a Sequence, URLs relative to this file
  spectrum.json          # optional: a Spectrum of the target, linked from meta.spectrum
  frames/<id>.f32
  frames/<id>.flags.u32
```

`meta.spectrum` (optional, `null` = none) points to a `Spectrum` of the **target** at its proper-motion-propagated
position: forced photometry on every exposure, one point per exposure. One file serves both the spectrum
(flux vs `lambda_um`) and the light curve (flux vs `mjd`, grouped by `detector`). Same rules as the API: saturated
points have `flux_ujy: null`, `err_ujy: null`, `saturated: true`. Frontend order for the spectrum and light-curve tabs:
live `/api/spectrum` / `/api/lightcurve` → `meta.spectrum` → "unavailable offline". Sources other than the target
need the live backend.

`frontend/public/mock/` is synthetic (`scripts/make_mock.py`). Prebaked real targets go to
`frontend/public/prebaked/<target_id>/` (`scripts/prebake.py`, Track C). The viewer loads any bundle via
`?manifest=/prebaked/barnard/sequence.json`.
