# SPHEREx Blink — NASA Space Apps 2026 "Planet X and SPHEREx"

Public web tool: the user enters RA/Dec (or an object name) and gets an animated sequence (blink / flipbook)
of NASA SPHEREx images of that sky patch, so moving and variable objects stand out.

- Hackathon: submission deadline **2026-11-15**. Team of 3–4, parallel Claude Code sessions, one per track.
- Plan, tracks, priorities, API contract: `docs/agent-prompt.md` (source of truth for *what* to build).
- Challenge text: `docs/project_info.md`. Background research: `docs/spherex-research.md`.
  The research doc is **partly outdated**: where it disagrees with "Verified data facts" below, this file wins.

## Communication
- Reports to the team: **Ukrainian**. Code, comments, identifiers, commit messages, API: English.
- Scope cuts, hosting, accounts, anything public-facing or irreversible → ask the team, don't guess.

## Stack and layout
- `backend/` — Python ≥3.11, FastAPI, astropy, astroquery, pyvo, reproject, photutils, numpy, Pillow. Env: `uv` (fallback: venv + pip).
- `frontend/` — React + Vite + TypeScript, Aladin Lite v3 (npm `aladin-lite`, pinned to an exact version).
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
<!-- Phase 0 fills this in: install, run backend, run frontend, tests, prebake. -->
