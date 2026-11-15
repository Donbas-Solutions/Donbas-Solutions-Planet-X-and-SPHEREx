# Space Apps submission — draft

Fields of the submission form (`docs/deploy.md`, OD-3), English only. Fill in the `[…]` placeholders before
submitting. Test every link in a private window.

## Project name

SPHEREx Blink

## High-level summary

SPHEREx Blink is a public web tool for blinking NASA SPHEREx images. Enter a star name or sky coordinates, and it
builds a short animation of that patch of sky from every SPHEREx visit, so stars that move or change brightness
stand out. Each frame is a stack of one visit per detector. All frames are put on the same north-up grid and share
one brightness scale, so they can be compared directly. A difference mode shows a moving star as a dark/bright
pair. The tool also measures a spectrum on the fly: flux against wavelength from every exposure. Gaia DR3 stars,
FLAGS masks and sky context from other surveys can be shown on top. Every view can be shared or embedded as a URL.
We checked the tool on all five challenge targets. Barnard's Star moves 10.3″ in 1.1 years, and ε Indi B moves
6.7″. RW Aurigae brightens 2.5×. Our spectra agree with IRSA's own Spectrophotometry Tool to 0.2 %.

## Links

- **Project demo:** [public YouTube link of the ≤ 30 s video]
- **Final project:** <https://github.com/Donbas-Solutions/Donbas-Solutions-Planet-X-and-SPHEREx>
- **Live tool:** <https://spherex-blink-web.victoriousmeadow-02021db7.polandcentral.azurecontainerapps.io/>

## Detailed description

### What it does

- **Search** by name (SIMBAD) or RA/Dec, with an optional proper motion. The field of view can be set from 2′ to
  30′.
- **Blink player.** Play and pause, step through frames at 0.5–3 fps, or choose any two frames to blink (A/B). You
  can switch detectors without fetching again, zoom in, and pick an asinh, linear or log stretch.
- **Difference mode.** B − A on a diverging colour scale: a moving star shows up as a dark/bright pair.
- **Expected position.** A marker shows where a high-proper-motion star should be in each frame. The catalogue
  position is propagated to the frame's epoch.
- **Spectrum on the fly.** Forced aperture photometry at the target in every exposure, plotted as flux against
  wavelength and coloured by visit, with error bars. Each SPHEREx exposure sees a different wavelength at the
  star, so one field gives a spectrum.
- **Light curve.** Flux against time per detector, a χ² test against constant brightness, and brightness changes
  measured at the same wavelength.
- **Honest data quality.**
  - The FLAGS mask (saturated, bad and artifact pixels) can be shown on top of the image.
  - Saturated points are labelled "saturated" and never reported as numbers.
  - A warning appears when a frame covers only part of the wavelength band or has few exposures.
- **Overlays and context.**
  - Gaia DR3 stars, moved to each frame's date.
  - An Aladin Lite panel with 2MASS, AllWISE and DSS2.
- **Share and embed.** The whole view lives in the URL. `/embed` gives a minimal player for iframes.
- **Works offline.** The five test targets ship as prebaked bundles of real SPHEREx data. A live search falls back
  to them when the archive is down.

### How it works

1. The backend (Python, FastAPI) asks IRSA for the SPHEREx exposures that cover the position. It reads only the
   pixel rows it needs from the public SPHEREx copy on AWS S3, so an exposure costs ~4 MB instead of 62 MB.
2. The pipeline follows the SPHEREx team's guidance and astronomical practice:
   - subtract the zodiacal-light model (`ZODI`), then a local 2D background;
   - mask flagged pixels;
   - reproject every exposure to a common north-up grid at the native 6.2″/px;
   - stack per visit and detector with inverse-variance weights;
   - apply one shared brightness stretch to the whole sequence.

   Deep-field targets are split into 30-day bins.
3. The React frontend plays the frames on a canvas and draws the overlays. It keeps all view state in the URL.

### Results on the challenge targets (`science/VALIDATION.md`)

| Target | Result |
|---|---|
| Barnard's Star | Moves 1.65 px (10.3″) toward PA 359° in 1.1 yr. The catalogue proper motion predicts the same within 0.4σ. |
| ε Indi B | Moves 1.07 px (6.7″) toward PA 129° over 4 visits, within 1.2σ of the catalogue. Its J/H spectrum agrees with 2MASS to 2–3 %. |
| WISE 0855−0714 | Motion seen in D5–D6 toward PA 276–277° (275° expected). A field star (Gaia DR3) blends with it, so its flux is reported only as an upper bound. |
| RW Aurigae | Brightens 2.5× at 0.75 µm between visits (16.6σ), measured at the same wavelength. Saturated in the other bands, and shown as such. |
| R Draconis | Saturated in every exposure. The tool says "saturated" instead of showing false numbers. |

**Spectra checked against IRSA.** For an unsaturated field star (G 13.9), our flux in 248 exposures has a median
ratio of 0.998 to IRSA's SPHEREx Spectrophotometry Tool (6 detectors: 0.98–1.06).

### Benefits

- Anyone with a browser can see in seconds how a patch of sky changed over a year of SPHEREx data. No Python, no
  FITS files, no login.
- Volunteers and students get the same blink workflow that found many brown dwarfs in WISE data (WiseView), now
  with SPHEREx's 102 wavelengths and a spectrum for every source.
- The tool never shows saturated, blended or incomplete data as clean measurements.
- URLs can be shared and embedded, so a find can be shown to others in one link.

### Tools

Python 3.13, FastAPI, Astropy, astroquery, PyVO, reproject, photutils, NumPy · React 19, TypeScript, Vite,
Aladin Lite 3.8 · Docker, GitHub Actions, Azure Container Apps.

## Use of AI

- **Idea and decisions** are the team's. The idea comes from the challenge. Scope, the science rules, data
  choices and hosting were decided by the team, not by AI.
- **Code, tests and documentation** were written with Claude Code (Anthropic), an AI coding assistant. Each team
  member ran their own session for their part of the project. Team members gave the tasks, reviewed every pull
  request and merged it.
- **Research.** Claude Code helped read the SPHEREx documentation and IRSA tutorials and probe the archive
  services.
- **Checking.** Every science result was checked against real data and catalogues: SIMBAD, Gaia DR3, 2MASS and
  IRSA's Spectrophotometry Tool. A person reviewed each result.
- **The running tool uses no AI.** Every image is computed from SPHEREx data. No image, video or slide was
  generated by AI.

The same text is in the README ("Use of AI").

## NASA data

- SPHEREx Spectral Images (DR1, QR3), NASA/IPAC Infrared Science Archive (IRSA). Access through the SIA service,
  the cutout service and the public AWS S3 copy (`nasa-irsa-spherex`).
- IRSA SPHEREx Spectrophotometry Tool, used to check our spectra.
- 2MASS and AllWISE sky surveys (IPAC/NASA), as HiPS images from the IRSA mirror in the context panel.
- SPHEREx tutorial notebooks (caltech-ipac.github.io/irsa-tutorials), for how to read the data.
- WiseView, as the model for the blink workflow.

## Space agency partner data

- Gaia DR3 (ESA / Gaia DPAC), read from the MAST and GAVO archives: the star overlay and the propagated positions.

## Other references

- SIMBAD and Aladin Lite (CDS, Strasbourg); DSS2 images through the IRSA HiPS mirror.
- Open-source libraries: Astropy, astroquery, PyVO, reproject, photutils, NumPy, Pillow, FastAPI, uvicorn, httpx,
  React, Vite, Aladin Lite.
- 2MASS zero points: Cohen, Wheaton & Megeath (2003). WISE zero points: Jarrett et al. (2011).
- Licence: LGPL-3.0 (`LICENSE`).

---

# Demo video script (≤ 30 s)

Rules (`docs/deploy.md`):
- ≤ 30 s, English; captions in English if anyone speaks another language.
- No NASA or SPHEREx logos.
- No AI-generated footage.
- Public link that needs no login.

How to record:
- Screen recording of the live site in Chrome, 1920×1080.
- Zoom the browser to 125 % so the text is readable.
- English captions on screen. A voice-over is optional; it is not timed into the shots below.
- Before recording, open every URL below once, so frames come from the cache and nothing loads during the take.

| Time | Screen | Caption |
|---|---|---|
| 0–3 s | Title card: "SPHEREx Blink", team name, "NASA Space Apps 2026 · Planet X and SPHEREx". Text only, no logos. | — |
| 3–9 s | Home page. Click the "Barnard's Star" test-target button. The blink plays and the star jumps north between the three visits; the expected-position marker follows it. | "Pick a star or type coordinates. Every SPHEREx visit of that patch, blinked." |
| 9–13 s | Tick "Difference B − A". A dark/bright pair appears at the star. | "Difference mode: a moving star becomes a dark/bright pair. 10″ in one year." |
| 13–18 s | Open `?target=eps_ind_b&gaia=1`. Four visits play; the Gaia diamonds sit on the field stars while ε Indi B moves away from its old position. | "ε Indi B, a pair of brown dwarfs: 6.7″ south-east, matching the catalogue." |
| 18–23 s | Scroll to the Spectrum tab of ε Indi B: points coloured by visit across 0.75–5 µm. | "A spectrum on the fly from every exposure. It matches IRSA's own tool to 0.2 %." |
| 23–27 s | Open `?target=rw_aur`, then the Light curve tab: D1 brightens between visits; the saturated points are hollow markers. | "Variable stars: RW Aur brightens 2.5×. Saturated data is labelled, never faked." |
| 27–30 s | End card: live site URL and GitHub URL. | "Open source, free to use. Built on SPHEREx data from IRSA." |

URLs (live site):
- `/?target=barnard`
- `/?target=eps_ind_b&gaia=1`
- `/?target=rw_aur`

Use the test-target buttons, not a typed name. A typed name starts a live IRSA search, which took up to 2 min on
2026-11-15.
