# Промпт для Claude Code: SPHEREx Blink

**Як користуватися.** Phase 0 уже виконано (коміти `07c4e26`, `fca9366`). Кожен учасник відкриває свою сесію на своїй гілці (`track-a-backend`, `track-b-frontend`, `track-c-science`) і пише:

> Read `CLAUDE.md` and `docs/agent-prompt.md`, then execute **Track X**. Stop at every checkpoint.

Сам промпт нижче — англійською. Звіти агент пише українською.

---

## 0. Mission

You are a senior engineer on a 3–4 person team at NASA Space Apps 2026, challenge **"Planet X and SPHEREx"**.
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
browser (React + Aladin Lite)            backend (FastAPI)                       external
 ├─ form / URL state ──────────► GET /api/sequence ─► 1 resolve ───────────────► SIMBAD
 ├─ player (canvas, Float32)  ◄── job id / progress    2 query (collections, SIA) ► IRSA TAP / SIA2
 ├─ diff / stretch client-side                        3 fetch cutouts + disk cache ► IRSA cutouts (or S3)
 ├─ charts (spectrum, LC)     ◄── /api/spectrum ...   4 process: bg, flags, λ, reproject, stack
 └─ static fallback: /prebaked/<target>/manifest.json 5 serve: Float32 frames + flags + JSON
```

Key design decision: frames travel as **raw little-endian Float32 arrays** (≤290×290 px, ≤340 KB each) plus
uint32 flag arrays and a JSON manifest. Stretch, colormap, diff and sums run **client-side** on a canvas, so
contrast sliders are instant and the same files work for the live API and the static prebaked bundles.

### Backend pipeline (the 5 steps)
1. **Resolve.** Name → ICRS RA/Dec, PM, parallax, reference epoch (SIMBAD via astroquery; cache). Raw RA/Dec → no PM unless given.
2. **Query.** Discover collections (TAP, cached 6 h, fallback env `SPHEREX_COLLECTIONS`); SIA2 for each; dedupe by `obs_id`;
   group by detector (`energy_bandpassname`) and **visit** = time clusters split by gaps > 40 d; clusters longer than
   60 d (deep fields) → fixed 30-d bins. Cap exposures per (detector, bin) via `max_exposures_per_group` (evenly spaced in time).
3. **Fetch.** Cutout size = FOV × 1.3 + motion margin. Disk cache keyed by `(obs_id, round(center, 1e-4°), size)`.
   ≤8 concurrent, retries with backoff, timeout 120 s, progress reported to the job. Raw cache is LRU-capped (default 5 GB).
4. **Process (per exposure).** Subtract background (ZODI extension, fallback sigma-clipped median); build mask from FLAGS
   (bit meanings from the header / IRSA docs — do not guess); evaluate λ at the target pixel from the spectral WCS
   (copy the canonical method from the IRSA `spherex-intro` tutorial source); reproject IMAGE and VARIANCE onto the
   common north-up TAN grid (native 6.2″/px, bicubic). **Per visit:** inverse-variance weighted mean per detector +
   all-detector combination; record λ coverage, N exposures, flag fractions; warn if λ coverage is incomplete
   compared with other visits.
5. **Serve.** Float32 frame files + flag files + manifest; suggested shared stretch (percentiles over all frames);
   cache processed results (small) separately from raw cutouts (large).

## 3. API contract

The authoritative contract is **`docs/api.md`**, mirrored by `backend/app/models.py` and `frontend/src/api/types.ts`
(`backend/tests/test_contract.py` checks the mock bundle against it). Do not restate it here.

## 4. Test targets

Acceptance criteria: `docs/spec.md` §6.2 (T-1 … T-5). Catalog values (SIMBAD J2000 + proper motion, with the epoch of
the challenge coordinates): `science/targets.json`. Track C writes the evidence to `science/VALIDATION.md`.

## 5. Plan

### Phase 0 — done
Skeletons (FastAPI with `/api/health` and validated 501 stubs; Vite + React + TS with a Float32 frame renderer and a
lazy Aladin panel), contract `docs/api.md`, mock bundle `frontend/public/mock/` (`scripts/make_mock.py`),
`science/targets.json` (`science/resolve_targets.py`), uv + ruff + mypy, Commands in `CLAUDE.md`.
Not yet verified: Aladin rendering in a real browser (headless Chrome has no WebGL).

### Track A — backend (`backend/`)
- **A0 spike (≤45 min, before committing to a fetch strategy; decides OD-4, OD-5).** For Barnard, time 20 cutouts
  (latency, MB/s, failures). Check (a) whether the cutout service can drop `EPSF`; (b) S3 reads — already known: prefixes
  `dr1/`, `qr2/`, `qr3/`, same paths as IRSA, ~65 MB per file, HTTP range requests supported; measure
  `astropy.io.fits.open(..., use_fsspec=True)` + `.section` for `IMAGE/FLAGS/VARIANCE` (FITS rows are contiguous: a 97-px
  window still reads ~0.8 MB per extension); (c) HTTP range reads on the IRSA `ibe` URL. Report a table of
  bytes/time/reliability per method and recommend one. **Checkpoint A0.**
- A1 collections discovery + SIA query + visit grouping (SR-2, NFR-3); unit tests on recorded CSV fixtures (all 5 targets).
- A2 fetch + cache + concurrency + progress (NFR-5).
- A3 processing (SR-1, SR-3 … SR-6): background, flags, λ, reprojection, per-visit stacks, all-detector stack. Test with
  saved small fixtures (strip `EPSF` before saving). Show PNG/GIF of Barnard and ε Indi B diffs (T-1, T-2) before A4.
- A4 API with the job model (FR-13), CORS, files endpoint, `/api/resolve` with mirror fallback (FR-2).
  **Checkpoint A (M1):** real Barnard and ε Indi B sequences via HTTP.
- A5 (P1, FR-16, FR-17) spectrum + light curve: forced aperture photometry at the PM-propagated position per exposure
  (photutils, annulus background, VARIANCE errors, skip flagged), surface brightness × pixel solid angle → flux, aperture
  correction from EPSF or empirically; validate against the IRSA Spectrophotometry Tool on one unsaturated star.
- A6 (P1, FR-18, FR-25) overlays: Gaia DR3 cone (epoch 2016.0 → frame mjd), SkyBoT with cache, short timeout, graceful "unavailable".
- A7 Dockerfile, health check, raw-cache LRU cap (NFR-4).

### Track B — frontend (`frontend/`)
- B1 (FR-1 … FR-5) URL ↔ state sync per spec §5.3; input parsing (decimal/sexagesimal), name resolve, presets.
- B2 (FR-7 … FR-10) canvas player on Float32: stretch (asinh/linear/log + sliders), colormaps (grey; diverging
  blue–orange for diff), play/pause/fps/step/slider, A/B blink, zoom with `image-rendering: pixelated`, expected-position
  marker, keyboard shortcuts (Space, ←/→, B); fps cap and `prefers-reduced-motion` per spec §5.4.
- B3 (FR-13, FR-14) data layer: job polling with progress; fallback live API → `/prebaked/<target>/` → offline banner;
  all states of spec §5.2; dev on `/mock/`.
- B4 (FR-11, FR-12) metadata panel, warnings, FLAGS overlay by group. **Checkpoint B (M1):** the mock and then the live
  sequence play end-to-end.
- B5 (P1, FR-19) Aladin Lite panel synced to target/FOV: `CDS/P/SPHEREx/QR2/color`, AllWISE, 2MASS; Gaia DR3 via VizieR (`I/355/gaiadr3`).
- B6 (P1, FR-16, FR-17) spectrum and light-curve charts (one small chart lib), saturated points drawn hollow and labelled.
- B7 (P1, FR-21) `/embed?...` minimal mode + "copy embed code".
- B8 (FR-15) About/limitations page with data credits (NFR-10).

### Track C — science and prebake (`science/`, `scripts/`)
- C1 `targets.json` (done in Phase 0); add expected shifts per visit pair.
- C2 Validation runs on all 5 targets against T-1 … T-5 → `science/VALIDATION.md` (draft by M1, complete by M3).
- C3 (FR-3, FR-14) `scripts/prebake.py` → `frontend/public/prebaked/<target>/` (manifest + frames) + GIFs for the pitch.
  **Checkpoint C (M2):** the app works on all 5 targets with the backend off.
- C4 (P1, FR-20) proper-motion measurement: centroid per visit stack, linear fit over time → μ with errors vs catalog.
- C5 (P1, T-3) WISE 0855: D5–D6 stack S/N at the expected position or a 5σ upper limit; AllWISE frame (FR-22) for comparison.

### Track D — pitch (humans; Claude assists on request)
README (what, how, screenshots, limitations, credits), demo script, project description, video. Check the Space Apps
Participant Guides for submission format and rules (AI-use disclosure, NASA branding) — don't assume.

### Timeline
| When (2026-11-14/15) | Milestone |
|---|---|
| Sat, first hour | Checkpoint 0 |
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
- Ask before: changing the API contract, adding a heavy dependency, cutting a P0 item, anything public-facing.
- Keep it simple: no auth, no database (disk cache + JSON), no microservices.
- Tests: pytest for pure logic (visit grouping, PM propagation, stretch, cache keys, collection selection); a smoke test
  that the 5 prebaked manifests load. No exhaustive UI tests.

## 7. Risks and fallbacks
| Risk | Mitigation |
|---|---|
| IRSA slow / down during the demo | prebaked bundles (FR-3, FR-14); cached processed results |
| ~4 MB per cutout (EPSF not trimmed) | A0 spike: S3/range reads; caps per group; cache processed, not raw |
| λ differences fake brightness changes | per-visit stacks per detector; λ coverage warnings |
| Sub-pixel motion invisible | longest baseline (first vs last visit), diff mode, upsampled display, AllWISE old epoch |
| Saturation on Barnard / R Dra | FLAGS overlay; "saturated" labels instead of numbers; ε Indi B for PM measurement |
| WISE 0855 not detected | expected-position marker + honest S/N / upper limit |
| External APIs (SkyBoT, Gaia, SIMBAD) fail | caches, short timeouts, UI shows "unavailable" instead of breaking |
