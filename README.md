# SPHEREx Blink

A web tool for blinking NASA SPHEREx images: enter sky coordinates (RA/Dec) or an object name and get an animated
sequence of SPHEREx images of that sky patch, so moving and variable objects stand out.

Built for the NASA Space Apps Challenge 2026, challenge "Planet X and SPHEREx".

<p align="center">
  <img src="frontend/public/prebaked/barnard/blink.gif" width="300" alt="Barnard's Star blinking between three SPHEREx visits, all detectors combined">
  &nbsp;
  <img src="frontend/public/prebaked/eps_ind_b/blink.gif" width="300" alt="Epsilon Indi B blinking between four SPHEREx visits, all detectors combined">
</p>
<p align="center"><em>Barnard's Star (left) and ε Indi B (right): visit stacks of all six detectors, one frame per
visit.</em></p>

![ε Indi B: four visit stacks and the last − first difference](science/figures/eps_ind_b_motion.png)

*ε Indi B in four visits from 2025-04 to 2026-09, and the last − first difference: the blue/orange pair is the star
moving 6.7″ toward the south-east.*

All images are rendered by our pipeline from real SPHEREx data. None of them is AI-generated.

## Features

- **Search by name or position**: names resolve through SIMBAD, with the Harvard mirror as a fallback. Positions
  are entered as RA/Dec, with an optional proper motion. The field of view is 2–30′.
- **Comparable frames**: frames are per-visit stacks per detector, or all detectors combined. They are not raw
  single exposures at different wavelengths. Every frame is reprojected to one north-up grid at the native
  6.2″/px. Zodiacal light and the local background are subtracted, and every frame gets the same brightness
  stretch. Deep-field targets are split into 30-day bins.
- **Blink player**: play, pause and step through frames at 0.5–3 fps, or pick any two frames (A/B) to blink.
  Zoom in, switch detectors without a refetch, and choose an asinh, linear or log stretch.
- **Difference mode**: shows B − A on a diverging colour scale, so a moving star appears as a dark/bright pair.
- **Expected position**: a marker shows where a high-proper-motion target should be in each frame. The position
  is propagated with `SkyCoord.apply_space_motion`.
- **Gaia DR3 overlay**: Gaia stars propagated to each frame's epoch.
- **FLAGS overlay**: saturated, bad and artifact pixels are masked in the stacks and can be shown on top of the
  image. Saturated measurements are labelled "saturated" and never reported as numbers.
- **Data quality warnings**: a frame is marked when its wavelength coverage is incomplete, it has few
  exposures, or it is saturated.
- **Pixel readout and frame metadata**: click a pixel to read its value and flags. Each frame lists its dates,
  detectors, wavelength range and number of exposures.
- **Spectrum chart**: forced aperture photometry of the target per exposure, plotted as flux against wavelength
  and coloured by visit, with error bars. Saturated and masked points get hollow markers in a strip under the
  plot, never a value.
- **Light-curve chart**: flux against time per detector, with visit means, a χ² test against a constant
  brightness, and brightness changes measured at matched wavelength between visits.
- **Sky context**: Aladin Lite with 2MASS, AllWISE and DSS2 (from the IRSA HiPS mirror) and Gaia stars, centred on
  the target and matching the field of view.
- **Shareable views**: the whole view state lives in the URL (target, detector, frames, mode, stretch, overlays).
  A "Copy link" button copies it, and `/embed` shows a minimal player for iframes.
- **Works offline**: the five test targets ship as prebaked bundles of real SPHEREx data, so they open even
  without the backend or IRSA. A live search near a test target falls back to its bundle when the archive is
  down.
- **About page**: explains blinks, the dark/bright pairs of difference mode and the SPHEREx terms, with tooltips
  in the interface.

## Test targets

| Target | What it shows | Result (`science/VALIDATION.md`) |
|---|---|---|
| Barnard's Star | fastest proper motion | moves 1.65 px (10.3″) toward PA 359° in 1.1 yr |
| ε Indi B | nearby brown-dwarf binary | moves 1.07 px (6.7″) toward PA 129°; spectrum within 2–23 % of 2MASS J/H/Ks |
| WISE 0855−0714 | coldest known brown dwarf, at the detection limit | motion seen in D5–D6; the flux is blended with a field star and is an upper bound |
| RW Aurigae | T Tauri star, variable | 2.5× brightening at 0.75 µm (16.6σ); saturated in the other bands |
| R Draconis | Mira variable in the deep field | saturated in every exposure: shown as "saturated", not as numbers |

## How it works

1. The backend finds SPHEREx exposures covering the position (IRSA SIA / TAP) and downloads small cutouts.
2. Exposures are grouped into visits and stacked per detector, reprojected to a common north-up grid and given
   one shared brightness stretch, so frames are directly comparable.
3. The frontend plays the stacks as a blink / flipbook, with a difference mode, the expected position of
   high-proper-motion targets, and a FLAGS (saturation / artifact) overlay. The view state is kept in the URL,
   so any view can be shared.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Python 3.11.5+ / FastAPI API: data discovery, cutouts, stacking |
| `frontend/` | React + TypeScript + Vite viewer, Aladin Lite sky context |
| `science/` | Test targets and validation scripts |
| `scripts/` | Mock and prebaked data bundles |
| `docs/` | API contract (`api.md`), challenge text, background research |

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) and Node.js with npm.

```sh
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm ci && npm run dev
```

Open <http://localhost:5173>. The five test targets open from prebaked real SPHEREx data, also without the
backend; a search by name or coordinates asks the live archive through the backend.

### With Docker

Requirements: Docker with Compose v2.

```sh
docker compose up -d --build
```

Open <http://localhost:8080>. nginx serves the built frontend and the prebaked bundles and proxies `/api` and
`/files` to the backend, which is not published on the host. Downloaded and processed data live in the `cache`
volume (`docker compose down -v` removes it). Settings: copy `.env.example` to `.env`; no secrets are needed.
The port is bound to `127.0.0.1` unless `BIND_ADDR` says otherwise.

### CI/CD

Every pull request runs lint, type checks, tests, a Docker smoke test and secret/vulnerability scans
(`.github/workflows/ci.yml`). A green `main` is deployed to Azure Container Apps (`deploy.yml`, `infra/main.bicep`);
one-time setup in [`docs/deploy.md`](docs/deploy.md).

## Limitations

- SPHEREx pixels are 6.2″, so even the fastest nearby stars move only ~1–2 px over the available ~1 year baseline.
- Each detector covers a range of wavelengths that varies across the frame; frames are compared per detector,
  and incomplete wavelength coverage is reported.
- Faint targets near the detection limit are shown with their expected position and an upper limit, without
  claiming a detection.

## Use of AI

- **Idea and decisions**: the team. The idea comes from the challenge statement. Scope, priorities, the science
  rules, data choices and hosting were decided by the team, not by AI.
- **Code, tests and documentation**: written with [Claude Code](https://claude.com/claude-code) (Anthropic), an AI
  coding assistant. Each of the four team members ran their own session for their part of the project (archive and
  API, frontend, science pipeline, charts and context). Team members gave the tasks, reviewed every pull request
  and merged it.
- **Research**: Claude Code also helped read the SPHEREx documentation and IRSA tutorials, probe the archive
  services, and summarise the background in `docs/spherex-research.md`.
- **Checking the results**: the science was checked against real data, not taken on trust. Measured proper motions
  and fluxes were compared with SIMBAD, Gaia DR3 and 2MASS catalogue values (`science/VALIDATION.md`), and each
  result was looked at by a person before it went into this README.
- **The running app uses no AI**: there are no AI calls at run time, and every image is computed from SPHEREx data.

## Data

SPHEREx data: NASA / IPAC Infrared Science Archive (IRSA). Object names resolved with SIMBAD (CDS).
Star overlay: Gaia DR3 (ESA / Gaia DPAC), read from the MAST, GAVO or ESA archives.
