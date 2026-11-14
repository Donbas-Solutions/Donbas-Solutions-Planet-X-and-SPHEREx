# SPHEREx Blink — NASA Space Apps 2026 "Planet X and SPHEREx"

Public web tool: the user enters RA/Dec (or an object name) and gets an animated sequence (blink / flipbook)
of NASA SPHEREx images of that sky patch, so moving and variable objects stand out.

- Hackathon: submission deadline **2026-11-15**. Team of 3–4, parallel Claude Code sessions, one per track.
- Plan, tracks, priorities, API contract: `docs/agent-prompt.md` (source of truth for *what* to build).
- Challenge text: `docs/project_info.md`. Background research: `docs/spherex-research.md`.
  The research doc is **partly outdated**: where it disagrees with "Verified data facts" below, this file wins.

## Communication
- Reports to the team: **Ukrainian**. Code, comments, identifiers, commit messages, API: English.

## Code comments
- Keep comments to a minimum: names, types and small functions should explain *what* the code does.
- Comment only a non-obvious *why*: a science/instrument fact, an upstream workaround, a deliberate trade-off.
- No comments that restate the code, no commented-out code, no section banners or changelog notes.
- Scope cuts, hosting, accounts, anything public-facing or irreversible → ask the team, don't guess.

## Stack and layout
- `backend/` — Python ≥3.11 (dev machine: 3.13), FastAPI, astropy 8, astroquery, pyvo, reproject, photutils, numpy.
  Env: **uv** — `backend/pyproject.toml` + `backend/uv.lock`, Python pinned by `backend/.python-version` (3.13).
  Lint/format: **ruff** — `ruff.toml` at the repo root covers `backend/`, `scripts/`, `science/`.
  Types: **mypy --strict** (`backend/pyproject.toml`). Python conventions: skill `.claude/skills/fastapi-backend`.
- `frontend/` — React 19 + Vite 8 + TypeScript, npm. Aladin Lite pinned to **3.8.2** (npm `latest` is a beta).
  Aladin Lite is GPL/LGPL-3 — keep in mind when choosing the repo license.
  Lint: **oxlint**. Frontend conventions: skill `.claude/skills/react-frontend`.
- `science/` — validation scripts/notebooks, `targets.json`, `VALIDATION.md`.
- `scripts/prebake.py` — builds static bundles for the 5 test targets into `frontend/public/prebaked/`.
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
- DR1 and QR3 sample files both carry pipeline tag `l2b-v27` (consistent calibration).
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
- **HiPS for Aladin** (CDS): `CDS/P/SPHEREx/QR2/D1`…`D6`, `CDS/P/SPHEREx/QR2/color` (order 7, png).
- Pixel 6.2″; 6 detectors = 6 bands (D1 0.75–1.11 µm … D6 4.42–5.00 µm); λ varies across each frame (LVF).
- macOS python.org Python fails HTTPS to IRSA with `CERTIFICATE_VERIFY_FAILED` → run `Install Certificates.command` or use `certifi`.

## Science rules (non-negotiable)
- Compare like with like: the default blink unit is a **per-visit stack per detector** (or all detectors combined),
  never raw single exposures of different λ presented as the same band. Record λ coverage per stack; warn when incomplete.
- Deep-field targets (e.g. R Dra) have no 6-month gaps: split long visits into fixed time bins (default 30 d)
  and cap exposures per bin.
- Propagate catalog positions with proper motion to each frame's `MJD-AVG` (`SkyCoord.apply_space_motion`).
  Stay in ICRS: do NOT transform to GCRS (aberration ≈ 20″). Ignore parallax (≤0.55″, <0.1 px) and say so.
- Background first (ZODI extension or sigma-clipped median), then one shared stretch for every frame of a sequence.
- Reproject to a common north-up TAN grid at native 6.2″/px with bicubic interpolation; upsample only for display.
- FLAGS: mask in stacks, show as overlay, never report a saturated measurement as a number.
- Honesty: WISE 0855 is at the detection limit — show the expected position and S/N or an upper limit, no detection claims
  below 5σ. No Planet Nine claims.

## Git: commits and pushes
- Commit messages are **exactly one line**: English, imperative, ≤72 chars, no body, no trailers.
  Example: `Add visit grouping for SIA results`.
- Commits are **local only**: commit at green checkpoints on your track branch.
- Before every commit, everything you touched is clean: Python — `ruff check`, `ruff format --check`, `mypy`, `pytest`;
  frontend — `npm run build`, `npm run lint` (see Commands).
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
dev dependencies). Setup: `cd backend && uv sync && cd ..` and `cd frontend && npm install && cd ..`.
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
| Add a Python dependency | `cd backend && uv add <pkg>` (dev: `uv add --dev <pkg>`); commit `pyproject.toml` + `uv.lock` |
| View a bundle | `http://localhost:5173/?manifest=/mock/sequence.json` (default) |
| Prebake real targets (from root) | `uv run --project backend python scripts/prebake.py` (Track C, not written yet) |

Use `uv run ... ruff` for checks: it is the locked version. A brew/editor ruff may differ by a patch release
(on 2026-11-14: brew 0.17.4, lock 0.17.5). VS Code Ruff extension: set `"ruff.importStrategy": "fromEnvironment"`.
