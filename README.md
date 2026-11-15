# SPHEREx Blink

A web tool for blinking NASA SPHEREx images: enter sky coordinates (RA/Dec) or an object name and get an animated
sequence of SPHEREx images of that sky patch, so moving and variable objects stand out.

Built for the NASA Space Apps Challenge 2026, challenge "Planet X and SPHEREx".

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
| `backend/` | Python 3.11+ / FastAPI API: data discovery, cutouts, stacking |
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

## Limitations

- SPHEREx pixels are 6.2″, so even the fastest nearby stars move only ~1–2 px over the available ~1 year baseline.
- Each detector covers a range of wavelengths that varies across the frame; frames are compared per detector,
  and incomplete wavelength coverage is reported.
- Faint targets near the detection limit are shown with their expected position and an upper limit, without
  claiming a detection.

## Data

SPHEREx data: NASA / IPAC Infrared Science Archive (IRSA). Object names resolved with SIMBAD (CDS).
Star overlay: Gaia DR3 (ESA / Gaia DPAC), read from the MAST, GAVO or ESA archives.
