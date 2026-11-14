# Planet X and SPHEREx — challenge research (Space Apps 2026)

Nov 14, 2026 · @Huss

> **Updated 2026-11-14 after checking the live IRSA archive; translated from Ukrainian** (the original is in git
> history). Fixed: collection names (QR2 is gone from SIA, DR1 and QR3 exist), spectral cubes are already published,
> every cutout weighs \~4 MB, real epochs of the test targets, a text description of the architecture.
> Requirements: `docs/spec.md`. Plan for agents: `docs/agent-prompt.md`. Verified facts: `CLAUDE.md`.

## The challenge in short

Build a public web tool: the user enters the coordinates of a patch of sky (RA and Dec), and the tool shows a series of SPHEREx images of that patch as a short video, so moving objects stand out at once. Finding Planet X is the motivation and the name, not a required goal. Difficulty: Advanced; topics: astrophysics, planets, software. ([challenge page](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/))

**Context from the description.** Since May 2025 SPHEREx has mapped the whole sky every six months in 102 near-infrared bands, imaging more than a billion objects. Comets, asteroids, nearby stars, brown dwarfs and possibly new planets reveal themselves by shifting between images. Pluto was discovered this way, and Backyard Worlds volunteers found hundreds of brown dwarfs with the same method.

**Required (Objectives):**

1. Input of the RA/Dec of a sky patch.
2. Display of a series of SPHEREx images of that patch as an animation (blink / flipbook).
3. Testing on the target list: Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae, R Draconis (next section).

**Desirable (Potential Considerations) — in practice the "extra kudos" criteria:**

- Easy updates for new data releases (data arrive weekly).
- Creative display of the 102 bands: e.g. co-add all data of each of the 6 detectors separately for better signal-to-noise. Extra points for **spectra on the fly**.
- Options to add (stack) and subtract (difference) images from different epochs.
- User-selectable field of view: a larger field makes fast movers easier to track but loads longer.
- Overlays of data from other telescopes: Gaia, WISE.
- Coordinates in the URL so the tool can be embedded in other websites.
- Display of metadata such as contamination flags.
- Ready-made libraries: Astropy for processing, Aladin (CDS) for display.

**Official resources (Resources tab):** IRSA's SPHEREx resources, the SPHEREx tutorial notebooks, WiseView as an example of a similar tool for WISE, Gaia DR3 data. From CSA: NEOSSat data and tutorial and the CADC archive — secondary for this challenge.

## Test targets

The five targets test two different things: three test **motion** (proper motion of nearby objects), two test **brightness changes**. The main trap: catalog coordinates are for epoch 2000 or 2010, and since then the objects have moved by 2–4.5′. That is dozens of SPHEREx pixels, so a small cutout at the catalog coordinates can miss the target. Propagate the position to the image date (astropy `SkyCoord.apply_space_motion`) or use a field of view of at least \~10′.

| Target | What it is | RA / Dec | Motion | IR brightness | What to expect in SPHEREx |
| --- | --- | --- | --- | --- | --- |
| [Barnard's Star](https://en.wikipedia.org/wiki/Barnard%27s_Star) | M4 red dwarf, 1.83 pc | 17h57m48.50s +04°41′36.1″ (epoch 2000) | 10.3″/yr, northward; moved about 4.5′ since 2000 | J 5.2, K 4.5 | almost certainly saturated in all bands; motion is visible as a shift of the saturated blob and its flags |
| [Epsilon Indi Ba/Bb](https://en.wikipedia.org/wiki/Epsilon_Indi) | pair of brown dwarfs T1 + T6, 0.6″ apart | 22h04m10.5s −56°46′58″ (2MASS, epoch 1999.9) | ≈ 4.7″/yr (+3.98″, −2.47″); about 2′ since 1999 | J 11.9, K 11.2 (combined) | a single point (0.6″ is tiny next to a 6.2″ pixel); bright ε Indi A (V 4.7) is only 6.7′ to the west (the projected \~1460 AU separation is in AU, not arcsec): just outside a 10′ field, its halo fills the western part of the frame; not saturated, so the best target for measuring proper motion; [source](https://arxiv.org/pdf/astro-ph/0309256) |
| [WISE 0855−0714](https://en.wikipedia.org/wiki/WISE_0855%E2%88%920714) | coldest known brown dwarf, Y4, 2.28 pc | 08h55m10.831s −07°14′42.53″ (from the challenge; WISE position, epoch ≈2010.5 — 85″ from the J2000 position) | 8.15″/yr, westward; parallax 0.44″ | J ≈ 25, W2 ≈ 14.0 (4.6 µm) | invisible at short wavelengths; a chance only in bands 5–6 (3.8–5 µm) and only in a stack of several images |
| [RW Aurigae](https://en.wikipedia.org/wiki/RW_Aurigae) | young T Tauri star, \~160 pc | 05h07m49.46s +30°24′04.8″ | small, irrelevant for this target | G ≈ 12.2 | irregular dimming by a dusty disk; a new deep dimming started in February 2025 (no source, check against AAVSO) — a light-curve test |
| R Draconis | Mira variable | 16h32m40.3s +66°45′18″ ([BAA](https://britastro.org/vss/obj-dra.html)) | irrelevant for this target | V 6.7–13.2, period \~246 d | very bright in the IR, probably saturated; lies in the Deep field near the north ecliptic pole: 2,514 images with continuous coverage, so a dense light curve is possible |

Motion over half a year is less than a pixel: Barnard \~5.2″, WISE 0855 \~4″, ε Indi B \~2.4″ with a 6.2″ pixel. The full baseline is shorter than it looks: SPHEREx's first visit to Barnard is August 2025, the last is September 2026, i.e. \~1.1 yr and \~1.8 pixels. Coverage of the test targets, checked in IRSA on 2026-11-14 (DR1 + QR3, wide + deep, radius 0.01°):

| Target | Images | Visits | Max baseline → shift |
| --- | --- | --- | --- |
| Barnard's Star | 363 | 2025-08/10 · 2026-03/05 · 2026-08/09 | \~1.1 yr → \~11″ ≈ 1.8 px |
| ε Indi B | 468 | 2025-04/06 · 2025-09/11 · 2026-04/05 · 2026-09/10 | \~1.4 yr → \~6.6″ ≈ 1.1 px |
| WISE 0855 | 258 (DR1 only, none in QR3 yet) | 2025-05 (only 30 images) · 2025-10/12 · 2026-04/05 | \~1.0 yr → \~8″ ≈ 1.3 px |
| RW Aur | 336 | 2025-09 · 2026-02/03 · 2026-09 | brightness test |
| R Dra | 2,514 (Deep field) | continuous 2025-04 … 2026-09 | brightness test |

So the blink should show the first and the last epoch, not only neighbouring ones. AllWISE (2010) can be added as a very old epoch to make motion more obvious. SPHEREx saturates at roughly 11.7–9.7 AB mag ([source](https://arxiv.org/pdf/2604.22983)), so bright targets need honest display of saturation flags.

## SPHEREx: what you need to know

A SPHEREx image is not "a photo through one filter": the wavelength changes across the frame, so the same point of the sky falls at different wavelengths in different exposures. This drives the whole blink logic: compare images at similar wavelengths, otherwise a change of colour looks like a change of brightness.

| Parameter | Value |
| --- | --- |
| Launch / survey start | 11 March 2025 / 1 May 2025 ([source](https://arxiv.org/pdf/2506.13863)) |
| Coverage | whole sky every \~6 months; 4 passes in the 2-year nominal mission |
| Spectrum | 0.75–5.0 µm, 102 channels = 6 bands × 17, R ≈ 35–130 |
| Detectors | 6 × H2RG 2048×2048, each with its own linear variable filter (LVF); 1 detector = 1 band |
| Pixel / field of view | 6.2″ / 3.5° × 3.5° per detector, 3.5° × 11° in total |
| Exposure | 112.5 s, \~600 exposures per day |
| Sensitivity | deeper than 18.4 AB mag (5σ) per spectral bin at 2 µm ([Crill et al. 2024](https://arxiv.org/pdf/2404.11017)); to be confirmed whether this is the full-mission depth or a single frame: conclusions about WISE 0855 and Planet Nine depend on it |
| Saturation | roughly 11.7–9.7 AB mag; the brightest stars have a black core |

Bands 1–3 (0.75–2.42 µm) have R = 41, band 4 (2.42–3.82 µm) R = 35, bands 5–6 (3.82–5.0 µm) R ≈ 110–130. Bands 5–6 are the useful ones for cold brown dwarfs. Band 1 images (0.75–1.11 µm) show a bright arc of the 1.083 µm helium line from Earth's atmosphere — it is not an object ([SPHEREx first images](https://spherex.caltech.edu/image/spherex20250401b-spherex-first-images)).

## Data and access

Everything needed is in the NASA/IPAC IRSA archive and is available without authentication. The main product is calibrated level-2 **Spectral Images**. As of 2026-11-14 there are two sets: **DR1** (`spherex_dr1`, released October 2026, images up to May 2026) and **QR3** (`spherex_qr3`, weekly Quick Releases since August 2026) ([QR overview](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html)). QR2 was removed from SIA: a query for `spherex_qr2` returns 0 rows. Sample files from both sets carry the pipeline tag `l2b-v27`, so they can be mixed. DR1 also includes **spectral cubes** (`spherex_dr1_cube`, HiPS tiles), but for the blink we work with individual exposures.

**What is inside a file (multi-extension FITS):** `IMAGE` (surface brightness in MJy/sr), `FLAGS` (bitmask: cosmic rays, saturation, known sources), `VARIANCE`, `ZODI` (zodiacal light model), `EPSF` (PSF) and `WCS-WAVE` (wavelength of each pixel); the celestial WCS is `RA---TAN-SIP` ([Spectrophotometry Tool docs](https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html)). The `FLAGS` bits are the "contamination flags" from the challenge text.

| Method | How | When to use |
| --- | --- | --- |
| astroquery (Python) | `Irsa.query_sia(pos=(coord, radius), collection='spherex_dr1')` (and likewise `spherex_qr3`); one result row = one image ([tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-intro)) | main path for the backend |
| SIA2 over HTTP | `https://irsa.ipac.caltech.edu/SIA?COLLECTION=spherex_dr1&POS=circle+RA+DEC+0.01&RESPONSEFORMAT=CSV` ([documentation](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access)) | from any language, C# included |
| Cutout service | append `?center=RA,Dec&size=0.1` (degrees) to the image URL; it cuts `IMAGE/FLAGS/VARIANCE/ZODI` but returns `EPSF` (\~4 MB) and `WCS-WAVE` in full, so **every cutout weighs \~4 MB** regardless of size ([IRSA](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html)) | always instead of the full file; a target is \~360–470 images ≈ 1.5–1.9 GB, so cache processed stacks, not raw cutouts |
| TAP | `https://irsa.ipac.caltech.edu/TAP` via pyvo ([tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts)) | metadata: dates, detectors, wavelengths; list of collections: `SELECT obs_collection, COUNT(*) FROM ivoa.obscore WHERE obs_collection LIKE 'spherex%' GROUP BY obs_collection` |
| AWS S3 | `s3://nasa-irsa-spherex/` (anonymous, `--no-sign-request`; plain HTTPS also works) — prefixes `dr1/`, `qr2/`, `qr3/` (QR2 is still in S3 although SIA dropped it), same paths as IRSA (`dr1/level2/<week>/<version>/<detector>/…`); full file \~65 MB, HTTP range requests supported ([AWS Open Data](https://registry.opendata.aws/spherex-qr/)) | bulk download; maybe reading only the needed rows of `IMAGE/FLAGS/VARIANCE` via `fits.open(use_fsspec=True)` + `.section` — to be measured (FITS rows are contiguous, so a 97-px window still reads \~0.8 MB per extension) |
| SPHEREx Data Explorer | IRSA web application | manual checks and comparisons |
| Spectrophotometry Tool | forced photometry (Tractor) on all images of a point → spectrum table | the reference for our "spectrum on the fly" |
| SPHEREx HiPS (CDS) | `CDS/P/SPHEREx/QR2/D1`…`D6`, `CDS/P/SPHEREx/QR2/color` | background and context in Aladin Lite without a backend |

**Collections (as of 2026-11-14):** `spherex_dr1` (Wide Survey), `spherex_dr1_deep` (Deep Survey near the ecliptic poles), `spherex_dr1_cal` (calibration files), `spherex_dr1_cube` (spectral cubes), `spherex_qr3` and `spherex_qr3_deep` (new weekly data). The names change with every release, so code must not hardcode them but discover them via TAP. Data appear in SIA with about a one-day delay, so the simplest "update for new releases" is to cache cutouts and processed stacks while refreshing the lists of collections and images with a TTL.

**Auxiliary sources for overlays and checks:**

- **Gaia DR3** — positions and proper motions of stars; can be propagated to the image date and overlaid as markers.
- **AllWISE / unWISE** — the sky of the 2010s–2020s at 3.4 and 4.6 µm; gives a long baseline for visible motion ([unWISE at IRSA](https://irsa.ipac.caltech.edu/data/WISE/unWISE/overview.html)).
- **HiPS tiles** 2MASS / AllWISE / DSS2 — backgrounds for Aladin Lite.
- **SIMBAD** — object name → coordinates and proper motion (for search by name).
- **SkyBoT (IMCCE) / MPC MPChecker / JPL Horizons** — known asteroids in the field at the image date.

## Architecture and pipeline

A Python backend does all astronomical processing; the browser receives ready frames and only displays them. This way FITS never has to travel to the browser.

```
browser (React + Aladin Lite) ──RA/Dec, FOV, detector──► backend (FastAPI) ──► SIMBAD · IRSA (TAP, SIA, cutouts/S3) · Gaia DR3 · SkyBoT
```

The backend runs 5 steps:

1. **Resolve** — name → coordinates, proper motion, epoch (SIMBAD).
2. **Query** — list of collections from TAP, SIA query, grouping of images by detector and visit (Deep fields — by 30-day bins).
3. **Fetch** — cutouts with a concurrency limit, retries and a disk cache.
4. **Process** — background subtraction, FLAGS mask, λ at the target pixel, reprojection onto a common north-up grid, a stack per visit.
5. **Serve** — frames as Float32 arrays + flags + a JSON manifest.

The browser sends coordinates and receives frames with flags and metadata; it computes contrast and frame differences itself. The backend's disk cache protects against a slow archive, and static bundles of the five test targets work even without a backend.

**Minimal backend API:**

- `GET /api/sequence?ra=&dec=&fov=&det=&mode=` → a ready sequence of frames or a `job_id`: the first request is slow, so the frontend polls `/api/jobs/{id}` and shows progress
- `GET /api/spectrum?ra=&dec=&pmra=&pmdec=` → points (λ, flux, error, date, flags)
- `GET /api/overlays?ra=&dec=&fov=&mjd=` → Gaia DR3 stars at the frame date and known asteroids
- `GET /api/resolve?name=` → coordinates and proper motion from SIMBAD

The frontend reads the same parameters from its own URL (`/?ra=...&dec=...`), so links and embeds work without extra logic. Full API contract: `docs/api.md`.

## Pitfalls

Most problems are not in the code but in the physics and the quirks of the data. Check these before polishing the UI.

1. **Different wavelengths at different epochs.** Because of the LVF, the same point has a different λ in different exposures, and a red dwarf will "blink" without any real change. Compare images from the same detector at nearly the same λ, or co-add all images of a detector within one survey pass (which is what the challenge suggests).
2. **Motion smaller than a pixel.** Even Barnard's Star moves only \~0.8 pixel in half a year. One team reports that its detector misses motion below \~0.8 pixel over the whole period ([SPHEREx Blink](https://github.com/mateibut/SPHEREx)). Remedy: the longest baseline, upsampling for display, an old AllWISE epoch as an extra frame.
3. **Catalog coordinates are outdated** by 2–4.5′ for the test targets (see above). Centre the field on the position propagated to the image date.
4. **Saturation and artifacts.** Bright stars (Barnard, R Dra, ε Indi A) produce a black core, a halo (BLOOM), an inverted ghost exactly 32 rows above from crosstalk; cosmic rays leave "snowball" blobs ([artifact overview](https://blog.pebblous.ai/blog/spherex-detector-artifact-bestiary/en/); this is a blog and the details are unverified — take the FLAGS bit meanings from the official IRSA documentation). It is easier to show all this as an overlay from `FLAGS` than to hide it.
5. **Zodiacal background and unevenness.** Before blinking, subtract the zodiacal light model or the background median and use a shared asinh stretch for all frames, otherwise the frames flicker in brightness.
6. **Reprojection.** The PSF is undersampled: bilinear interpolation flattens peaks and leaves star residuals in differences; a cubic spline is better ([another team's experience](https://github.com/lzphellipe/spherex)). Align all frames on a common north-up grid.
7. **Archive speed and volume.** Reading SPHEREx files can exceed astropy's default timeout (`conf.remote_timeout = 120`). Every cutout weighs \~4 MB because of the untrimmed `EPSF`, so one target is 1.5–1.9 GB and R Dra in the Deep field is more than 10 GB (a per-visit image cap is needed). For the demo, build static bundles of all five test targets — a live request during the pitch is a risk. On a Mac with Python from python.org, HTTPS to IRSA fails with `CERTIFICATE_VERIFY_FAILED`: run `Install Certificates.command`.
8. **External APIs fail.** One team's JPL identification API timed out and SkyBoT blocked its requests ([GhostShift](https://github.com/ahmedatta3322/ghostshift)). Cache responses and have a fallback source.
9. **WISE 0855 is barely visible.** At J ≈ 25 it is absent at short wavelengths. One team got only a "hint" in a stack (0.4 mJy, 4.3× the noise), not a detection. Better to honestly show the expected position and the sensitivity limit than to claim a detection.
10. **Don't expect Planet Nine from SPHEREx.** A Planet Nine–like body hundreds of AU away is 3–5 magnitudes fainter than the single-image limit. Infrared searches in IRAS/AKARI produced only unconfirmed candidates ([Phan et al. 2025](https://arxiv.org/abs/2504.17288)). Planet X is a story for the pitch, not a promise.

## How to stand out

Almost everyone builds an RA/Dec blink viewer: GitHub already has dozens of repositories for this challenge (e.g. [planetx-spherex](https://github.com/gitmahin/planetx-spherex), [spherex-blink](https://github.com/pythonhack000/spherex-blink), [GhostShift](https://github.com/ahmedatta3322/ghostshift)). So the winner will not be decided by the blink itself but by the "Potential Considerations" done well and an honest demonstration on the test targets.

- **Spectrum on the fly (extra kudos in the challenge).** Click an object → aperture photometry on all images where the point falls at different λ → a flux-vs-λ plot. For moving objects the aperture follows the proper motion. A comparison with IRSA's Spectrophotometry Tool (and, for static sources, with the DR1 spectral cubes) shows the numbers are real.
- **Per-detector stacks and difference mode.** For each survey pass, co-add all images of one detector (higher S/N), then subtract passes: a moving object gives a dipole (dark at the old position, bright at the new one), a variable star a single blob.
- **Pseudo-colour from the 6 detectors.** Three bands → RGB: brown dwarfs and icy sources stand out by colour, like WISE 0855 as an orange dot in Backyard Worlds.
- **Gaia DR3 overlays propagated to the frame date.** The marker moves together with the star in the blink — a visual check that the motion is real. Plus AllWISE (2010) as a very old frame.
- **Motion measured in numbers.** For ε Indi B (not saturated) and Barnard (saturated, centroid less reliable) show the measured proper motion with its error next to the catalog value. Agreement within the error is a strong argument for the judges. For reference: one team got a discrepancy of 0.2–0.8″/yr.
- **Light curves for the variables.** For RW Aur and R Dra — a flux-vs-date plot next to the blink; saturated points labelled "saturated" rather than given a false number.
- **Shareable URL and embed.** `/?ra=269.45&dec=4.74&fov=10&det=3` + an iframe mode — it is right in the challenge text and cheap to build.
- **Citizen science.** An "I see a moving object" button with a click on the position → automatic check against SkyBoT and Gaia ("known asteroid" / "known star with proper motion" / "unknown"). This matches the spirit of the challenge — involve as many people as possible.
- **Honesty in the pitch.** Show what the tool can and cannot see (WISE 0855 at the limit, Planet Nine out of reach). Judges of science challenges value this more than loud claims.

## Hackathon plan and roles

Goal by Saturday evening: a working blink and frame difference for Barnard's Star and ε Indi B on real data; everything else is layered on top. The detailed plan with tracks, P0/P1/P2 priorities and checkpoints is in `docs/agent-prompt.md`. Stack: Python (FastAPI + astropy, astroquery, reproject, photutils) for data, React + Aladin Lite v3 for the frontend. Processing FITS in C# does not pay off: the astronomy ecosystem is Python.

**Roles (for 3–4 people):**

- **Data / backend** — SIA queries, cutouts, reprojection, stack/difference, spectrum, cache.
- **Frontend** — RA/Dec form, frame player, slider, Aladin, overlays, URL parameters.
- **Science / QA** — test targets, position propagation, checks against catalogs and the Spectrophotometry Tool.
- **Pitch** — video, project description, submission (requirements are in the Participant Guides on the Space Apps site).

**Saturday, day — foundation**

- [ ] Work through the IRSA notebooks `spherex-intro` and `spherex-cutouts`
- [ ] Script: RA/Dec + detector → list of images with dates → cutouts → visit stacks (Float32) with a shared stretch
- [ ] Proper-motion propagation of positions for the test targets
- [ ] Frontend skeleton: RA/Dec form + frame animation

**Saturday, evening — first end-to-end result**

- [ ] Blink of Barnard's Star from real data in the browser
- [ ] Reprojection onto a common north-up grid, field-of-view selection
- [ ] Per-detector stack within a pass + difference mode
- [ ] Static bundles of all five test targets (working without a backend)

**Sunday, morning — features from the Considerations**

- [ ] Overlays: Gaia DR3 (propagated to the date), FLAGS, an AllWISE frame
- [ ] Spectrum on click + light curves for RW Aur / R Dra
- [ ] Coordinates in the URL, embed mode, search by name via SIMBAD

**Sunday, day — freeze and submission**

- [ ] Deploy and check from a clean browser
- [ ] Screenshots/GIFs for each test target, a "limitations" section
- [ ] Video and project description, submission before the hackathon closes on 15 November

## Sources

**Challenge and official resources**

- [Planet X and SPHEREx — challenge page](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/) (Details and Resources tabs)
- [IRSA: SPHEREx mission page](https://irsa.ipac.caltech.edu/Missions/spherex.html) · [QR Overview](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html)
- [SPHEREx Data Access (User Guide)](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access)
- [IRSA tutorial: SPHEREx intro](https://caltech-ipac.github.io/irsa-tutorials/spherex-intro) · [cutouts](https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts) · [source discovery tool](https://caltech-ipac.github.io/irsa-tutorials/spherex-source-discovery-tool-demo)
- [SPHEREx Cutout Service](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html) · [Spectrophotometry Tool](https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html)
- [SPHEREx on AWS Open Data](https://registry.opendata.aws/spherex-qr/)
- [SPHEREx HiPS at CDS (color)](https://alasky.cds.unistra.fr/SPHEREx/color) · [IRSA TAP](https://irsa.ipac.caltech.edu/TAP)
- [WiseView (ASCL)](https://ascl.net/1806.004) · [WiseView blog post](https://blog.backyardworlds.org/2017/09/13/wiseview/) · [Backyard Worlds](https://en.wikipedia.org/wiki/Backyard_Worlds)

**The SPHEREx mission**

- [Crill et al. 2024 — SPHEREx all-sky survey](https://arxiv.org/pdf/2404.11017)
- [Spectral response of SPHEREx](https://arxiv.org/pdf/2602.09139)
- [SPHEREx first images](https://spherex.caltech.edu/image/spherex20250401b-spherex-first-images)
- [POKEMON-DLC (SPHEREx saturation limit)](https://arxiv.org/pdf/2604.22983)

**Test targets and Planet Nine**

- [Barnard's Star](https://en.wikipedia.org/wiki/Barnard%27s_Star) · [Epsilon Indi](https://en.wikipedia.org/wiki/Epsilon_Indi) · [ε Indi Ba/Bb (McCaughrean et al.)](https://arxiv.org/pdf/astro-ph/0309256) · [WISE 0855−0714](https://en.wikipedia.org/wiki/WISE_0855%E2%88%920714) · [RW Aurigae](https://en.wikipedia.org/wiki/RW_Aurigae) · [R Draconis (BAA)](https://britastro.org/vss/obj-dra.html)
- [Phan et al. 2025 — Planet Nine in IRAS and AKARI](https://arxiv.org/abs/2504.17288)

**Other teams' repositories (for orientation)**

- [SPHEREx Blink (mateibut)](https://github.com/mateibut/SPHEREx) · [GhostShift](https://github.com/ahmedatta3322/ghostshift) · [SPHEREx Moving Objects](https://github.com/lzphellipe/spherex) · [planetx-spherex](https://github.com/gitmahin/planetx-spherex) · [spherex-blink](https://github.com/pythonhack000/spherex-blink)
