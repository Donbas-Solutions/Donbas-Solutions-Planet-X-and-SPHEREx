# Промпт для Claude Code: SPHEREx Blink

**Як користуватися.** Phase 0, Phase 0.5 і перші дві хвилі треків уже в `main` (PR #1–#15). Команда з 4 людей, кожен бере
одну роль і робить її фічі по черзі, кожну в окремій короткій гілці від свіжого `main` (див. «Roles and ownership —
round 3»), з PR одразу по завершенні. У своїй сесії Claude Code пишіть:

> Read `CLAUDE.md` and `docs/agent-prompt.md`, then execute **Track X, round 3**. Stop at every checkpoint.

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
  archive/        Track A — sia.py, visits.py, cutouts.py, http.py, collections.py, ranges.py, fetch.py, resolve.py,
                  gaia.py (all done); naive.py (only for scripts/fetch_sample.py)
  pipeline/       Track C — sequence.py (build_sequence), bundle.py (write_bundle), photometry.py, variability.py (done)
  jobs.py         Track A — job runner (done)
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
uv + ruff + mypy, Commands in `CLAUDE.md`. Aladin rendering was verified in a real browser on 2026-11-15.

### Phase 0.5 — done (the A/C seam)
`domain.py`, `astrometry.py`; archive building blocks with tests on recorded SIA responses and a real stripped cutout
(`tests/fixtures/cutout_barnard_qr3_d3.fits`); temporary `archive/naive.py` + `scripts/fetch_sample.py`;
`pipeline/bundle.py`; stubs `archive/fetch.py` (A) and `pipeline/sequence.py` (C).

Measured on 2026-11-14: the IRSA cutout service answered **503** to many requests at 4 parallel workers; with
2 workers and patient retries a cutout takes **~6 s**, so the full depth of one target (360–470 exposures) is
**~20 min**. A real Barnard sample (3 visits × 6 detectors × 2) came back with shapes 129×128, 106×129, 56×128.

### Status after round 2 (2026-11-14, 20:30) — what is already in `main`
- **A:** live API (#9): background jobs, `/api/sequence` (200 cached | 202 job), `/api/jobs/{id}`, `/api/resolve`
  (SIMBAD + Harvard mirror, short designations like `WISE 0855-0714`), `/api/health`; 30 s collection-discovery limit.
  Target spectra (#15): every job measures the target's photometry; `/api/spectrum` and `/api/lightcurve` serve it
  (`404` until a sequence of that target has finished). Only `/api/overlays` still answers **501**.
  M1 checked off-line: recorded SIA → S3 → process pool → bundle reproduced Barnard 1.65 px / ε Indi B 1.07 px
  (expected 1.67 / 1.05) in 117 s / 88 s from an empty cache; A ran Barnard live end to end (368 s).
- **B:** live mode (#13: cached jobs on reload, no-coverage state, partial-data wording), About + glossary tooltips
  (#14, FR-15, spec §5.5), combined playlist keeps visits missing detectors (#7).
- **C:** absolute LVF-channel coverage warning (#11: capped live stacks always get `incomplete_lambda`);
  matched-λ variability between visits (#12: `pipeline/variability.py`, light-curve line, RW Aur D1 ×2.43 at
  12.5σ; ε Indi B and WISE 0855 ≤ 2σ).
- **D:** spectrum chart (#8, FR-16) and light-curve chart (#10, FR-17: visit means, χ² against constant).
- Milestones: **M1 ✓** (live API; SIA live check depends on IRSA uptime), **M2 ✓** (offline end to end with charts),
  **M3 🟡** (Aladin context, Gaia markers, README and submission open).
- IRSA was unstable on 2026-11-14 (SIA/TAP `502` or hanging for minutes): prebaked bundles are the demo path.

### Status of round 3 (2026-11-15, 11:00 UTC)
Done — in `main`: `fix/spectrum-store` (#17: expired spectra replaced, race-free writes, a hung TAP waited out once).

Done — on `feat/gaia-overlays` (pushed, not merged into `main` yet):
- **FR-18 complete:** `/api/overlays` (Gaia DR3 at the frame epoch; MAST → GAVO → ESA) and the "Gaia DR3 stars"
  overlay in the player (`gaia=1`). Barnard and ε Indi B markers land within 0.01 px of `expected_px`.
- **FR-19 working:** context panel with 2MASS / AllWISE / DSS2 from the IRSA HiPS mirror (CDS is down), survey
  selector, Gaia stars, outage message. The SPHEREx mosaic is offered only while CDS answers.
- Live search survives a flapping IRSA (SIA answers kept per collection); unique names for deep-field bins;
  partial-data note scoped to the frames on screen; error boundary.
- Checked in a real browser: all five presets and user-found targets (Teegarden's star, raw coordinates,
  Wolf 359), offline mode, embed, every URL parameter (FR-5), FOV limits and detector switching without refetch
  (FR-4), first frame and render time (NFR-1). Every P0 requirement (FR-1 … FR-15) is implemented.
- FOV-limit notice kept in the page banner; a preset searched live at another FOV; notice for unknown `a`/`b`.

Still open, in order of importance:
1. **Merge `feat/gaia-overlays`** and tell the team about the contract changes (`GaiaStar.source_id` is a string,
   `unavailable` always lists `skybot`, new page parameter `gaia`).
2. **Submission (C):** repository public + licence (OD-2, GPL/LGPL-3-compatible), Team Owner and Kyiv cutoff
   confirmed, README (local run on macOS and Windows, screenshots, limitations, credits, AI-use disclosure), video
   ≤ 30 s or ≤ 7 slides, submission text, links tested in a private window.
3. **Clean-clone test on Windows** from the README (B), screenshots and GIFs.
4. **FR-16 acceptance (C):** one unsaturated star against IRSA's Spectrophotometry Tool (ratio 0.8–1.25); only the
   2MASS sanity check exists.
5. **When IRSA is stable:** M1 live numbers for Barnard and ε Indi B (A); regenerate the RW Aur (cap 10) and R Dra
   (cap 3) bundles with fuller depth and rerun `science/validate.py` so `VALIDATION.md` matches (C).
6. **Not started, drop first:** FR-20 measured proper motion in the UI (it exists only in `VALIDATION.md`), FR-22
   AllWISE old-epoch frame, FR-21 embed acceptance (the view works; "copy embed code" is missing), optional error
   `code` in `JobStatus`.
7. Not checked: narrow screens (< 768 px), browsers other than Chrome, and the "no SPHEREx coverage" state
   (FR-13; it needs a sky position without images and a working IRSA).
8. Only if the site is ever hosted (NFR-1): every frame of a sequence is loaded before the first one is shown.
   Locally a preset appears in 0.25–0.33 s (R Dra 1.2 s). Over a 20 Mbit/s link the 1.6–2.0 MB bundles take
   under 1 s, but R Dra's 4.6 MB about 3 s: it needs the on-demand loading that NFR-2 mentions.

The round-3 track lists below are kept as written on 2026-11-14; this section overrides them where they differ.

### Roles and ownership — round 3

| Role | Who | Feature branches (in order) | Owns | Mission now |
|---|---|---|---|---|
| **A — Archive & API** | the A person | `fix/spectrum-store` → `feat/gaia-overlays` | `backend/app/archive/`, `jobs.py`, `main.py`, `config.py`; contract files | Spectrum-store fixes, Gaia overlays, live M1 numbers |
| **B — Frontend core** | the B person | no new feature branch; `docs/…` screenshots with C | app shell, state, URL, player, panels, `package.json` | Support D (Aladin), Windows clean-clone test, screenshots/GIFs |
| **C — Science & delivery** | the team lead | `fix/prebake-discovery-timeout` → `test/fr16-spectrophotometry` → `docs/readme-and-pitch` | `backend/app/pipeline/`, `science/`, `scripts/prebake.py`, `frontend/public/prebaked/`, README, pitch | Decisions, README and submission |
| **D — P1 features** | the new person | `feat/aladin-context` → `feat/gaia-markers` | `frontend/src/components/{charts,context,embed}/` (+ their `lib/` helpers) | Aladin context panel, then Gaia markers |

Shared: `domain.py` (A + C), `CLAUDE.md`, `docs/spec.md`, `docs/api.md` (announce changes). B and D share the
frontend: D only touches its component folders and reads app state through B's hooks; anything else goes through B.

### Track A — round 3
1. `fix/spectrum-store` — follow-ups from the #15 review: overwrite the per-target spectrum when the existing file is
   older than the TTL (today an expired, larger spectrum blocks a fresh smaller one → `404`); give `_write_atomic` a
   unique temp name (two jobs of one target share `<target>.part`).
2. When IRSA is stable: run M1 live for Barnard and ε Indi B and post the numbers, including the `/api/spectrum`
   response (Barnard: every point `saturated: true`, `flux_ujy: null`).
3. `feat/gaia-overlays` (P1) — `/api/overlays` (Gaia DR3 propagated to the frame epoch) for D's Gaia markers (FR-18).
4. Optional (contract change, announce it): an error `code` in `JobStatus`, so the frontend stops matching the
   "no coverage" message by text.

### Track B — round 3
1. Review and support D's Aladin PR (state hooks, layout).
2. **Clean-clone test on Windows** from the README alone (acceptance of C's `docs/readme-and-pitch`): report every
   step that fails.
3. Screenshots and GIFs for the README and the video (prebaked targets: ε Indi B diff, Barnard blink, RW Aur light
   curve), with C.

### Track C — round 3
1. **Decisions (no branch), first:** the repo becomes public before submission (it is the "link to final project")
   and its licence (OD-2, GPL/LGPL-3-compatible because of Aladin); confirm the Team Owner who clicks "Submit" and
   whether the Kyiv Local Lead set an earlier cutoff.
2. `fix/prebake-discovery-timeout` (ready locally) — 30 s TAP limit in `scripts/prebake.py`, `validate.py` keeps a
   target's last section when IRSA fails, regenerated `science/VALIDATION.md` (matched-λ table for T-4).
3. `test/fr16-spectrophotometry` — FR-16 acceptance: one unsaturated star against IRSA's Spectrophotometry Tool
   (ratio 0.8–1.25).
4. `docs/readme-and-pitch` — README (what, how, **local run on macOS and Windows**, screenshots/GIFs, limitations,
   credits NFR-10, AI-use disclosure), licence (OD-2), pitch script, video ≤ 30 s from a local run, submission text.
5. Optional, when IRSA is stable: regenerate the RW Aur and R Dra bundles so they carry the #11 warnings.

### Track D — round 3
1. `feat/aladin-context` — **Context panel** (FR-19), with a HiPS mirror fallback (CDS `alasky` was down on
   2026-11-14; `irsa.ipac.caltech.edu/data/hips/CDS/…` answered): Aladin Lite (`components/AladinPanel.tsx`) synced
   to target and FOV; SPHEREx colour HiPS, AllWISE, 2MASS; Gaia DR3 via VizieR. Verify in a real browser (WebGL).
2. `feat/gaia-markers` (P1, needs A's `/api/overlays`) — Gaia sources in the player (FR-18).
3. AllWISE frame (FR-22) and embed (FR-21) only if everything else is done.

### Who waits for whom — round 3
| Who | Waits for | Meanwhile |
|---|---|---|
| D (Gaia markers) | A's `/api/overlays` | Aladin panel |
| B (clean-clone test) | C's README draft | review D, screenshots |
| C (repo public, submission) | team decisions; features frozen | README, FR-16 check, video script |
| A (live M1 numbers) | IRSA uptime | spectrum-store fixes, overlays |

### Integration and git
- **One short-lived branch per feature**, named like a commit (`feat/…`, `fix/…`, `chore/…`, `docs/…`, `test/…`) and
  created from a fresh `main`: `git switch -c feat/spectrum-chart origin/main`. Open the PR as soon as the feature is
  green; the team lead merges. Then start the next branch from the updated `main`. The old `track-*` branches are
  retired.
- Start every work round with `git pull origin main` into your branch (merge; never rebase pushed commits).
- Lockfile conflicts: regenerate (`uv lock`, `npm install`), never merge by hand. Ask before adding a dependency.
- Contract changes only through A, announced in the team chat; `domain.py` changes agreed by A and C.
- Pushes only when the human you work with explicitly says so (`CLAUDE.md` → Git).

### Timeline — round 3
| When (2026-11-14/15) | Milestone |
|---|---|
| Sat night | ✓ M1 live API, live mode, spectrum and light-curve charts, matched-λ variability |
| Sun morning | Aladin panel; Gaia overlays/markers if on time; README draft; team decisions (repo public, licence, Team Owner) |
| Sun midday | **Feature freeze** → clean-clone test on Windows from the README → GIFs/screenshots → video |
| Sun afternoon | Repo public, submission text final, links tested in a private window |
| Sun 23:59 Kyiv (21:59 UTC) | Submission by the Team Owner — aim for well before |

If time runs short, drop in this order: FR-21 (embed) → FR-22 (AllWISE) → FR-18 (Gaia markers) → FR-19 (Aladin). Never drop FR-3 / FR-14 (prebaked bundles) or the README local-run instructions.

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
