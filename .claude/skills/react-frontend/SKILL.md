---
name: react-frontend
description: React 19 + TypeScript + Vite conventions for this repo's frontend/. Use before writing or changing anything in frontend/ - components, hooks, state, URL sync, data fetching and job polling, the canvas blink player, diff mode, flags overlay, coordinate input, Aladin Lite, charts, CSS, accessibility - and before committing frontend changes. Covers strict TypeScript, Rules of React and hooks, effects and cleanup, pixel/sky conventions, shared stretch, diff and flag rules, performance of typed-array rendering, a11y (WCAG 2.2, flashing content), security, oxlint, npm and comments.
---

# React frontend conventions

Project facts (stack, science rules, guardrails, commands) live in `CLAUDE.md`; the API contract lives in
`docs/api.md` + `frontend/src/api/types.ts`; the Track B plan lives in `docs/agent-prompt.md`. This skill is *how*
to write the frontend code. If it ever conflicts with `CLAUDE.md`, `CLAUDE.md` wins.

## Workflow

1. Read the code you are changing first and match its style (2 spaces, single quotes, no semicolons, trailing commas).
2. Develop against the mock bundle: `npm run dev` → `http://localhost:5173/?manifest=/mock/sequence.json`.
   The backend is optional; the app must stay usable with it off (prebaked/mock fallback).
3. Before calling the work done or committing, both must pass with **zero errors and zero new warnings**:
   ```
   cd frontend && npm run build && npm run lint
   ```
   `build` runs `tsc -b` (type check) then `vite build`. Never commit with type errors "to fix later".
4. Check the change in a browser: no console errors or React warnings, works at 360 px width and on desktop,
   works with keyboard only.
5. Dependencies: `npm install <pkg>` (`-D` for tooling); commit `package.json` + `package-lock.json` together.
   `aladin-lite` stays pinned at exactly `3.8.2`. Ask the team before adding any runtime dependency; prefer the
   platform (fetch, URL, Intl, canvas) or a dependency already present. Check bundle impact and the license
   (the repo license must stay compatible with Aladin's GPL/LGPL-3).

## Layout

```
src/
  api/types.ts      contract types (mirror of docs/api.md + backend/app/models.py) — change all three together
  api/*.ts          fetch functions: one place that knows URLs, status codes, polling, fallback order
  lib/*.ts          pure logic: stretch, flags, coordinate parsing, frame decoding — no React imports
  hooks/use*.ts     custom hooks that glue lib/ + api/ to React state
  components/*.tsx  one component per file, PascalCase file = component name
  App.tsx, main.tsx
```

- Keep logic out of components: anything testable without a DOM (parsing sexagesimal, stretch math, flag masks,
  URL ↔ state mapping) goes in `lib/` as pure functions with explicit types.
- A component file exports components only (oxlint `react/only-export-components`, needed for Fast Refresh).
  Shared constants/helpers live in `lib/`.
- Relative imports, no path aliases unless the team adds one to both `tsconfig.app.json` and `vite.config.ts`.
- Type-only imports use `import type` / inline `type` (`verbatimModuleSyntax` is on).

## TypeScript

- Strict mode is mandatory (TS ≥ 6 enables it by default; never turn any strict flag off). `noUnusedLocals`,
  `noUnusedParameters` and `erasableSyntaxOnly` are on: no `enum`, no `namespace`, no parameter properties —
  use union literal types and `as const` objects instead.
- `noUncheckedIndexedAccess` is on: `arr[i]` is `T | undefined`, typed arrays included. In pixel loops write
  `data[i] ?? Number.NaN` / `flags[i] ?? 0`; elsewhere destructure or check. Never reach for `!` to get past it.
- **No `any`.** Use `unknown` and narrow. The only sanctioned `any` is the untyped `aladin-lite` module
  declaration; wrap Aladin in a small typed interface at the boundary instead of spreading `any`.
- Data from the network is `unknown` until checked. `res.json() as Sequence` is acceptable only for our own
  backend/manifest that is typed by the contract; anything else (SIMBAD, URL params, localStorage) is validated.
- No non-null assertions (`!`) except the single `getElementById('root')!` in `main.tsx`. Handle `null`/`undefined`.
- Prefer `interface` for object shapes and props, `type` for unions and aliases. Name props `Props` (local) or
  `<Component>Props` (exported).
- Use discriminated unions for state machines instead of several booleans:
  ```ts
  type LoadState =
    | { status: 'idle' }
    | { status: 'loading'; progress: number }
    | { status: 'ready'; seq: Sequence }
    | { status: 'error'; message: string }
  ```
  and make `switch` exhaustive (`const never: never = x`).
- Annotate exported function return types. Locals and callbacks can rely on inference.
- `readonly` arrays/tuples for data you don't mutate; never mutate props, state or contract objects.
- Name values with units when there is no type for it: `fovDeg`, `radiusArcsec`, `intervalMs`, `mjd`.

## React (19): Rules of React

- Components and hooks are **pure** during render: no side effects, no mutation of outside variables, no
  `Math.random()`/`Date.now()` in render output. StrictMode (on in `main.tsx`) double-invokes render and effects in
  dev to surface violations — fix the cause, never remove StrictMode.
- Function components only. Hooks only at the top level of components/custom hooks (`react/rules-of-hooks`
  is an error); custom hooks are named `useX`.
- Never call a component as a function (`Foo()`); render it (`<Foo />`).
- Props are destructured in the signature with defaults there (`{ survey = 'CDS/...' }: Props`), not
  `defaultProps`. `ref` is a regular prop in React 19 — no `forwardRef` in new code.

### State

- Keep the minimal state; **derive** everything else during render (`const step = ...`, `useMemo` if expensive).
  Never copy props into state, never sync two states with an effect.
- One source of truth for things in the URL (target, fov, frame index, fps, stretch): parse the URL into state once,
  write it back with `history.replaceState` (`pushState` only for user navigations worth a Back step).
- Updates that depend on the previous value use the updater form: `setIndex((i) => (i + 1) % n)`.
- Lift state to the closest common parent; reach for context only for truly app-wide values. No global state
  library unless the team agrees.
- Reset a subtree's state by changing its `key` (e.g. new sequence → `<Player key={seq.meta.generated_at} />`),
  not with an effect.
- `key` is a stable id (`frame.id`), never the array index for lists that can change.

### Effects

- An effect is for **synchronizing with an external system** (network, canvas, Aladin, timers, `keydown`
  listeners, `document.title`). If no external system is involved, you don't need an effect
  (see react.dev "You Might Not Need an Effect"). Event-specific logic goes in event handlers.
- Every effect that subscribes, starts a timer, fetches or creates an object **cleans up**. Fetches use
  `AbortController` and ignore `AbortError`:
  ```ts
  useEffect(() => {
    const ac = new AbortController()
    loadSequence(url, ac.signal).then(setSeq, (e: unknown) => {
      if (!ac.signal.aborted) setError(errorMessage(e))
    })
    return () => ac.abort()
  }, [url])
  ```
- Dependency arrays are complete and honest. Don't silence the linter; restructure instead (move the function
  inside the effect, use the updater form, or `useEffectEvent` for non-reactive logic).
- Polling (job status) uses `setTimeout` chains, not `setInterval`, stops on `done`/`error`/unmount, and backs off.

### Refs and imperative code

- `useRef` for DOM nodes and mutable values that must not trigger renders (animation frame id, Aladin instance,
  last timestamp). Don't read or write `ref.current` during render.
- Imperative libraries (canvas, Aladin Lite) live behind one component that owns them: create in an effect, update
  through the instance on prop change (`aladin.gotoRaDec`, `setFoV`) instead of recreating, destroy in cleanup.
- Aladin Lite 3.8.2: `await A.init` (WASM) before `A.aladin(el, options)`; keep `cooFrame: 'ICRS'`; survey ids
  are the HiPS ids in `CLAUDE.md`. Present in the 3.8.2 bundle: `gotoRaDec`, `setFoV`, `setBaseImageLayer`,
  `newImageSurvey`, `A.catalogFromVizieR`. The package ships no types — check signatures against the 3.8.2 API
  docs and add each method you use to a typed interface in `src/aladin-lite.d.ts`.
  `components/AladinPanel.tsx` is still the Phase 0 skeleton (it recreates the instance on every prop change);
  B5 brings it in line with the rule above.

## Performance

- The blink player renders typed arrays to `<canvas>`: the per-pixel loop stays in `lib/` and runs outside React.
  Playback uses one `requestAnimationFrame` loop driven by refs, not `setState` per tick at 60 fps; only UI that
  shows the frame index re-renders.
- Precompute what is shared across frames (stretched `ImageData` per frame when the stretch changes, flag masks),
  not on every frame flip. For big work consider `OffscreenCanvas`/a Worker before micro-optimizing.
- Display upscaling via CSS size + `image-rendering: pixelated`, never by resampling data in JS.
- Lazy-load heavy, non-critical code with `lazy()` + `Suspense` (Aladin is already a separate chunk; do the same
  for chart libraries).
- `useMemo`/`useCallback`/`memo` only for expensive computations or to keep identity for a memoized child/effect
  dependency — measure (React DevTools Profiler) before adding them everywhere.
- Fetch frames in parallel but bounded; show progress; never refetch what is already loaded.

## Domain rules: frames, pixels, science

The conventions come from `docs/api.md` and the science rules in `CLAUDE.md`. Getting them wrong produces a
plausible-looking but scientifically wrong picture, so they are not optional.

### Pixel and sky geometry
- Arrays are row-major `[ny, nx]`, **row 0 = south**, x grows to the **west**; displayed north up, east left.
  Rows are flipped once, when drawing (`renderFrame`); never flip the data arrays themselves.
- Pixel positions (`expected_px`) are 0-based with the integer at the pixel **center**. Data → CSS position:
  `left = (x + 0.5) * zoom`, `top = (ny - 1 - y + 0.5) * zoom`. Screen → data is the exact inverse. Keep both
  directions as one pair of functions in `lib/`; markers, crosshair, click handling and overlays all use it.
- Pixel ↔ RA/Dec goes through `grid.wcs` (TAN, FITS cards, 1-based `CRPIX`) with a real gnomonic (de)projection
  in `lib/` — not `dec + dy * scale`, which ignores cos(dec) and breaks near the poles (R Dra is at +66.8°).
- The marker shows the **expected** position from proper motion, not a detection. Label it that way.

### Stretch and colormaps
- One shared stretch for every frame of a sequence (`seq.stretch` or the user's sliders). Never autoscale per
  frame: it would fake or hide brightness changes.
- `NaN` = no data. Draw it in a distinct color, never as 0 or black, and exclude it from any statistics.
- Guard `vmin === vmax` (division by zero) and keep `vmin < vmax` when sliders move.

### Diff mode
- Computed client-side from two `visit_stack` frames: **later − earlier** (by `mjd_mid`).
- Only like with like: same `detectors` in both frames. If `lambda_um` coverage differs, or either frame carries
  a warning, show the warning on the diff too.
- `NaN` in either input → `NaN` in the diff. Flags of the diff = bitwise OR of both inputs.
- The diff has its own stretch: symmetric around 0 (`vmin = -vmax`), diverging colormap, with a legend saying
  which color means "brighter later". It never reuses the intensity stretch.
- Help text explains the reading: dipole = moving source, single blob = variable source.

### Flags
- Build masks from `seq.flag_bits` by `group`; never hardcode bit numbers in the frontend.
- Flag arrays are uint32: `1 << 31` is negative in JS, so build masks with `>>> 0` and test with `!== 0`.
- Overlay `bad` and `saturation` (and optionally `artifact`) as separate, legend-labeled layers. `info` bits
  (including `SOURCE`, bit 21 — every known star) are hidden by default and never shown as "bad".
- Any number derived from pixels flagged `saturation` is displayed as "saturated", not as a value.

### Coordinate input
- Decimal RA is **degrees**; sexagesimal RA (`17 57 48.5`, `17:57:48.5`, `17h57m48.5s`) is **hours** → ×15.
  Dec is always degrees.
- Take the Dec sign from the string, not from the parsed degrees: `-00 30 00` is −0.5°, and `-0` loses the sign.
- Reject out-of-range input (RA 0–360, Dec −90…90, minutes/seconds < 60) with a message; don't clamp silently.
- The WISE 0855 preset uses `science/targets.json` (SIMBAD J2000 + PM), never the challenge-text coordinates.

### URL state
- The page URL params are defined in `docs/spec.md` §5.3 — that table is the source of truth; don't invent others.
  Params: `target` (preset id), `name`, `ra`/`dec` (decimal degrees or URL-encoded sexagesimal), `fov` (arcmin,
  2–30, default 10), `det` (`all` or a comma list of `1..6`), `view` (`blink` | `diff`), `a`/`b` (frame ids),
  `fps` (0.5–3, default 2), `stretch` (`asinh` | `linear` | `log`), `flags` (comma list of `saturation`, `bad`,
  `artifact`), `gaia` (`1` = Gaia DR3 stars overlay), `pmra`/`pmdec`/`epoch`, and `manifest` (development only).
- Precedence: `target` > `name` > `ra`/`dec`.
- Page params are not API params: the page has `view` and `epoch`, the API has `mode` and `ref_epoch`
  (`docs/api.md`). Map them in one place in `api/`.
- Adding or renaming a param = change spec §5.3 and tell the team (shared links and `/embed` depend on it).
- Omit params that hold their default. Unknown params are ignored; an invalid value falls back to the default with a
  visible notice, never a crash.

### Honest wording
- No "detected" for anything below 5σ: show S/N or a 5σ upper limit (WISE 0855 is at the detection limit).
- No Planet Nine / Planet X discovery claims anywhere in UI copy.
- The Limitations text stays reachable from every view, including `/embed`.
- Dates are UTC (`date_range` ISO, `mjd_mid` MJD); never format them in the local timezone.

## Data layer

- App URLs are root-absolute (`/api/...`, `/files/...`, `/prebaked/...`, `/mock/...`); the Vite proxy makes them
  same-origin in dev. They break if the site is served from a sub-path, so build static-asset URLs from
  `import.meta.env.BASE_URL` in one place in `api/`. Frame `data`/`flags` URLs resolve against the manifest URL
  (`new URL(frame.data, manifestUrl)`), never against the page.
- Config via `import.meta.env.VITE_*` only (types come from `"types": ["vite/client"]` in `tsconfig.app.json`;
  declare custom vars in a `src/vite-env.d.ts` when the first one is added). No secrets in the frontend —
  everything in the bundle is public.
- `GET /api/sequence` returns `200 Sequence` or `202` with a job id → poll `/api/jobs/{id}` and show
  `progress.stage` with `done/total`.
- Check the byte length of every binary against `shape` (`ny * nx * 4`) before wrapping it in a typed array.
- Check `res.ok`, turn HTTP failures into a readable message (status + what failed), and surface it in the UI.
  Fallback order (Track B): live API → `/prebaked/<target>/` → clear error message. Never fail silently.
- Every async UI state is explicit: loading (with progress where available), empty, error (with a retry), ready.
- Show contract `warnings` and incomplete λ coverage to the user; never hide them. Don't present a saturated or
  flagged value as a number (science rules in `CLAUDE.md`).

## Accessibility (WCAG 2.2 AA)

- Semantic HTML first: `button` for actions, `a` for navigation, `label` bound to every input, `main`/`header`/
  `nav`/`section` with headings in order. No clickable `div`s; if a custom widget is unavoidable, give it a role,
  `tabIndex`, keyboard handlers and an accessible name.
- Everything works with the keyboard; focus is always visible (don't remove outlines without a replacement).
  Global shortcuts (space, ←/→, B) are ignored while focus is in an input/select/textarea and are listed in Help.
- `<canvas>` gets `role="img"` and an `aria-label` describing the current frame (target, date, band). Icon-only
  buttons get `aria-label`. Progress and status changes use `aria-live="polite"` / `<progress>`.
- Text contrast ≥ 4.5:1 (3:1 for large text and UI controls). Don't encode meaning by color alone (flags overlay,
  saturated points: also shape/label/legend).
- **Flashing:** a blink is flashing content. Respect `prefers-reduced-motion` (don't autoplay; start paused),
  keep the default rate ≤ 3 Hz (WCAG 2.3.1), and require an explicit user action to go faster.

## Security

- Never use `dangerouslySetInnerHTML` or write to `innerHTML` with data; React escapes text for you.
- Treat URL params and object names as untrusted: validate/clamp numbers (RA 0–360, Dec −90…90, FOV limits from
  `docs/api.md`), build query strings with `URLSearchParams`, never by string concatenation.
- Only allow `http(s)` URLs in `href`/`src` built from data. External links: `rel="noopener noreferrer"`.
- The `/embed` mode must not expose anything the normal page doesn't; no `postMessage` handlers without an origin
  check.
- No personal data in requests or `localStorage`; wrap `localStorage` access in `try/catch`.

## Styling

- Plain CSS (`index.css` + per-component CSS files imported by the component) with class names; no inline style
  objects except for computed geometry (canvas size, marker position).
- Design tokens as CSS custom properties on `:root` (colors, spacing, font sizes); support dark color scheme
  via `prefers-color-scheme`. Use `rem` for type, flex/grid for layout, mobile-first media queries.
- No CSS framework or CSS-in-JS library without a team decision.

## Code style

- oxlint (`frontend/.oxlintrc.json`) is the authority. It enforces hooks rules, `react/exhaustive-deps`,
  `typescript/no-explicit-any`, `no-console` (only `console.error` allowed) and the `jsx-a11y` plugin
  (a11y findings are warnings — still fix them). A clean run prints nothing. Disable a rule only on one line
  with a reason:
  `// oxlint-disable-next-line <rule> -- reason`; never file-wide.
- Naming: `PascalCase` components/types, `camelCase` functions/variables, `useX` hooks, `UPPER_SNAKE` module
  constants, event handlers `handleX` and their props `onX`. Booleans read as questions (`isPlaying`, `hasFlags`).
- Small components (≈ < 150 lines); split when a component has several independent responsibilities.
- **Comments: as few as possible** (see `CLAUDE.md` → Code comments). Names and types explain *what*; comment only
  a non-obvious *why* (row flip because FITS row 0 is south, a browser/Aladin workaround, a deliberate trade-off).
  No commented-out code, no banners, no TODOs without an owner. Short `/** */` on exported functions/props only when
  units, shape or side effects aren't obvious from the name.
- No `console.log` left in committed code; `console.error` only alongside a user-visible error state.
- Text shown to users is English, concise, and uses correct units (µm, ″, °, MJD/UTC dates in ISO format).

## Tests

- No test runner is installed yet. Pure logic in `lib/` is written so it can be tested with Vitest
  (the Vite-native choice) once the team agrees to add it; then tests go next to the code as `*.test.ts`,
  with React components tested via Testing Library by behavior (roles, labels), not implementation details.
- Until then: `npm run build` + `npm run lint` + a manual check on the mock bundle and at least one prebaked target.
