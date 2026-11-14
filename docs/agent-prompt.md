# Промпт для Claude Code: SPHEREx Blink

**Як користуватися.** Phase 0, Phase 0.5 і перша хвиля треків уже в `main` (PR #1–#4). Команда з 4 людей, кожен бере
одну роль і робить її фічі по черзі, кожну в окремій короткій гілці від свіжого `main` (див. «Roles and ownership —
round 2»), з PR одразу по завершенні. У своїй сесії Claude Code пишіть:

> Read `CLAUDE.md` and `docs/agent-prompt.md`, then execute **Track X, round 2**. Stop at every checkpoint.

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
  archive/        Track A — sia.py, visits.py, cutouts.py, http.py, collections.py, ranges.py, fetch.py (done); naive.py (temporary)
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

### Status after round 1 (2026-11-14, 18:20) — what is already in `main`
- **A:** A0 spike (`docs/a0-fetch-spike.md`), A1 SIA + TAP collection discovery, A2 async fetcher (S3 → `ibe` →
  cutout service), bundled-spectrum contract (`meta.spectrum`). Not yet: jobs, and all five API endpoints still answer
  **501**.
- **B:** app shell, URL state, presets, search box, blink player (A/B, diff, stretch, zoom, expected position), flags
  overlay, frame metadata, pixel readout, job polling, offline fallback, About page.
- **C:** pipeline (`build_sequence`, positions, photometry), 5 static bundles with spectra and GIFs,
  `science/VALIDATION.md` (T-1 ✓, T-2 ✓, FR-16 vs 2MASS ✓, T-3 motion ✓ / flux blended, T-4/T-5 saturated),
  structured frame warnings (`{code, message}`, PR #4).
- **D:** OD-3 settled and hosting proposed in `docs/deploy.md` (PR #6): deadline **Sun 2026-11-15 23:59 Kyiv
  (21:59 UTC)**, demo = video ≤ 30 s or ≤ 7 slides, AI-use disclosure, no NASA branding; hosting = **Netlify**
  (frontend + bundles at the domain root, proxies `/api/*` and `/files/*`) + **Hugging Face Spaces, Docker** (backend).
  **Then decided: no deploy for the submission** (not required) — local runs only; the public GitHub repo is the
  "link to final project" (OD-1 deferred).
  Spectrum / Light curve / Context tabs are still placeholders.
- Milestones: **M1 ✗** (no live API), **M2 🟡** (offline part works end to end), **M3 ✗**.

### Roles and ownership — round 2

| Role | Who | Feature branches (in order) | Owns | Mission now |
|---|---|---|---|---|
| **A — Archive & API** | the A person | `feat/live-sequence-api` → `feat/spectrum-api` → `feat/gaia-overlays` | `backend/app/archive/`, `jobs.py`, `main.py`, `config.py`; contract files | Live API (M1) |
| **B — Frontend core** | the B person | `feat/live-mode` → `fix/diff-default-and-about` | app shell, state, URL, player, panels, `package.json` | Live mode, fixes, support D |
| **C — Science & delivery** | the team lead | `test/fr16-spectrophotometry` → `docs/readme-and-pitch` | `backend/app/pipeline/`, `science/`, `scripts/prebake.py`, `frontend/public/prebaked/`, README, pitch | Spectrum endpoint with A, FR-16 acceptance, **README (local run) and submission** |
| **D — P1 features** | the new person | `feat/spectrum-chart` → `feat/light-curve-chart` → `feat/aladin-context` | `frontend/src/components/{charts,context,embed}/` (+ their `lib/` helpers) | Spectrum and light-curve charts, Aladin context panel, embed, Gaia markers |

Shared: `domain.py` (A + C), `CLAUDE.md`, `docs/spec.md`, `docs/api.md` (announce changes). B and D share the
frontend: D only touches its component folders and reads app state through B's hooks; anything else goes through B.

### Track A — round 2
1. `feat/live-sequence-api` — **A3 `jobs.py`** (FR-13): registry keyed by request; background task query → plan → `fetch_cutouts` →
   `build_sequence` in a process pool (`progress=None`) → `write_bundle` into `cache/processed/<key>/`, served at `/files`.
2. same branch — **A4 endpoints**: `/api/sequence` (200 cached | 202 job), `/api/jobs/{id}`, `/api/resolve` (SIMBAD + Harvard mirror,
   FR-2), `/api/health` with discovered collections. **Checkpoint A (M1):** live Barnard and ε Indi B over HTTP.
3. `feat/spectrum-api` — **`/api/spectrum` and `/api/lightcurve`** with C: call `pipeline.photometry.measure_spectrum` on the cutouts of the
   job's plan.
4. `feat/gaia-overlays` (P1) — `/api/overlays` (Gaia DR3 propagated to the frame epoch) for D's Gaia markers (FR-18).

### Track B — round 2
1. `feat/live-mode` — **Live mode** once A4 lands: `/?ra=&dec=` and `/?name=` end to end, job progress, errors (FR-2, FR-13).
2. `fix/diff-default-and-about` — the default diff of ε Indi B uses visit 2026-04 instead of the last visit 2026-09; About says WISE 0855 is
   "not a detection" — update to "motion seen in D5–D6, flux blended with a field star" (`science/VALIDATION.md` T-3).
3. No branch — support D: expose the selected pixel / current frame / sequence through the state hook; review D's PRs.

### Track C — round 2
1. **Decisions (no branch), first:** the repo becomes public before submission (it is the "link to final project")
   and its licence (OD-2, GPL/LGPL-3-compatible because of Aladin); confirm the Team Owner who clicks "Submit" and
   whether the Kyiv Local Lead set an earlier cutoff. OD-3 is done and OD-1 deferred: no deploy (`docs/deploy.md`).
2. On A's `feat/spectrum-api` — `/api/spectrum` + `/api/lightcurve` (C owns the science, A the endpoint).
3. `test/fr16-spectrophotometry` — FR-16 acceptance: one unsaturated star against IRSA's Spectrophotometry Tool (ratio 0.8–1.25).
4. `docs/readme-and-pitch` — README (what, how, **local run on macOS and Windows**, screenshots/GIFs from the bundles,
   limitations, credits NFR-10), licence (OD-2), pitch script and video recorded from a local run, submission text.
   Acceptance: a teammate on another machine (ideally Windows) clones the repo and runs it from the README alone.

### Track D — round 2
One branch per feature, from a fresh `main`; develop against the bundles: `/?target=eps_ind_b` (spectrum in `meta.spectrum`).
1. `feat/spectrum-chart` — **Spectrum chart** (FR-16): flux vs λ from `spectrum.json` / `/api/spectrum`, errors, coloured by visit;
   saturated points as hollow markers labelled "saturated", never as values (SR-6). One small chart library, lazy-loaded
   (ask before adding it).
2. `feat/light-curve-chart` — **Light-curve chart** (FR-17): flux vs time per detector from the same points.
3. `feat/aladin-context` — **Context panel** (FR-19), with a HiPS mirror fallback (CDS `alasky` was down on
   2026-11-14; `irsa.ipac.caltech.edu/data/hips/CDS/…` answered): Aladin Lite (`components/AladinPanel.tsx`) synced to target and FOV; SPHEREx colour HiPS,
   AllWISE, 2MASS; Gaia DR3 via VizieR. Verify in a real browser (WebGL).
4. P1 if time allows: Gaia markers in the player (FR-18, needs A's `/api/overlays`), AllWISE frame (FR-22).
   Embed (FR-21, `feat/embed-view`) is last: without a hosted URL nobody can embed it.

### Who waits for whom — round 2
| Who | Waits for | Meanwhile |
|---|---|---|
| B (live mode) | A4 | fixes, support D |
| D | nothing — data are in the bundles | charts and Aladin on `/?target=…` |
| C (README, local-run test) | features merged | FR-16 check, README draft, decisions |
| C + A (`/api/spectrum`) | A3 | — |

### Integration and git
- **One short-lived branch per feature**, named like a commit (`feat/…`, `fix/…`, `chore/…`, `docs/…`, `test/…`) and
  created from a fresh `main`: `git switch -c feat/spectrum-chart origin/main`. Open the PR as soon as the feature is
  green; the team lead merges. Then start the next branch from the updated `main`. The old `track-*` branches are
  retired.
- Start every work round with `git pull origin main` into your branch (merge; never rebase pushed commits).
- Lockfile conflicts: regenerate (`uv lock`, `npm install`), never merge by hand. Ask before adding a dependency.
- Contract changes only through A, announced in the team chat; `domain.py` changes agreed by A and C.
- Pushes only when the human you work with explicitly says so (`CLAUDE.md` → Git).

### Timeline — round 2
| When (2026-11-14/15) | Milestone |
|---|---|
| Sat evening | OD-3 settled; no deploy (OD-1); A3 started; D charts started |
| Sat night | **M1** live API for Barnard and ε Indi B |
| Sun morning | Live mode in the UI; spectrum/light-curve charts and Aladin; README |
| Sun midday | Feature freeze → clean-clone test from the README on another machine → GIFs/screenshots → video → repo public |
| Sun 23:59 Kyiv (21:59 UTC) | Submission by the Team Owner — aim for well before |

If time runs short, drop in this order: FR-21 (embed) → FR-22 (AllWISE) → FR-18 (Gaia markers) → FR-19 (Aladin) →
FR-17 (light curves). Never drop FR-3 / FR-14 (prebaked bundles) or the README local-run instructions.

## 6. Working rules
- **Checkpoints:** stop and report in Ukrainian using: *Зроблено / Як перевірено (команди + реальний вивід) /
  Відхилення від плану / Ризики та питання / Наступний крок.* Wait for "go".
- Verify against real data, not just mocks; paste real numbers. If something cannot be verified, say so plainly.
- Commit locally at each green checkpoint on your track branch, following the Git section of `CLAUDE.md`
  (one-line Conventional Commits, e.g. `feat(pipeline): …`; push only when explicitly told to). Never deploy or create accounts without a human OK.
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
