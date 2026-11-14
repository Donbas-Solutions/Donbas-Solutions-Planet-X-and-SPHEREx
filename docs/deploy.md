# Submission and deployment (Track D)

## OD-3 — Space Apps submission rules (checked 2026-11-14)

Source: the official *Project Submission Guide*, spaceappschallenge.org/resources/project-submission-guide/ (dated 2026-11-13).

- **Deadline:** click "Submit for Judging" before **Sun 2026-11-15, 23:59 local time of our Local Event**
  (Universal Event: the Team Owner's local time). Our Local Lead may set an earlier local-judging cutoff — **ask**.
  Save or submit after the deadline → not judged. Resubmitting is allowed until then; the last save counts.
- **Required fields (English only):** project name; high-level summary; link to project demo; link to final project;
  detailed description (what, how, benefits, tools); use of AI ("SI"); NASA data used (≥1 NASA resource required
  for a Global Award); space-agency partner data and all other references (code, text, images, even open source).
- **Demo:** a video of **≤30 s** (another spoken language allowed only with English subtitles) **or** a deck of
  **≤7 slides** including title/intro slides. Over the limit → not eligible for Global Judging.
  Slides must show the team name, members' names and the chosen challenge.
- **Links:** demo and final project hosted externally (YouTube, Drive, GitHub, …), **public, no login or permission**.
  Test them in a private window. The page accepts images (JPG/PNG/GIF ≤10 MB), not videos or documents.
  For a new website, a FortiGuard web-filter classification request is recommended (optional).
- **AI disclosure:** AI tools are allowed, but not for coming up with the idea. Mark where and how they were used:
  images/videos — visible watermark; code and data — acknowledged in descriptive text and metadata.
  ⇒ README states that code was written with Claude Code; generated images (if any) get a watermark.
- **Branding:** generated content may not use, contain or modify NASA branding (NASA logos, flags, mission
  identifiers). ⇒ no NASA/SPHEREx logos in the UI, deck or video; text credits only (NFR-10).
- **Other:** no images/video/audio of persons under 18. Checkboxes "Terms and Conditions" and "Confirm All Work is
  Original" on submit. Judging criteria: Impact, Creativity, Validity, Relevance, Presentation.

## OD-1 — hosting proposal (team decides)

What we need (NFR-4): a static frontend with the prebaked bundles that stays up for weeks after the event; a backend
(Docker, cache on disk) that may sleep — the UI then falls back to `/prebaked/` (FR-14).
Size estimate: a 290×290 frame is 336 KB of Float32 + 336 KB of flags; 5 targets ≈ 200 frames ≈ **150 MB** in total,
mostly R Dra (30-day bins). No single file is over 1 MB.

| Part | Proposal | Why | Alternatives |
|---|---|---|---|
| Frontend + bundles | **Netlify** (free tier; confirm current bandwidth limits at signup) | Serves at the domain root (our URLs are absolute: `/mock/…`, `/prebaked/…`); `_redirects` gives SPA fallback for `/embed` **and** can proxy `/api/*` + `/files/*` to the backend, so the frontend stays same-origin with no CORS and no code change | Cloudflare Pages (no external proxy without a Pages Function); GitHub Pages (repo is private → needs a paid plan or a public repo; serves under `/<repo>/`, which breaks absolute URLs) |
| Backend | **Hugging Face Spaces, Docker** (free CPU) | Docker as-is, 16 GB RAM, sleeps when idle — allowed by NFR-4 | Fly.io (persistent volume, needs a card); Render free (sleeps, no disk) |

Free-tier disk on Spaces is ephemeral: the raw cache is lost on restart. That is acceptable because prebaked bundles
cover the 5 targets. Each option needs an account → **human OK required** before creating one.

## Walking skeleton (no host chosen yet)

`npm run build` → `frontend/dist/` (3.3 MB incl. the mock bundle; Aladin chunk 2.4 MB, lazy-loaded) is the whole
static site. Checked locally with `vite preview` (launch config `frontend-dist` in `.claude/launch.json`): the mock
sequence loads and blinks from the static build with no backend.

Once a host is approved, the deploy is: build → upload `frontend/dist/` (CLI or Git integration) → open the public URL
in a private window → check `/?manifest=/mock/sequence.json`.

Found on the way (input for D1): on 2026-11-14 CDS HiPS hosting was down (`alasky.unistra.fr` did not resolve,
`alasky.cds.unistra.fr` returned 404 even for DSS) while the IRSA mirror
`irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color` answered. The context panel needs mirror fallbacks.
