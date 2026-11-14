# Промпт для Claude Code: SPHEREx Blink

**Як користуватися.** Phase 0 робить одна людина в одній сесії Claude Code на `main`:

> Read `CLAUDE.md` and `docs/agent-prompt.md`, then execute **Phase 0**. Stop at Checkpoint 0.

Після Checkpoint 0 кожен учасник відкриває свою сесію на своїй гілці (`track-a-backend`, `track-b-frontend`, `track-c-science`) і пише:

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

Read before acting: `CLAUDE.md` (verified facts and rules — they override the research doc), `docs/project_info.md`
(challenge text), `docs/spherex-research.md` (background; outdated parts: collection `spherex_qr2`, "cubes not
published", "2.5 px baseline", cutout sizes).

## 1. Priorities

**P0 — must work by Milestone M2 (Saturday night):**
1. Input: RA/Dec (decimal or sexagesimal) or object name (SIMBAD); FOV selector (2–30′, default 10′); detector selector (D1–D6 / all).
2. Blink player over **per-visit stacks** (per detector and all-detector), shared stretch, zoom with pixelated upsampling, play/pause/fps/step/slider, A/B blink of two chosen frames.
3. **Diff mode** (later − earlier visit, diverging colormap): a moving source shows a dipole, a variable one a single blob.
4. Expected-position marker per frame (proper motion propagated to the frame epoch) when PM is known.
5. FLAGS overlay toggle (at least saturation) and a metadata panel (dates, detectors, λ coverage, N exposures, warnings).
6. URL state: `/?ra=&dec=&fov=&det=&mode=&name=` reproduces the view; share button.
7. All 5 test targets **prebaked** and working with the backend switched off (static fallback).
8. "Limitations" text in the UI and README.

**P1 — Sunday morning:**
spectrum on the fly (click → flux vs λ), light curves (RW Aur, R Dra), Gaia DR3 overlay propagated to the frame
epoch, Aladin Lite context panel (SPHEREx color HiPS / AllWISE / 2MASS), measured proper motion with errors vs
catalog, `/embed` mode, AllWISE (~2010) "old epoch" frame via CDS hips2fits.

**P2 — only if P0+P1 are solid:**
RGB pseudo-color from detector groups, single-exposure mode with a λ window, asteroid overlay (SkyBoT), citizen-science
"I see a mover" button with automatic Gaia/SkyBoT check, GIF export, S3 fast path for fetching.

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
uint16/uint32 flag arrays and a JSON manifest. Stretch, colormap, diff and sums run **client-side** on a canvas, so
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

## 3. API contract (Phase 0 writes it to `docs/api.md` and `backend/app/models.py`)

```
GET /api/health                    → {status, collections:[...], cache:{raw_mb, processed_items}}
GET /api/resolve?name=             → {name, ra, dec, ref_epoch, pmra, pmdec, parallax, source}
GET /api/sequence?ra=&dec=&fov=&det=&mode=&pmra=&pmdec=&ref_epoch=&allwise=
                                   → 200 Sequence (cached) | 202 {job_id}
GET /api/jobs/{job_id}             → {status: queued|running|done|error, progress:{stage, done, total}, result?: Sequence, error?}
GET /api/spectrum?ra=&dec=&pmra=&pmdec=&ref_epoch=   (P1) → {points:[{lambda_um, flux_ujy, err_ujy, mjd, detector, visit, saturated, flags}]}
GET /api/lightcurve?…same…         (P1) → same points; client groups by detector/λ bin
GET /api/overlays?ra=&dec=&fov=&mjd=  (P1) → {gaia:[{source_id, ra, dec, g, pmra, pmdec}], asteroids:[{name, ra, dec, v}]}
GET /files/...                     → Float32 / flag binaries
```

`Sequence`:
```json
{
  "grid": {"ra": 0, "dec": 0, "fov_arcmin": 10, "npix": 97, "pixscale_arcsec": 6.2, "wcs": {"...": "FITS header cards"}},
  "stretch": {"kind": "asinh", "vmin": 0, "vmax": 1, "a": 0.1},
  "frames": [{
    "id": "v2-D5", "kind": "visit_stack|exposure|diff|allwise", "label": "2026-03 · D5",
    "mjd_mid": 0, "date_range": ["iso", "iso"], "detectors": [5], "lambda_um": [3.82, 4.42],
    "n_exposures": 20, "data": "/files/.../v2-D5.f32", "flags": "/files/.../v2-D5.flags.u16",
    "shape": [97, 97], "expected_px": {"x": 48.1, "y": 49.7}, "warnings": ["incomplete λ coverage"]
  }],
  "meta": {"collections": ["spherex_dr1", "spherex_qr3"], "n_exposures_total": 363, "generated_at": "iso", "pipeline_tags": ["l2b-v27"]}
}
```

## 4. Test targets and acceptance criteria (Track C owns, everyone uses)

Verify every catalog value via SIMBAD in Phase 0 and store it with its source and reference epoch in `science/targets.json`.

| Target | Approx. ICRS (deg) | PM (mas/yr) | Acceptance |
|---|---|---|---|
| Barnard's Star | 269.4521, +4.6934 (J2000) | −802, +10362 | diff last−first visit shows a dipole ~north (PA ≈ 356°); shift ≈ 10.3″/yr × Δt (≈1.7–1.8 px); saturation flagged, centroid treated as unreliable |
| ε Indi Ba/Bb | 331.0438, −56.7828 (2MASS, ep. 1999.9) | +3966, −2536 | shift ≈ 4.7″/yr × Δt (≈1.1 px) toward PA ≈ 122°; **best target for measured PM** (not saturated); ε Indi A is ~24′ away |
| WISE 0855−0714 | 133.7951, −7.2451 (WISE designation, ep. ≈2010.4 — confirm what SIMBAD's epoch is) | ≈ −8100, +700 | DR1 only; check D5–D6 stacks at the expected position; report S/N or 5σ upper limit; no detection claim below 5σ |
| RW Aur | 76.9561, +30.4013 | small | per-detector light curve over 3 visits; saturation marked |
| R Dra | 248.1679, +66.7550 | small | deep field, 2,514 exposures → binned light curve; likely saturated → flagged, not fake numbers |

Track C writes `science/VALIDATION.md`: per target — figure/GIF, measured vs expected numbers with errors, verdict, caveats.

## 5. Plan

### Phase 0 — skeleton and contract (one session on `main`, ≤1 h)
1. Monorepo layout from `CLAUDE.md`. `.gitignore` and `.gitattributes` already cover Python, Node, caches, FITS and
   macOS/Windows/VS Code files — extend them only if a new tool needs it.
2. Backend skeleton: FastAPI app, `/api/health`, pydantic models for the contract, config via env, pytest wired.
3. Frontend skeleton: Vite + React + TS, Aladin Lite pinned, a page that loads a manifest and draws one Float32 frame.
4. `docs/api.md` (contract above) + **mock bundle** `frontend/public/mock/` with synthetic frames (a Gaussian source moving
   1–2 px across 3 visits + a varying one) so the frontend can be built before the backend works.
5. `science/targets.json` with SIMBAD-verified values.
6. Fill the **Commands** section in `CLAUDE.md`.
7. **Checkpoint 0**: everything runs locally with one command each; commit on `main`.

### Track A — backend (`backend/`)
- **A0 spike (≤45 min, before committing to a fetch strategy).** For Barnard, time 20 cutouts (latency, MB/s, failures).
  Check (a) whether the cutout service can drop `EPSF`; (b) the S3 layout (`aws s3 ls --no-sign-request s3://nasa-irsa-spherex/`)
  and whether `astropy.io.fits.open(..., use_fsspec=True)` + `.section` reads only `IMAGE/FLAGS/VARIANCE/ZODI`;
  (c) HTTP range reads on the `ibe` URL. Report numbers and pick a strategy. **Checkpoint A0.**
- A1 collections discovery + SIA query + visit grouping; unit tests on recorded CSV fixtures (all 5 targets).
- A2 fetch + cache + concurrency + progress.
- A3 processing: background, flags, λ, reprojection, per-visit stacks, all-detector stack. Test with saved small fixtures
  (strip `EPSF` before saving).
- A4 API with the job model, CORS for the frontend origin, files endpoint. **Checkpoint A (M1):** real Barnard and ε Indi B sequences via HTTP.
- A5 (P1) spectrum + light curve: forced aperture photometry at the PM-propagated position per exposure (photutils,
  annulus background, VARIANCE errors, skip flagged), convert surface brightness × pixel solid angle → flux, aperture
  correction from EPSF or empirically; validate against the IRSA Spectrophotometry Tool on one unsaturated star.
- A6 (P1) overlays: Gaia DR3 cone (epoch 2016.0 → frame mjd), SkyBoT with cache, short timeout, graceful "unavailable".
- A7 Dockerfile, health check, raw-cache LRU cap.

### Track B — frontend (`frontend/`)
- B1 URL ↔ state sync; input parsing (decimal/sexagesimal), name resolve, preset buttons for the 5 test targets.
- B2 Canvas player on Float32: stretch (asinh/linear/log + sliders), colormaps (gray, inverted, diverging for diff),
  play/pause/fps/step/slider, A/B blink, zoom with `image-rendering: pixelated`, crosshair + expected-position marker,
  keyboard shortcuts (space, ←/→, B).
- B3 Data layer: job polling with a progress bar; fallback order live API → `/prebaked/<target>/` → error message; dev on `/mock/`.
- B4 Metadata panel + warnings + FLAGS overlay toggle. **Checkpoint B (M1):** the mock and then the live sequence play end-to-end.
- B5 (P1) Aladin Lite panel synced to target/FOV: `CDS/P/SPHEREx/QR2/color`, AllWISE, 2MASS; Gaia DR3 via VizieR (`I/355/gaiadr3`).
- B6 (P1) spectrum and light-curve charts (one small chart lib), saturated points drawn hollow and labeled.
- B7 (P1) `/embed?...` minimal mode + "copy embed code"; share button.
- B8 About/Help: how to read a blink and a dipole, limitations, data credits (NASA/IPAC IRSA, SPHEREx, Gaia, CDS).

### Track C — science and prebake (`science/`, `scripts/`)
- C1 `targets.json` (Phase 0), expected shifts per visit pair.
- C2 Validation runs on all 5 targets → `science/VALIDATION.md` (draft by M1, complete by M3).
- C3 `scripts/prebake.py` → `frontend/public/prebaked/<target>/` (manifest + frames) + GIFs for the pitch. **Checkpoint C (M2):** the app works on all 5 targets with the backend off.
- C4 (P1) proper motion measurement: centroid per visit stack, linear fit over time → μ with errors vs catalog (Barnard, ε Indi B).
- C5 (P1) WISE 0855: D5–D6 stack S/N at the expected position or an upper limit; AllWISE frame for comparison.

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

If M1 slips by >2 h, drop P1 items in this order: AllWISE frame → light curves → spectrum → Gaia overlay. Never drop P0.7 (prebake).

## 6. Working rules
- **Checkpoints:** stop and report in Ukrainian using: *Зроблено / Як перевірено (команди + реальний вивід) /
  Відхилення від плану / Ризики та питання / Наступний крок.* Wait for "go".
- Verify against real data, not just mocks; paste real numbers. If something cannot be verified, say so plainly.
- Commit locally at each green checkpoint on your track branch, following the Git section of `CLAUDE.md`
  (one-line messages; push only when explicitly told to). Never deploy or create accounts without a human OK.
- Ask before: changing the API contract, adding a heavy dependency, cutting a P0 item, anything public-facing.
- Keep it simple: no auth, no database (disk cache + JSON), no microservices.
- Tests: pytest for pure logic (visit grouping, PM propagation, stretch, cache keys, collection selection); a smoke test
  that the 5 prebaked manifests load. No exhaustive UI tests.

## 7. Risks and fallbacks
| Risk | Mitigation |
|---|---|
| IRSA slow / down during the demo | prebaked bundles (P0.7); cached processed results |
| ~4 MB per cutout (EPSF not trimmed) | A0 spike: S3/range reads; caps per group; cache processed, not raw |
| λ differences fake brightness changes | per-visit stacks per detector; λ coverage warnings |
| Sub-pixel motion invisible | longest baseline (first vs last visit), diff mode, upsampled display, AllWISE old epoch |
| Saturation on Barnard / R Dra | FLAGS overlay; "saturated" labels instead of numbers; ε Indi B for PM measurement |
| WISE 0855 not detected | expected-position marker + honest S/N / upper limit |
| External APIs (SkyBoT, Gaia, SIMBAD) fail | caches, short timeouts, UI shows "unavailable" instead of breaking |
