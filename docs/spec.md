# SPHEREx Blink — Specification

Version 1.0 · 2026-11-14 · NASA Space Apps 2026, challenge "Planet X and SPHEREx"

This document says **what** we build and **how we know it is done**. It is the source of truth for requirements.

| Document | Role |
|---|---|
| `docs/project_info.md` | Challenge text — origin of all requirements |
| **`docs/spec.md`** | Requirements with IDs and acceptance criteria (this file) |
| `docs/api.md` | Interface contract: endpoints, data formats, FLAGS policy |
| `CLAUDE.md` | Verified data facts, science rules, engineering rules, commands |
| `docs/agent-prompt.md` | Plan: tracks, order of work, checkpoints, timeline |
| `docs/spherex-research.md` | Background: physics, data access, pitfalls, sources |

Requirement IDs (`FR-n`, `SR-n`, `NFR-n`, `T-n`, `OD-n`) are stable: reference them in code reviews, commits and
checkpoint reports. Priorities: **P0** = must work at Milestone M2; **P1** = Sunday morning; **P2** = only if P0 and P1
are solid.

## 1. Goal

A public web tool where anyone enters a position on the sky and immediately sees how that patch changed across
SPHEREx's all-sky passes, so that moving and variable objects stand out.

**Challenge objectives (mandatory):**

| ID | Objective | Covered by |
|---|---|---|
| O-1 | Users enter the coordinates (RA, Dec) of a sky patch | FR-1, FR-2, FR-5 |
| O-2 | The tool shows a series of SPHEREx images of that patch like a short video | FR-6 … FR-9 |
| O-3 | Tested on Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae, R Draconis | FR-3, §6 |

**Success means:** all five test targets are demonstrated with honest, quantified results (§6); the tool works for
arbitrary coordinates; the challenge's "Potential Considerations" are covered (§4.4).

## 2. Users and use cases

| User | Need |
|---|---|
| Curious public, citizen scientists | Type a name or coordinates, watch the blink, notice something that moves |
| Amateur and professional astronomers | Check a candidate mover: motion, flags, spectrum, comparison with catalogs |
| Judges | Open a link (possibly weeks later), try the test targets in one click, understand the limitations |
| Website owners, educators | Embed a view of a sky position in another page |

- **UC-1** Pick a test target from the presets → the blink plays at once (prebaked data).
- **UC-2** Enter coordinates or a name → see progress → blink and difference of the SPHEREx visits.
- **UC-3** Switch detectors / field of view / difference view; read flags and metadata to judge whether a change is real.
- **UC-4** Click a source → spectrum (flux vs λ) and light curve (flux vs time).
- **UC-5** Copy a link or an embed snippet that reproduces the current view.

## 3. Scope

**In scope:** SPHEREx level-2 images from IRSA (newest DR + newest QR, wide and deep surveys); per-visit stacks;
blink and difference views; flags; Gaia DR3 and AllWISE context; spectra and light curves of clicked sources;
shareable URLs and embedding; static bundles for the five test targets.

**Out of scope (non-goals):**
- User accounts, a database, storing user reports on the server.
- Sky-wide automatic search for movers or any automatic "discovery" claims.
- Claims about Planet X / Planet Nine; detections below 5σ.
- Photometry of saturated sources (they are labelled, not measured).
- Mobile-first design (mobile must be usable, desktop is the primary target).
- Hosting our own copy of SPHEREx data (we read from IRSA / its S3 mirror and cache).

## 4. Functional requirements

### 4.1 P0 — core

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-1 | **Coordinate input.** ICRS RA/Dec as decimal degrees or sexagesimal (`17 57 48.5 +04 41 36`, `17h57m48.5s +4d41m36s`). | All listed formats parse to the same position within 0.1″. Invalid input shows an inline message and sends no request. |
| FR-2 | **Search by name** via `/api/resolve` (SIMBAD with mirror fallback); fills position, proper motion and its epoch. | The 5 test targets resolve. Unknown name → "not found". SIMBAD unreachable → message suggesting coordinates; coordinate input keeps working. |
| FR-3 | **Test-target presets**: one control per target, loading its prebaked bundle. | Each preset shows its first frame in < 2 s (NFR-1) with the backend switched off. |
| FR-4 | **Field of view** 2–30′ (default 10′) and **detector** choice: all / D1–D6. | Out-of-range values are rejected by the API (422) and clamped with a notice in the UI. Changing detectors does not refetch data that is already loaded. |
| FR-5 | **URL state**: every view parameter (§5.3) lives in the page URL. | Opening a copied URL in a fresh browser reproduces target, FOV, detectors, view, frames A/B, fps, stretch. A "Copy link" control exists. |
| FR-6 | **Visit-stack sequence**: frames are per-visit stacks (per detector and all detectors combined), in time order, each labelled with date range and detectors. | Barnard shows 3 visits, ε Indi B 4 visits (per `CLAUDE.md` coverage table). Labels match the manifest. |
| FR-7 | **Player**: play/pause, previous/next, slider, fps, loop, A/B blink of two chosen frames; keyboard: Space, ←/→, B. | All controls work by mouse and keyboard; fps bounded by §5.4. |
| FR-8 | **Display controls**: shared stretch for the whole sequence (asinh/linear/log, adjustable min/max); zoom 1–8× with nearest-neighbour upsampling; masked pixels (NaN) in a distinct colour. | Switching frames never changes the stretch. A saturated core is visibly distinct from sky. |
| FR-9 | **Difference view**: B − A (default: last − first visit) with a diverging, colour-blind-safe colormap symmetric around 0. | Barnard and ε Indi B show a dipole as specified in T-1, T-2. |
| FR-10 | **Expected-position marker** on every frame when proper motion is known (from FR-2, a preset or URL params). | ε Indi B: marker within 1 px of the source centroid in every visit. |
| FR-11 | **Flags overlay** with toggles per group (saturation, bad data, artifacts) and a legend with bit names (`docs/api.md`). | Barnard's core shows saturation; toggling never alters the underlying image. |
| FR-12 | **Frame metadata and warnings**: dates, detectors, λ range, number of exposures, warnings (incomplete λ coverage, few exposures, target saturated). | WISE 0855's first visit (30 exposures) carries an "incomplete coverage" warning. |
| FR-13 | **Live request states**: queued / running with stage and counts (searching, downloading N/M, stacking), error with retry, "no SPHEREx coverage", cancel. | Progress appears < 2 s after submitting; IRSA outage produces a readable error offering the presets. |
| FR-14 | **Offline mode**: if the backend is unreachable, the presets still work from static bundles; a banner explains the mode. | With the backend stopped, all 5 presets work and the banner is shown. |
| FR-15 | **About / limitations** page: how to read a blink and a dipole, what the tool cannot see (sub-pixel motion, saturation, WISE 0855 at the limit, no Planet Nine), parallax ignored, data credits (NFR-10). | Reachable from every view; the pitch uses the same wording. |

### 4.2 P1 — distinguishing features

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-16 | **Spectrum on the fly**: click a source → forced aperture photometry on every exposure at the proper-motion-propagated position → flux vs λ with errors, coloured by visit; saturated or flagged points marked, not plotted as values. | For one unsaturated star in the ε Indi B field, the median ratio to IRSA's Spectrophotometry Tool fluxes is within 0.8–1.25. |
| FR-17 | **Light curve**: flux vs time per detector (or λ bin) for the clicked source. | RW Aur and R Dra curves render; saturated R Dra points are labelled "saturated". |
| FR-18 | **Gaia DR3 overlay** propagated from epoch 2016.0 to each frame's epoch. | Barnard's Gaia marker moves with the source across visits. Gaia unavailable → overlay listed as unavailable, no crash. |
| FR-19 | **Context panel** (Aladin Lite) synced to target and FOV: SPHEREx colour HiPS, AllWISE, 2MASS; Gaia catalogue. | Panel follows the current target; CDS outage affects only this panel. |
| FR-20 | **Proper-motion measurement**: centroid per visit stack, linear fit over time → μα*, μδ ± σ next to the catalog value. | ε Indi B agrees with (+3982, −2467) mas/yr within 3σ (T-2). Saturated sources get "unreliable" instead of a number. |
| FR-21 | **Embed mode** `/embed?<§5.3 params>`: minimal chrome, link to the full tool, "copy embed code". | The snippet works inside an iframe on a blank HTML page. |
| FR-22 | **AllWISE old-epoch frame** (~2010) on the same grid (CDS hips2fits), clearly labelled as a different instrument and band. | Barnard's 2010 → 2026 shift (≈2.7′) is obvious next to the SPHEREx frames. |

### 4.3 P2 — if time allows

| ID | Requirement |
|---|---|
| FR-23 | RGB pseudo-colour from detector groups (D1+D2 → blue, D3+D4 → green, D5+D6 → red). |
| FR-24 | Single-exposure mode with a λ-window filter (`api` `mode=exposures`). |
| FR-25 | Known-asteroid overlay per frame epoch (SkyBoT), with cache and graceful failure. |
| FR-26 | "I see a mover" check: click → automatic match against Gaia / SkyBoT → known star / known asteroid / unknown; a copyable report (nothing stored server-side). |
| FR-27 | Export of the current sequence as GIF. |

### 4.4 Traceability to the challenge's Potential Considerations

| Consideration | Requirements |
|---|---|
| Easy to update with new data releases | NFR-3 |
| Creative use of the 102 bands; spectra on the fly | FR-6 (per-detector stacks), FR-16, FR-23 |
| Add / subtract images from different times | FR-6 (stacks), FR-9 (difference) |
| User-chosen field of view | FR-4 |
| Overlays from Gaia / WISE | FR-18, FR-19, FR-22 |
| Coordinates in the URL, embeddable | FR-5, FR-21 |
| Metadata such as contamination flags | FR-11, FR-12 |
| Astropy and Aladin | backend stack, FR-19 |

## 5. UX specification

### 5.1 Layout
- **Desktop (≥ 1024 px):** top bar — search (name or coordinates), FOV, detectors, presets; centre — viewer with
  zoom; under it — player controls; right — metadata, warnings, flag legend; below — tabs *Spectrum*, *Light curve*,
  *Context* (Aladin).
- **Mobile (< 768 px):** single column in the same order; viewer full width; controls wrap. Usable, not optimised.

### 5.2 States
| State | What the user sees |
|---|---|
| Landing | One-sentence explanation, the five presets, an example link |
| Loading (live) | Stage and counts from the job (FR-13), cancel |
| Ready | Player, metadata, overlays |
| Partial data | Player plus warning badges (missing visits, incomplete λ coverage) |
| No coverage | "SPHEREx has no images here yet" + nearest suggestion: try a preset |
| Error | Plain-language cause (archive slow/down, invalid input), retry, presets |
| Offline | Banner "Offline mode — test targets only" (FR-14) |

### 5.3 URL parameters (page URL, not the API)
| Param | Values | Default | Notes |
|---|---|---|---|
| `target` | `barnard` · `eps_ind_b` · `wise0855` · `rw_aur` · `r_dra` | — | Loads the prebaked bundle; highest precedence |
| `name` | object name | — | Resolved via FR-2; precedence over `ra`/`dec` |
| `ra`, `dec` | decimal degrees or URL-encoded sexagesimal | — | ICRS |
| `fov` | 2–30 (arcmin) | 10 | |
| `det` | `all` or `1`–`6`, comma list | `all` | |
| `view` | `blink` · `diff` | `blink` | |
| `a`, `b` | frame ids from the manifest | first, last | A/B blink and difference operands |
| `fps` | 0.5–3 | 2 | §5.4 |
| `stretch` | `asinh` · `linear` · `log` | `asinh` | |
| `flags` | comma list of `saturation`, `bad`, `artifact` | none | |
| `pmra`, `pmdec`, `epoch` | mas/yr (pmra includes cos δ), Julian year | from resolve | Enables FR-10 for raw coordinates |
| `manifest` | bundle URL | — | Development and testing only |

Unknown parameters are ignored; invalid values fall back to the default with a visible notice.

### 5.4 Animation safety
Blinking is flashing content (WCAG 2.2 SC 2.3.1): fps is capped at **3**, default **2**. With
`prefers-reduced-motion` the player starts paused and never autoplays.

### 5.5 Accessibility and wording
- All controls keyboard-operable with visible focus and accessible names; text contrast WCAG AA.
- Colour maps: perceptually uniform greyscale for images; diverging blue–orange (not red–green) for differences.
- Plain language with tooltips for *visit*, *detector*, *dipole*, *saturated*, *proper motion*.
- Names and text from external services are rendered as text, never as HTML.

## 6. Science requirements and test-target acceptance

### 6.1 Science rules (details and rationale: `CLAUDE.md` → Science rules)
| ID | Rule |
|---|---|
| SR-1 | Compare like with like: the blink unit is a per-visit stack per detector (or all detectors combined); λ coverage is recorded per stack and a warning is raised when a visit has < 80 % of the exposures or λ coverage of the best-covered visit of the same detector. |
| SR-2 | Visits = time clusters separated by > 40 d; clusters longer than 60 d (deep fields) are split into 30-d bins; exposures per (detector, bin) are capped (cap set at Checkpoint A0, OD-4). |
| SR-3 | Positions are propagated with proper motion to each frame's `MJD-AVG` in ICRS (no GCRS, no aberration); parallax is ignored and stated in FR-15. Catalog positions always carry their epoch (WISE 0855 challenge coordinates are epoch ≈2010.5). |
| SR-4 | Background is subtracted (ZODI extension, then residual median) before one shared stretch is computed over all frames. |
| SR-5 | Frames are reprojected to a common north-up TAN grid at 6.2″/px with bicubic interpolation; flags with nearest-neighbour and OR-combined. |
| SR-6 | FLAGS policy per `docs/api.md`: `bad` and `saturation` masked in stacks, `artifact` and `info` kept; `SOURCE` never masked; saturated measurements are never reported as numbers. |
| SR-7 | No detection claims below 5σ — report S/N or a 5σ upper limit. No Planet X / Planet Nine claims. |

### 6.2 Acceptance per test target
Evidence for each target goes to `science/VALIDATION.md`: a figure or GIF, measured vs expected numbers with errors,
a verdict, caveats. Catalog values: `science/targets.json`.

| ID | Target | Must show |
|---|---|---|
| T-1 | Barnard's Star | 3 visits. Difference last − first: dipole toward PA 356° ± 30°, separation 1.3–2.3 px (expected ≈ 1.8). Saturated core flagged; marker (FR-10) and Gaia (FR-18) follow the source; centroid labelled unreliable. |
| T-2 | ε Indi B | 4 visits. Dipole toward PA 122° ± 30°, separation 0.7–1.5 px (expected ≈ 1.1). Measured PM (FR-20) consistent with (+3982, −2467) mas/yr within 3σ. Artifacts from ε Indi A (~24′ away) flagged if present. |
| T-3 | WISE 0855−0714 | DR1 visits only (3; the first with 30 exposures and a warning). Expected position from SIMBAD J2000 + PM. D5–D6 stack: S/N at the expected position reported; below 5σ → "not detected, 5σ limit = X µJy". |
| T-4 | RW Aurigae | 3 visits. Per-detector flux per visit with errors (light curve); variability amplitude stated; saturated points labelled. |
| T-5 | R Draconis | Deep field: 30-d bins within the exposure cap; binned light curve or "saturated" labels; no numbers for saturated points. |

## 7. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | **Performance.** Prebaked or cached sequence: first frame < 2 s on a 20 Mbit/s connection; rendering a 290×290 frame < 16 ms on a mid-range laptop. Uncached: progress visible < 2 s; end-to-end time budget set after Checkpoint A0 (OD-5). |
| NFR-2 | **Payload.** Image + flags ≤ 75 KB per frame at 10′ and ≤ 680 KB at 30′. A typical 10′ sequence (3–4 visits × 7 stacks) ≤ 3 MB; deep-field sequences (e.g. R Dra, ~17 bins) may be larger and load frames on demand. |
| NFR-3 | **Data freshness.** No hardcoded collections: newest DR + QR discovered via TAP (cached 6 h, config fallback). Processed results are keyed by the set of image keys (obs_id, detector), so new exposures trigger a rebuild. Prebaked bundles regenerate with one command. |
| NFR-4 | **Availability.** Static frontend and prebaked bundles stay online through judging (weeks after the event); the backend may sleep — the UI degrades to offline mode (FR-14). |
| NFR-5 | **Load on external services.** ≤ 8 concurrent requests to IRSA per backend instance, retries with backoff, timeouts, caching; generic User-Agent; no personal data in requests. |
| NFR-6 | **Browsers.** Latest two versions of Chrome, Firefox, Safari, Edge on desktop; mobile Safari/Chrome usable. WebGL is required only for the context panel (FR-19). |
| NFR-7 | **Security.** No authentication and no user data stored. API validates every parameter (422 on violation); CORS restricted to known origins; no secrets in the repo; external text rendered as text. |
| NFR-8 | **Quality gates.** Python: ruff, mypy --strict, pytest. Frontend: strict TypeScript build, oxlint. All green before every commit (`CLAUDE.md`). |
| NFR-9 | **Reproducibility.** `uv.lock`, `package-lock.json`; `science/targets.json` regenerated by script; mock and prebaked bundles deterministic. |
| NFR-10 | **Licensing and credits.** Credits for NASA/IPAC IRSA and SPHEREx (Caltech/JPL), Gaia (ESA/DPAC), CDS (Aladin Lite, SIMBAD, HiPS), WISE/NEOWISE. Repository licence compatible with Aladin Lite (GPL/LGPL-3) — OD-2. |
| NFR-11 | **Honesty.** UI, README and pitch state limitations (FR-15) and never claim more than §6 supports. |

## 8. Architecture (summary)

Browser (React + canvas) ↔ FastAPI backend (resolve → query → fetch + cache → process → serve) ↔ IRSA / SIMBAD /
Gaia / SkyBoT; static bundles served next to the frontend; Aladin Lite reads CDS HiPS directly. Frames travel as
Float32 arrays and are stretched and differenced client-side. Details: `docs/agent-prompt.md` §2, `docs/api.md`.

## 9. Deliverables

- Public URL of the tool (static frontend + bundles; backend if hosted — OD-1).
- Repository with README (what, how to run, screenshots, limitations, credits).
- `science/VALIDATION.md` with evidence for T-1 … T-5.
- GIFs or screenshots per test target; demo video and project description in the Space Apps format (OD-3).

## 10. Open decisions

| ID | Decision | Owner | Needed by |
|---|---|---|---|
| OD-1 | Hosting for backend (Docker, persistent disk) and frontend (static) | Team | Sunday morning |
| OD-2 | Repository licence (Aladin Lite is GPL/LGPL-3) | Team | Before submission |
| OD-3 | Exact submission deadline (hour, time zone) and required format (video/slides, AI-use disclosure, branding rules) | Track D | Saturday |
| OD-4 | Fetch strategy — decided 2026-11-14 (A0): S3 range reads primary, IRSA `ibe` multi-range fallback, cutout service last resort (`CLAUDE.md` → Verified data facts). Exposure cap per group — proposed 20 per (detector, visit), 10 per deep-field bin; awaiting the team | Track A | Checkpoint A0 |
| OD-5 | Uncached end-to-end latency budget | Track A | Checkpoint A0 |
| OD-6 | ~~Who owns which track~~ — decided 2026-11-14: four roles A–D (`docs/agent-prompt.md` → Roles and ownership); people assigned by the team | Team | Done |

## 11. Glossary

| Term | Meaning |
|---|---|
| Visit | All exposures of a sky point taken during one pass of the survey (weeks long, ~6 months apart) |
| Visit stack | Inverse-variance weighted mean of a visit's exposures, per detector or all detectors combined |
| Detector / band | One of 6 H2RG arrays (D1–D6), each covering one wavelength band through its linear variable filter |
| LVF | Linear variable filter: wavelength changes across the frame, so one sky point is seen at different λ in different exposures |
| Dipole | Dark + bright pair in a difference image: a source that moved between the two frames |
| Proper motion (PM) | Apparent motion of a star on the sky, mas/yr; `pmra` includes cos δ |
| Epoch | The date a catalog position refers to (Julian year) |
| FLAGS | Per-pixel uint32 bitmask from the SPHEREx pipeline (`docs/api.md`) |
| HiPS | Hierarchical tiling of all-sky images used by Aladin Lite |
| Prebaked bundle | Static `sequence.json` + frame files for a test target, served without a backend |
| DR / QR | Data Release (curated) / Quick Release (weekly) of SPHEREx data |
