# Submission and deployment (Track D)

## OD-3 — Space Apps submission rules (checked 2026-11-14)

Source: the official *Project Submission Guide*, spaceappschallenge.org/resources/project-submission-guide/ (dated 2026-11-13).

- **Deadline:** click "Submit for Judging" before **Sun 2026-11-15, 23:59 local time of our Local Event**
  (Universal Event: the Team Owner's local time). Our Local Event is **Kyiv** ⇒ **2026-11-15 23:59 EET (UTC+2) =
  21:59 UTC**. The Kyiv Local Lead may set an earlier local-judging cutoff — **ask**. Only the Team Owner (not Track D)
  may be able to submit — confirm who clicks the button.
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

## Azure Container Apps + CI/CD (team OK on 2026-11-15)

```
GitHub ── PR / push ──► CI: ruff · mypy · pytest · oxlint · vite build · compose + azure image smoke tests · bicep lint
                                                       · gitleaks (blocking) · trivy (report only)
main, CI green ──► Deploy (OIDC, no stored secret): bicep pass 1 (ACR, env, logs, budget)
                   → build + push both images (tag = commit SHA) → bicep pass 2 (apps) → smoke test → prune ACR
Azure: one app spherex-blink-web, 0–1 replica, one container (infra/app.Dockerfile):
       nginx (public HTTPS) ──/api, /files via 127.0.0.1:8000──► backend
```

Files: `infra/main.bicep`, `infra/bootstrap.sh`, `.github/workflows/{ci,deploy}.yml`, `.github/dependabot.yml`.

**One-time setup** (a subscription Owner, Git Bash or any shell with `az`):
1. `az login`, then `infra/bootstrap.sh Donbas-Solutions@356984066/Donbas-Solutions-Planet-X-and-SPHEREx@1457654112 [rg-spherex-blink] [polandcentral]`.
   The organisation sends immutable OIDC subjects (`owner@id/repo@id`, seen 2026-11-15 in `AADSTS700213`); a
   plain `owner/repo` subject is never matched there.
   It registers the resource providers, creates the resource group and the app registration
   `spherex-blink-github-deploy` with a federated credential for the GitHub environment `production`, and gives it
   Contributor on that resource group plus the right to grant only `AcrPull` (an ABAC condition).
2. GitHub → Settings → Environments: create `production` (add required reviewers for a manual approval gate).
3. GitHub → Settings → Secrets and variables → Actions → **Variables, repository level** (environment variables are
   not visible to the job's `if`): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
   `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION` (printed by the script). They are IDs, not secrets: the job reads
   `vars.*`, so values stored under Secrets leave it skipped. Optional: `BUDGET_EMAIL`,
   `MIN_REPLICAS`. Our subscription is Azure for Students: its policy allows only `spaincentral`,
   `switzerlandnorth`, `francecentral`, `germanywestcentral`, `polandcentral` (checked 2026-11-15; `westeurope` is
   refused with `RequestDisallowedByAzure`). Our resource group is in `westeurope`, its resources in `polandcentral`.
4. Actions → Deploy → Run workflow. The site URL appears on the run and in the environment.

Until step 3 is done the Deploy job is skipped, so `main` stays green.

**Cost** (estimates; check the Azure pricing calculator): idle ≈ ACR Basic ~$5/month + a few cents of logs (ingestion
capped at 0.1 GB/day). The app scales to zero and bills per second while it runs; at 1.25 vCPU / 2.5 GiB it costs
roughly $0.13 per busy hour. `MIN_REPLICAS=1` (always warm, e.g. during judging) bills the idle rate around the clock,
roughly $25–30 a month.
`BUDGET_EMAIL` sets a $20/month alert at 80 % actual and 100 % forecast.

**Why one container with nginx and the backend:** the environment came up as an *express* environment
(`properties.environmentMode: "Express"`, visible from API version 2026-07-01; 2026-11-15). It rejected
`allowInsecure` (`ExpressAllowInsecureNotSupported`), gave an `external: false` app a public FQDN (no `.internal.`
names) and rejected a second container (`Sidecar Containers is not supported`). So `infra/app.Dockerfile` runs both
processes (`infra/app-start.sh`, the container exits when either dies), they talk over localhost and only nginx is
public. Azure also has no IPv6 inside containers: nginx listens on IPv4 only. CI builds this image and smoke-tests
it with IPv6 disabled. `compose.yaml` keeps the two separate images for local runs.

**Limits of this setup:** one replica at most (jobs live in the backend's memory); the cache is the container's
ephemeral disk, lost on scale-to-zero or restart; the prebaked bundles are part of the frontend image. A cold start
pulls the ~900 MB image and can take a minute or more; with `MIN_REPLICAS=1` there is none.
To tear everything down: `az group delete -n rg-spherex-blink`.

## OD-1 — hosting (deferred, superseded by the Azure section above)

**Decision 2026-11-14:** no deploy for the submission — it is not required. We test locally; the "link to final
project" is the public GitHub repository, run from the README. The proposal below is kept for later. If revisited:
Netlify's free plan for accounts created after 2025-09-04 is credit-based (300 credits/month, ~15 per production
deploy, the site pauses when they run out), so it is risky for frequent deploys; Azure (Static Web Apps + Container
Apps, team credits) is the alternative.

What we need (NFR-4): a static frontend with the prebaked bundles that stays up for weeks after the event; a backend
(Docker, cache on disk) that may sleep — the UI then falls back to `/prebaked/` (FR-14).
Size: the 5 committed bundles are **13 MB** (10′ FOV → 97×97 frames, 75 KB per frame incl. flags; R Dra is the
largest at 5 MB). No single file is over 1 MB.

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
