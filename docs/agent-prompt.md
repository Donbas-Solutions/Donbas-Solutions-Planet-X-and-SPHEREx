# Промпт для Claude Code: SPHEREx Blink

**Як користуватися.** Phase 0 і Phase 0.5 вже виконано. Команда з 4 людей: кожен бере одну роль (A, B, C, D),
відкриває свою сесію Claude Code на своїй гілці (`track-a-archive`, `track-b-frontend`, `track-c-science`,
`track-d-delivery`) і пише:

> Read `CLAUDE.md` and `docs/agent-prompt.md`, then execute **Track X**. Stop at every checkpoint.

Сам промпт нижче — англійською. Звіти агент пише українською.

---

## 0. Mission

You are a senior engineer on a 4-person team at NASA Space Apps 2026, challenge **"Planet X and SPHEREx"**.
Deadline: **2026-11-15**. Build a **public-facing web tool**: a user enters sky coordinates (RA/Dec) or an object name
and sees a series of NASA SPHEREx images of that patch as a short animation, so moving and variable objects are easy to spot.

Judges will compare dozens of blink viewers. We win on: **correct science on the 5 official test targets, honest
limitations, and the "Potential Considerations" done well** (stack/diff, spectra on the fly, overlays, URL/embed, flags).
A working, honest P0 beats an ambitious broken P2.

Read before acting: **`docs/spec.md`** (requirements with IDs and acceptance criteria — the source of truth for *what*
to build), `CLAUDE.md` (verified facts, science and engineering rules), `docs/api.md` (contract),
`docs/project_info.md` (challenge text), `docs/spherex-research.md` (background). This file is the **plan**: order of
work, tracks, checkpoints. Where it seems to disagree with the spec, the spec wins — flag the conflict.

## 1. Priorities

Defined in `docs/spec.md` §4: **P0** = FR-1 … FR-15 (must work at M2), **P1** = FR-16 … FR-22 (Sunday morning),
**P2** = FR-23 … FR-27 (only if P0 and P1 are solid). Science rules SR-1 … SR-7, test-target acceptance T-1 … T-5,
non-functional NFR-1 … NFR-11. Reference these IDs in checkpoint reports.

## 2. Architecture

```
browser (React + Aladin Lite)            backend (FastAPI)                         external
 ├─ form / URL state ──────────► GET /api/sequence ─► resolve ────────────────────► SIMBAD (+ mirror)
 ├─ player (canvas, Float32)  ◄── job id / progress   [A] query → visits → fetch ──► IRSA TAP / SIA2 / cutouts (or S3)
 ├─ diff / stretch client-side                        [C] build_sequence (process pool)
 ├─ charts, context (Aladin)  ◄── /api/spectrum ...   [C] write_bundle → cache/processed → /files
 └─ static fallback: /prebaked/<target>/sequence.json  (written by C's prebake script)
```

Frames travel as **raw little-endian Float32 arrays** (≤290×290 px) plus uint32 flag arrays and a JSON manifest.
Stretch, colormap, diff and sums run **client-side** on a canvas, so contrast sliders are instant and the same files
work for the live API and the static bundles.

### Backend modules and the A/C seam

```
backend/app/
  domain.py       shared types — Target, ExposureMeta, Visit, Cutout, SequenceParams, FrameArrays, SequenceResult
  astrometry.py   proper-motion propagation (SR-3)
  archive/        Track A — sia.py, visits.py, cutouts.py (done); naive.py (temporary); fetch.py (to implement)
  pipeline/       Track C — bundle.py (write_bundle, done); sequence.py (build_sequence, to implement)
  jobs.py         Track A — job runner (to create)
  main.py         Track A — endpoints
```

Flow: `Target` → **A** `query_exposures` → `group_visits` → `cap_per_detector` → `fetch_cutouts` → `list[Cutout]`
→ **C** `build_sequence` → `SequenceResult` → `write_bundle` (prebake) or `cache/processed/<key>/` served at `/files` (API).

Facts every track must respect (details in `CLAUDE.md`):
- An exposure's `obs_id` is shared by two detectors: the unique key is `ExposureMeta.key` = (obs_id, detector).
- Cutout shapes differ between exposures: IRSA truncates cutouts at detector edges instead of padding them.
  Every array inside one `Cutout` has the same shape; C reprojects everything onto the common grid.
- `Cutout.wavelength_um` / `bandwidth_um` are per-pixel LVF maps already evaluated from the spectral WCS (key `W`).

## 3. API contract

The authoritative contract is **`docs/api.md`**, mirrored by `backend/app/models.py` and `frontend/src/api/types.ts`
(`backend/tests/test_contract.py` checks the mock bundle against it). Do not restate it here.

## 4. Test targets

Acceptance criteria: `docs/spec.md` §6.2 (T-1 … T-5). Catalog values (SIMBAD J2000 + proper motion, with the epoch of
the challenge coordinates): `science/targets.json`. Recorded SIA responses of all five: `backend/tests/fixtures/sia/`.

## 5. Plan

### Phase 0 — done
Skeletons (FastAPI with `/api/health` and validated 501 stubs; Vite + React + TS with a Float32 frame renderer and a
lazy Aladin panel), contract `docs/api.md`, mock bundle `frontend/public/mock/`, `science/targets.json`,
uv + ruff + mypy, Commands in `CLAUDE.md`. Not yet verified: Aladin rendering in a real browser.

### Phase 0.5 — done (the A/C seam)
`domain.py`, `astrometry.py`; archive building blocks with tests on recorded SIA responses and a real stripped cutout
(`tests/fixtures/cutout_barnard_qr3_d3.fits`); temporary `archive/naive.py` + `scripts/fetch_sample.py`;
`pipeline/bundle.py`; stubs `archive/fetch.py` (A) and `pipeline/sequence.py` (C).

Measured on 2026-11-14: the IRSA cutout service answered **503** to many requests at 4 parallel workers; with
2 workers and patient retries a cutout takes **~6 s**, so the full depth of one target (360–470 exposures) is
**~20 min**. A real Barnard sample (3 visits × 6 detectors × 2) came back with shapes 129×128, 106×129, 56×128.

### Roles and ownership

| Track | Branch | Owns | Ask before touching |
|---|---|---|---|
| **A — Archive & API** | `track-a-archive` | `backend/app/archive/`, `jobs.py`, `main.py`, `config.py`, Dockerfile; contract files `docs/api.md`, `models.py`, `frontend/src/api/types.ts` | `pipeline/` |
| **B — Frontend core** | `track-b-frontend` | `frontend/` app shell, state, URL, player, panels; `package.json` | `components/{context,charts,embed}/` |
| **C — Science pipeline** | `track-c-science` | `backend/app/pipeline/`, `astrometry.py`, `science/`, `scripts/prebake.py`, `frontend/public/prebaked/` | `archive/` |
| **D — P1 features & delivery** | `track-d-delivery` | `frontend/src/components/{context,charts,embed}/`, `README.md`, deploy config, pitch material | B's state and player internals |

Shared: `domain.py` (A and C agree on every change), `CLAUDE.md`, `docs/spec.md` (announce changes).

### Track A — Archive & API
- **A0 spike (≤45 min; decides OD-4, OD-5).** Measure for Barnard: (a) cutout service at 1, 2, 3 workers —
  latency, MB/s, 503 rate, `Retry-After` behaviour; whether `EPSF` can be dropped server-side; (b) S3
  `nasa-irsa-spherex` (same paths as IRSA, ~65 MB per file, HTTP ranges supported): `fits.open(..., use_fsspec=True)`
  + `.section` for `IMAGE/FLAGS/VARIANCE/ZODI` — FITS rows are contiguous, so a 128-px window reads ~1 MB per
  extension, or many small per-row ranges; (c) HTTP range reads on the IRSA `ibe` URL. Report a table of
  bytes / time / reliability per method and recommend one. **Checkpoint A0.**
- A1 `archive/fetch.query_exposures`: async SIA for the collections discovered via TAP (cached 6 h, fallback
  `settings.fallback_collections`); reuse `sia.parse_sia_csv` (NFR-3).
- A2 `archive/fetch.fetch_cutouts`: shared `httpx.AsyncClient`, semaphore (start at 2 given the 503s), retries with
  backoff, jitter and `Retry-After`, atomic cache writes (`strip_to_file`), `load_cutout` in a worker thread,
  progress; failed exposures reported, not fatal. Same output as `naive.fetch_sample` (NFR-5).
- A3 `jobs.py`: registry keyed by request (sorted image keys of the plan + FOV + detectors); background task:
  query → plan → fetch → `build_sequence` in a process pool → `write_bundle` into `cache/processed/<key>/` (FR-13).
  Until C delivers `build_sequence`, test with a trivial stand-in that stacks nothing.
- A4 endpoints: `/api/sequence` (200 cached | 202 job), `/api/jobs/{id}`, `/api/resolve` (SIMBAD + mirror, FR-2),
  `/api/health` with discovered collections. **Checkpoint A (M1):** live Barnard and ε Indi B sequences via HTTP.
- A5 (P1, FR-18, FR-25) `/api/overlays`: Gaia DR3 cone propagated to the frame epoch; SkyBoT with cache and graceful failure.
- A6 Dockerfile, raw-cache LRU cap, deployment together with D (NFR-4).
- Backup duty: if C is behind at M2, A takes the photometry of FR-16 / FR-17.

### Track B — Frontend core
- **B0 (first hour; push on a human OK — D depends on it).** App shell with layout slots per spec §5.1: tabs
  *Spectrum* / *Light curve* / *Context*, route `/embed`, and a small shared state hook D can read (target, current
  frame, selected pixel, sequence).
- B1 (FR-1 … FR-5) URL ↔ state per spec §5.3; input parsing (decimal/sexagesimal), name resolve, presets.
- B2 (FR-7 … FR-10) canvas player on Float32: stretch (asinh/linear/log + sliders), colormaps (grey; diverging
  blue–orange for diff), play/pause/fps/step/slider, A/B blink, zoom with `image-rendering: pixelated`, expected-position
  marker, keyboard (Space, ←/→, B); fps cap and `prefers-reduced-motion` per spec §5.4.
- B3 (FR-13, FR-14) data layer: job polling with progress; fallback live API → `/prebaked/<target>/` → offline banner;
  all states of spec §5.2; develop on `/mock/`.
- B4 (FR-11, FR-12) metadata panel, warnings, FLAGS overlay by group. **Checkpoint B (M1):** mock, then live, end to end.
- B5 (FR-15) About / limitations page with data credits (NFR-10).

### Track C — Science pipeline
- **C0 (now).** Real data without waiting for A:
  `uv run --project backend python scripts/fetch_sample.py barnard eps_ind_b --max-per-detector 4`. Read the IRSA
  `spherex-intro` tutorial; the λ maps are already in `Cutout`.
- C1 (SR-1 … SR-6) `pipeline/`: per-exposure background (ZODI, then residual median) and mask
  (`flags.stack_mask_bits`); reprojection onto `grid.make_grid` (bicubic; flags nearest + OR); per-visit
  inverse-variance stacks per detector and all detectors; λ coverage and warnings; `expected_px` via
  `astrometry.position_at`; shared stretch → `build_sequence`. Show PNG/GIF of the Barnard and ε Indi B differences
  (T-1, T-2). **Checkpoint C1** — A wires it into the jobs (M1).
- C2 (FR-3, FR-14) `scripts/prebake.py`: full-depth fetch + `build_sequence` + `write_bundle` →
  `frontend/public/prebaked/<target>/` for all 5 targets, plus GIFs. Full depth is ~20 min per target at today's IRSA
  speed: start it as soon as C1 works and let it run unattended. **Checkpoint C (M2):** the app works on all 5
  targets with the backend off.
- C3 Validation against T-1 … T-5 → `science/VALIDATION.md` (draft by M1, complete by M3).
- C4 (P1, FR-16, FR-17) photometry: forced aperture at the propagated position per exposure, errors from VARIANCE,
  saturated / flagged points marked; data for the spectrum and light curve (wire `/api/spectrum` with A); compare
  with the IRSA Spectrophotometry Tool on one unsaturated star.
- C5 (P1, FR-20) proper-motion measurement with errors vs catalog.

### Track D — P1 features & delivery
- **D0 (first hour).** Settle OD-3 (exact deadline, submission format, AI-use disclosure, branding rules) and propose
  OD-1 (hosting) to the team; deploy the static frontend with mock data as a walking skeleton — accounts and deploys
  only with a human OK.
- D1 (FR-19) context panel in B's slot, reusing `components/AladinPanel.tsx`; verify rendering in a real browser.
- D2 (FR-16, FR-17) spectrum and light-curve charts on a mock `frontend/public/mock/spectrum.json` that matches the
  `Spectrum` model, then real data from C / A.
- D3 (FR-21) embed mode; (FR-18) Gaia markers in the player through B's state hook; (FR-22) AllWISE frame.
- D4 README with credits (NFR-10), GIFs and screenshots from C's prebaked bundles, demo script, video, submission;
  final deploy and clean-browser test (with a human OK).

### Who waits for whom

| Who | Waits for | When | Meanwhile |
|---|---|---|---|
| C | nothing (naive fetcher) | — | — |
| A | C's `build_sequence` for M1 | Checkpoint C1 | jobs with a stand-in |
| B | A's live API | M1 | mock bundle |
| D | B's shell (B0) | +1 h | OD-3, OD-1, deploy skeleton |
| D | C's spectrum data | M3 | mock spectrum |
| everyone | C's prebaked bundles | M2 | mock bundle |

### Integration and git
- Each track works on its own branch. Integration into `main` via PR at M1, M2, M3 and the freeze; the integrator is
  the team lead or Track D.
- Start every work round with `git pull origin main` into your branch (merge; never rebase pushed commits).
- Lockfile conflicts: regenerate (`uv lock`, `npm install`), never merge by hand.
- Contract changes only by A, announced in the team chat; `domain.py` changes agreed by A and C.
- Pushes only when the human you work with explicitly says so (`CLAUDE.md` → Git).

### Timeline
| When (2026-11-14/15) | Milestone |
|---|---|
| Sat afternoon | Phase 0.5 done; tracks start |
| Sat evening | **M1** — live blink + diff for Barnard and ε Indi B in the browser |
| Sat night | **M2** — all P0, 5 targets prebaked, static fallback works |
| Sun morning | **M3** — P1 features, `VALIDATION.md` complete |
| Sun midday | Feature freeze → deploy (with human OK) → clean-browser test → GIFs/screenshots |
| Before deadline | Submission (Track D) |

If M1 slips by >2 h, drop P1 items in this order: FR-22 (AllWISE) → FR-17 (light curves) → FR-16 (spectrum) →
FR-18 (Gaia). Never drop FR-3 / FR-14 (prebaked bundles).

## 6. Working rules
- **Checkpoints:** stop and report in Ukrainian using: *Зроблено / Як перевірено (команди + реальний вивід) /
  Відхилення від плану / Ризики та питання / Наступний крок.* Wait for "go".
- Verify against real data, not just mocks; paste real numbers. If something cannot be verified, say so plainly.
- Commit locally at each green checkpoint on your track branch, following the Git section of `CLAUDE.md`
  (one-line messages; push only when explicitly told to). Never deploy or create accounts without a human OK.
- Before each commit: ruff check + ruff format + mypy + pytest clean for Python, `npm run build` + `npm run lint` for
  the frontend. Python deps only via `uv add` (commit `uv.lock`); never `pip install` into the env by hand.
- Ask before: changing the API contract or `domain.py`, adding a heavy dependency, cutting a P0 item, anything public-facing.
- Keep it simple: no auth, no database (disk cache + JSON), no microservices.
- Tests: pytest for pure logic; recorded fixtures instead of the network (`-m network` for live checks); a smoke test
  that the 5 prebaked manifests load. No exhaustive UI tests.

## 7. Risks and fallbacks
| Risk | Mitigation |
|---|---|
| IRSA slow or returning 503 (measured: ~6 s per cutout at 2 workers) | prebake early and unattended (C2); low concurrency with backoff; S3 path if A0 shows it is faster |
| IRSA down during the demo | prebaked bundles (FR-3, FR-14); cached processed results |
| ~4 MB per cutout (EPSF not trimmed) | A0: S3 / range reads; per-group caps; cache processed, not raw |
| λ differences fake brightness changes | per-visit stacks per detector; λ coverage warnings (SR-1) |
| Sub-pixel motion invisible | longest baseline (first vs last visit), diff mode, upsampled display, AllWISE old epoch |
| Saturation on Barnard / R Dra | FLAGS overlay; "saturated" labels instead of numbers; ε Indi B for PM measurement |
| WISE 0855 not detected | expected-position marker + honest S/N / upper limit |
| External APIs (SkyBoT, Gaia, SIMBAD) fail | caches, short timeouts, UI shows "unavailable" instead of breaking |
| Integration breaks at a milestone | seam fixed in `domain.py` + contract tests; PR per milestone, not one big merge |
