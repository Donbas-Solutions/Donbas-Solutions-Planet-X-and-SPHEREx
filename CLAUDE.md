# SPHEREx Blink — NASA Space Apps 2026 "Planet X and SPHEREx"

Public web tool: the user enters RA/Dec (or an object name) and gets an animated sequence (blink / flipbook)
of NASA SPHEREx images of that sky patch, so moving and variable objects stand out.

- Hackathon: submission deadline **2026-11-15 23:59 Kyiv (21:59 UTC)** (`docs/deploy.md`). Team of 4, parallel Claude
  Code sessions, one per role.
- Requirements — what to build and when it is done (IDs FR/SR/NFR/T/OD): **`docs/spec.md`**, the source of truth.
- Plan — tracks, order of work, checkpoints: `docs/agent-prompt.md`. API contract: `docs/api.md`.
- Challenge text: `docs/project_info.md`. Background research (English): `docs/spherex-research.md`.
  Where any doc disagrees with "Verified data facts" below, this file wins.

## Communication
- Reports to the team: **Ukrainian**. Code, comments, identifiers, commit messages, API: English.
- Scope cuts, hosting, accounts, anything public-facing or irreversible → ask the team, don't guess.

## Code comments
- Keep comments to a minimum: names, types and small functions should explain *what* the code does.
- Comment only a non-obvious *why*: a science/instrument fact, an upstream workaround, a deliberate trade-off.
- No comments that restate the code, no commented-out code, no section banners or changelog notes.

## Stack and layout
- `backend/` — Python ≥3.11 (dev machine: 3.13), FastAPI, astropy 8, astroquery, pyvo, reproject, photutils, numpy.
  Env: **uv** — `backend/pyproject.toml` + `backend/uv.lock`, Python pinned by `backend/.python-version` (3.13).
  Lint/format: **ruff** — `ruff.toml` at the repo root covers `backend/`, `scripts/`, `science/`.
  Types: **mypy --strict** (`backend/pyproject.toml`). Python conventions: skill `.claude/skills/fastapi-backend`.
- `frontend/` — React 19 + Vite 8 + TypeScript, npm. Aladin Lite pinned to **3.8.2** (npm `latest` is a beta).
  Aladin Lite is GPL/LGPL-3 — keep in mind when choosing the repo license.
  Lint: **oxlint**. Frontend conventions: skill `.claude/skills/react-frontend`.
- Backend seam (Phase 0.5): `backend/app/domain.py` holds the types shared by `archive/` (Track A: query, visits,
  cutouts, fetch) and `pipeline/` (Track C: `build_sequence`, `write_bundle`). Ownership per track:
  `docs/agent-prompt.md` → Roles and ownership.
- `science/` — validation scripts/notebooks, `targets.json`, `VALIDATION.md`.
- `scripts/fetch_sample.py` — real development sample via the temporary naive fetcher;
  `scripts/prebake.py` (Track C) — static bundles for the 5 test targets into `frontend/public/prebaked/`.
- `docs/api.md` — API contract shared by all tracks. Changing it = tell the team.

## Verified data facts (checked live against IRSA, 2026-11-14)
- **Collections** (TAP `ivoa.obscore`): `spherex_dr1` (945,725 rows), `spherex_dr1_deep`, `spherex_dr1_cal`,
  `spherex_dr1_cube` (HiPS-tiled spectral cubes, released 2026-11), `spherex_qr3`, `spherex_qr3_deep`.
  `spherex_qr2` / `spherex_qr` return **0 rows** — never hardcode a collection; discover via
  `SELECT obs_collection, COUNT(*) FROM ivoa.obscore WHERE obs_collection LIKE 'spherex%' GROUP BY obs_collection`
  and use the newest DR + the newest QR (wide + deep), excluding `_cal` and `_cube`.
- **SIA2**: `https://irsa.ipac.caltech.edu/SIA?COLLECTION=<c>&POS=circle+<ra>+<dec>+<r_deg>&RESPONSEFORMAT=CSV`.
  Useful columns: `access_url, obs_id, t_min, t_max` (MJD), `energy_bandpassname` (`SPHEREx-D1`…`D6`),
  `em_min, em_max` (whole-image range, NOT the λ at your pixel), `s_region, obs_release_date`.
- **Cutouts**: `<access_url>?center=<ra>,<dec>&size=<deg>`. Returns MEF: `IMAGE` (surface brightness, check BUNIT),
  `FLAGS`, `VARIANCE`, `ZODI` — cut to size; `EPSF` (8752×451, ~4 MB) and `WCS-WAVE` (1100×1) — **not cut**.
  ⇒ every cutout is **~4 MB regardless of size**. Celestial WCS: `RA---TAN-SIP`. Headers: `DATE-OBS`, `MJD-AVG`, `DETECTOR`.
- **One `obs_id` = one exposure seen by two detectors** (dichroic pair): SIA lists 2 rows per `obs_id`. The unique key
  is (obs_id, detector) = `ExposureMeta.key`; deduplicating by `obs_id` alone silently drops half the data.
- **Spectral WCS**: alternate WCS key `W` (`WAVE-TAB` lookup in `WCS-WAVE`), evaluated without SIP;
  `archive.cutouts.load_cutout` already returns per-pixel `wavelength_um` / `bandwidth_um` maps.
- **Cutouts are truncated at detector edges**, not padded: shapes differ between exposures (seen: 129×128, 106×129,
  56×128, 7×29). Only the common grid (reprojection) makes frames comparable.
- **IRSA cutout service under load** (2026-11-14): many 503s at 4 parallel workers; at 2 workers ~3–6 s per cutout
  depending on the day; at 3 workers 18 % 503 with `Retry-After: 5`. Only `center` and `size` are accepted: EPSF
  cannot be dropped server-side.
- **`ZODI` is not subtracted from `IMAGE`** by the pipeline (IRSA tutorial) — subtract it yourself.
- **Bicubic `reproject_interp` with a single NaN input returns an all-NaN image.** Fill masked pixels first and re-mask
  from a resampled validity map (`backend/app/pipeline/exposure.py`).
- **Positions on the undersampled PSF:** flux-weighted centroids lock onto pixel centres and shortened 1-px shifts by
  10–20 % (ε Indi B: 0.87 vs 1.05 px); a 2D Gaussian fit with masked pixels excluded recovers them (1.05 px) and also
  works on Barnard's saturated (NaN) core.
- **WISE 0855 is blended with a field star:** at its propagated position a 3-px aperture gets 957 µJy at λ < 1.6 µm
  (S/N 83), where WISE 0855 itself (J ≈ 25) is invisible. In D5–D6 the source moves toward PA 276–277° (expected 275°),
  shortened by the blend; the 412 ± 26 µJy at λ ≥ 3.8 µm is an upper bound, not WISE 0855's flux.
- **The blending star is Gaia DR3 5756956644387831296** (G 16.31, proper motion 6 mas/yr): 11.8″ from WISE 0855's
  expected position in the 2025-05 visit and 4.6″ in 2026-04/05, inside the 3-px (18.6″) aperture both times.
- **Saturation confirmed at full depth:** Barnard in every band; RW Aur in D2–D6 (161 of 178 points); R Dra in all
  128 points. ε Indi B is not saturated (2 of 357 points).
- **ε Indi B's QR3 visit (2026-09/10) has no D1 and D4 exposures** — those frame sets have a shorter baseline.
- **SAPM** (per-pixel solid angle, would refine photometry): `s3://nasa-irsa-spherex/dr1/solid_angle_pixel_map/
  cal-sapm-v3-2026-191/<k>/solid_angle_pixel_map_D<k>_spx_cal-sapm-v3-2026-191.fits`, HDU `IMAGE`, arcsec² per pixel
  (IRSA source-discovery tutorial). Not used yet: photometry takes the pixel area from the WCS.
- Calling `logging.getLogger("astropy")` **before** importing astropy breaks astropy's logger (`AttributeError:
  _set_defaults`); configure it after the imports.
- DR1 and QR3 sample files both carry pipeline tag `l2b-v27` (consistent calibration).
- **Full L2 file layout** (62 MB): `IMAGE`, `VARIANCE`, `ZODI` = uncompressed float32 2040×2040 (8160 B per row);
  `FLAGS` = RICE_1 tile-compressed, one tile per image row (~3.9 KB); `EPSF` 3.9 MB; `WCS-WAVE` 2.9 KB.
- **S3 mirror** `nasa-irsa-spherex` (anonymous, plain HTTPS, region us-east-1): prefixes `dr1/`, `qr2/`, `qr3/`; same
  paths as the IRSA `ibe` URLs (`dr1/level2/<week>/<version>/<detector>/…`). **Primary fetch path (OD-4, A0):**
  single-range reads of whole rows give pixels bit-identical to the cutout service, ~3.9 MB per exposure, 0 errors,
  scales linearly (8 workers → 0.6 s per exposure, Barnard full depth ~4 min).
  **S3 ignores multi-range requests and answers `200` with the whole 62 MB file** — send one range per request.
- **IRSA `ibe` range reads** (fallback): `multipart/byteranges` up to **100 ranges per request**; 101+ → `200` with the
  whole file. Row-window multi-range reads: ~1 MB per exposure, 3 workers → 2 s per exposure, 0 errors.
- Any range request must stream the response and abort on a status other than `206`, without reading the body.
- All Resources-tab sources (IRSA, tutorials, WiseView, Gaia MAST/ESA TAP, NEOSSat, CADC) are publicly reachable; no
  private hackathon data exists beyond them.
- **Coverage of test targets** (SIA radius 0.01°, DR1+QR3, wide+deep):

  | Target | Exposures | Visits | Max baseline → expected shift |
  |---|---|---|---|
  | Barnard's Star | 363 | 2025-08/10 · 2026-03/05 · 2026-08/09 | ~1.1 yr → ~11″ ≈ 1.8 px |
  | ε Indi B | 468 | 2025-04/06 · 2025-09/11 · 2026-04/05 · 2026-09/10 | ~1.4 yr → ~6.6″ ≈ 1.1 px |
  | WISE 0855−0714 | 258 (DR1 only, none in QR3 yet) | 2025-05 (only 30 exp.) · 2025-10/12 · 2026-04/05 | ~1.0 yr → ~8″ ≈ 1.3 px |
  | RW Aur | 336 | 2025-09 · 2026-02/03 · 2026-09 | brightness test |
  | R Dra | 2,514 (deep field near NEP) | continuous 2025-04 … 2026-09 | brightness test; dense sampling |

- **FLAGS** is int32; bit names are in the FLAGS header (`MSKNnnnn`/`MSKDnnnn`). No dedicated saturation bit
  (use `OVERFLOW`, `NONLINEAR`). Bit 21 `SOURCE` = pixel of a known source → **never mask it**. Policy: `backend/app/flags.py`, `docs/api.md`.
- **WISE 0855 challenge coordinates are epoch ≈2010.5**, 85″ from the SIMBAD J2000 position. Use `science/targets.json`
  (SIMBAD J2000 + PM) for propagation, never the challenge coordinates as J2000.
- SIMBAD Strasbourg was down on 2026-11-14 (404); the mirror `simbad.harvard.edu` worked → always have a fallback.
- **Gaia DR3 TAP** (2026-11-15): ESA (`gea.esac.esa.int`), its Heidelberg mirror and VizieR did not answer; MAST
  (`mast.stsci.edu/vo-tap/api/v0.1/gaiadr3/sync`, table `dbo.gaia_source`) and GAVO (`dc.g-vo.org/tap/sync`,
  `gaia.dr3lite`) did: 1.3 s and 0.6 s for a 10′ field; GAVO timed out on a 30′ field at the Galactic centre.
  `source_id` exceeds 2^53: send it as a string. Barnard (4472832130942575872) and ε Indi B
  (6412596012146801152, G 18.0) propagated from 2016.0 land within 0.01 px of the frames' `expected_px`.
- **HiPS for Aladin** (CDS): `CDS/P/SPHEREx/QR2/D1`…`D6`, `CDS/P/SPHEREx/QR2/color` (order 7, png).
  CDS's HiPS servers (`alasky`, `alaskybis`) were down on 2026-11-14/15. The IRSA mirror answered throughout:
  `irsa.ipac.caltech.edu/data/hips/CDS/2MASS/Color`, `…/CDS/AllWISE/RGB-W4-W2-W1`, `…/CDS/DSS2/color` (list:
  `irsa.ipac.caltech.edu/data/hips/list`); it has no SPHEREx colour mosaic, only the DR1 cube.
- **IRSA SIA and TAP flapping** (2026-11-15, 08:40–09:20 UTC): `502 Proxy Error` within 0.6 s for most requests,
  now and then a `200` after ~21 s; sequential and parallel requests failed alike. The file servers (`ibe`, S3)
  were unaffected. The backend therefore keeps the SIA answer of each collection for an hour
  (`archive.sia.SiaCache`): a retried search converged on the third attempt while direct probes still failed.
- Pixel 6.2″; 6 detectors = 6 bands (D1 0.75–1.11 µm … D6 4.42–5.00 µm); λ varies across each frame (LVF).
- macOS python.org Python fails HTTPS to IRSA with `CERTIFICATE_VERIFY_FAILED` → run `Install Certificates.command` or use `certifi`.

## Science rules (non-negotiable)
- Compare like with like: the default blink unit is a **per-visit stack per detector** (or all detectors combined),
  never raw single exposures of different λ presented as the same band. Record λ coverage per stack; warn when incomplete.
- Deep-field targets (e.g. R Dra) have no 6-month gaps: split long visits into fixed time bins (default 30 d)
  and cap exposures per bin.
- Propagate catalog positions with proper motion to each frame's `MJD-AVG` (`SkyCoord.apply_space_motion`).
  Stay in ICRS: do NOT transform to GCRS (aberration ≈ 20″). Ignore parallax (≤0.55″, <0.1 px) and say so.
- Background first (ZODI extension, then a local 2D background — `photutils.Background2D`, 24-px boxes, no 3×3 filter),
  then one shared stretch for every frame of a sequence.
- Reproject to a common north-up TAN grid at native 6.2″/px with bicubic interpolation; upsample only for display.
- FLAGS: mask in stacks, show as overlay, never report a saturated measurement as a number.
- Positions: masked 2D Gaussian fit (`pipeline.measure.locate_source`), never flux-weighted centroids (see facts).
- Honesty: WISE 0855 is at the detection limit — show the expected position and S/N or an upper limit, no detection claims
  below 5σ. Its aperture is blended with a field star (see facts): its motion is shown, its flux is only an upper
  bound. No Planet Nine claims.

## Git: commits and pushes
- Commit messages follow **Conventional Commits** and are **exactly one line**: `<type>(<scope>): <summary>`.
  English, imperative, lower-case summary, no trailing period, ≤72 chars in total, no body, no trailers.
  - `type`: `feat` (new behaviour) · `fix` (bug fix) · `docs` · `test` · `refactor` (no behaviour change) · `perf` ·
    `build` (deps, packaging) · `ci` · `chore` (tooling, config, housekeeping) · `style` (formatting only).
  - `scope` (optional, one word): the area — `archive`, `api`, `jobs`, `pipeline`, `science`, `prebake`, `frontend`,
    `player`, `charts`, `deploy`, `docs`.
  - A change that breaks the API contract or `domain.py` gets `!`: `feat(api)!: add spectrum.json to static bundles`.
  - Examples: `feat(pipeline): add per-visit inverse-variance stacks` · `fix(archive): dedupe sia rows by obs_id and
    detector` · `docs: correct eps ind a distance` · `chore: ignore python caches of root scripts`.
  - Merge commits created by `git pull` / PRs keep git's default message.
- Commits are **local only**: commit at green checkpoints on your track branch.
- Before every commit, everything you touched is clean: Python — `ruff check`, `ruff format --check`, `mypy`, `pytest`;
  frontend — `npm run build`, `npm run lint` (see Commands).
  Do not pipe the gate commands into `tail`/`grep` inside an `&&` chain: the pipe hides their exit code.
- **Never push** (`git push`, PRs, remote branches, tags) unless the person you are working with explicitly tells you
  to push in the current conversation. One "push" covers that one push, not later ones.
- Never force-push or rewrite history that is already on the remote.

## Guardrails
- Never fetch full-frame FITS in a request path. ≤8 concurrent requests to IRSA, retries with backoff, timeout ≥120 s,
  generic User-Agent `spherex-blink/0.1` — no personal data in requests.
- Cache and data (`cache/`, `*.fits`, raw downloads) are never committed; `.gitignore` covers them. Exception: small
  FITS fixtures in `backend/tests/fixtures/` (strip `EPSF` first).
- No deploys, account creation, or anything public without an explicit OK from a human (pushes: see Git section).
- Stay inside your track's directories; contract changes go through `docs/api.md` + a note to the team.

## Commands
Install tools once: macOS `brew install uv ruff` · Windows `winget install astral-sh.uv` (ruff then comes with the
dev dependencies). Setup: `cd backend && uv sync && cd ..` and `cd frontend && npm ci && cd ..`.
uv reads `.python-version` + `uv.lock`, so everyone gets identical versions (it downloads Python 3.13 if missing).
All commands below are the same on macOS and Windows.

| Task | Command |
|---|---|
| Backend dev server (:8000) | `cd backend && uv run uvicorn app.main:app --reload --port 8000` |
| Frontend dev server (:5173, proxies `/api` + `/files` to :8000) | `cd frontend && npm run dev` |
| Backend tests | `cd backend && uv run pytest -q` (live IRSA/SIMBAD tests: `uv run pytest -m network`) |
| Backend type check | `cd backend && uv run mypy app tests` |
| Python lint + format (whole repo, from root) | `uv run --project backend ruff check --fix .` · `uv run --project backend ruff format .` |
| Frontend build / lint | `cd frontend && npm run build` · `npm run lint` |
| Regenerate mock bundle (from root) | `uv run --project backend python scripts/make_mock.py` → `frontend/public/mock/` |
| Re-resolve test targets (from root) | `uv run --project backend python science/resolve_targets.py` → `science/targets.json` |
| Real data sample (from root) | `uv run --project backend python scripts/fetch_sample.py barnard eps_ind_b --max-per-detector 4` → `cache/raw/` |
| Add a Python dependency | `cd backend && uv add <pkg>` (dev: `uv add --dev <pkg>`); commit `pyproject.toml` + `uv.lock` |
| View a bundle | `http://localhost:5173/?manifest=/mock/sequence.json` (default) |
| Prebake static bundles (from root) | `uv run --project backend python scripts/prebake.py [target ...]` → `frontend/public/prebaked/` (S3 fetcher; ~1–2 min per target) |
| Validate the test targets (from root) | `uv run --project backend python science/validate.py [target ...]` → `science/VALIDATION.md` (~5 min for all; a subset rewrites the report with only that subset) |
| Preview one target (from root) | `uv run --project backend python science/preview.py barnard` → `cache/preview/<target>/preview.png` |
| Type-check the scripts | `uv run --project backend mypy --strict --ignore-missing-imports --explicit-package-bases science/validate.py scripts/prebake.py` |

Use `uv run ... ruff` for checks: it is the locked version. A brew/editor ruff may differ by a patch release
(on 2026-11-14: brew 0.17.4, lock 0.17.5). VS Code Ruff extension: set `"ruff.importStrategy": "fromEnvironment"`.
