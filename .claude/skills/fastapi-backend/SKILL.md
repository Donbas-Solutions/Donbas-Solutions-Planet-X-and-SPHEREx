---
name: fastapi-backend
description: Python/FastAPI conventions for this repo's backend/ (and Python in scripts/, science/). Use before writing or changing any Python here - endpoints, Pydantic models, settings, IRSA/HTTP clients, background jobs, concurrency, tests - and before committing Python changes. Covers type annotations, mypy, ruff, uv, async vs sync (no event-loop blocking), error handling, logging, comments and pytest.
---

# FastAPI backend conventions

Project facts (stack, science rules, guardrails, commands) live in `CLAUDE.md`; the API contract lives in
`docs/api.md` + `backend/app/models.py`. This skill is *how* to write the Python. If it ever conflicts with
`CLAUDE.md`, `CLAUDE.md` wins.

## Workflow

1. Read the code you are changing and its tests first; match the existing style.
2. Write or update a test next to the change (`backend/tests/`).
3. Before calling the work done or committing, all of these must pass:
   ```
   uv run --project backend ruff check --fix .      # from the repo root
   uv run --project backend ruff format .
   cd backend && uv run mypy app tests && uv run pytest -q
   ```
   Always go through `uv run` (locked versions), never a global `ruff`/`mypy`/`pip`.
4. Dependencies: `cd backend && uv add <pkg>` (`--dev` for tooling). Never `pip install`. Commit
   `pyproject.toml` + `uv.lock` together. Prefer the standard library or an existing dependency; before adding a
   new one, check who publishes it and which transitive packages it pulls into `uv.lock`.

## Type annotations

- Annotate **every** function signature: all parameters and the return type, including `-> None`, private helpers,
  test functions, fixtures and FastAPI endpoints. ruff `ANN` enforces presence, `mypy --strict` checks correctness.
- Target is Python **3.11** (`ruff.toml` `target-version`): use `X | None`, `list[str]`, `dict[str, float]`,
  `collections.abc.Iterable/Sequence/Mapping/Callable`, `typing.Self`, `Literal`, `TypedDict`, `Final`.
  Do **not** use 3.12+ syntax (`type X = ...`, `def f[T]()`), and no `typing.List/Dict/Optional/Union`.
- Every module starts with a docstring and `from __future__ import annotations` (as the existing modules do).
- Accept abstract types, return concrete ones: parameter `Sequence[float]`, return `list[float]`.
- Avoid `Any`. astropy/astroquery/pyvo/reproject/photutils are untyped (treated as `Any` in `pyproject.toml`), so
  convert their results to typed values (`float(...)`, models, dataclasses) right at the boundary.
  No bare `# type: ignore`; if needed, `# type: ignore[code]  # reason`.
- Use the `Literal` aliases (`FrameKind`, `FlagGroup`, `JobState`) instead of `str` for enumerated values.
- numpy: annotate arrays as `npt.NDArray[np.float32]` (`import numpy.typing as npt`).
- Name values with units when there is no type for it: `fov_arcmin`, `radius_deg`, `timeout_s`, `mjd`.

## FastAPI

- **Contract first.** Request/response shapes are Pydantic models in `app/models.py`, mirrored in `docs/api.md`.
  Changing either one means changing both and telling the team.
- Every endpoint declares `response_model=` and the matching return annotation - never return bare dicts.
- Validate query params with `Annotated` + `Query` constraints, not manual checks. Reuse the aliases in
  `app/api/params.py` (`Ra`, `Dec`, `Fov`, `Pm`, `RefEpoch`); the limits come from `docs/api.md`.
- Path params that become file names (`job_id`, ...) are validated (UUID or a strict `pattern`) - never build
  a path from raw user input (path traversal into `cache/`).
- Endpoints live in one `APIRouter` per area under `app/api/<area>.py` (registered in `app/api/__init__.py`);
  `main.py` is the composition root: `create_app()` (middleware, mounts, routers) and `lifespan` (shared resources). Endpoints stay thin: parse -> call a plain function in a domain
  module -> return a model. Science/processing modules must not import FastAPI.
- Shared resources (one `httpx.AsyncClient`, semaphores, job registry) are created in a `lifespan` context manager
  and reach endpoints via `Depends` / `request.app.state`, not per request and not at import time.
- Settings come only from `app/config.py` (`settings`); never read `os.environ` elsewhere.
- Pydantic v2 API only: `model_validate`, `model_dump`, `model_validate_json`, `ConfigDict`, `Field`.

## async vs sync: never block the event loop

One blocked event loop stalls **every** request on the server, including `/api/health` and job polling.

**Rule of thumb for endpoints**
- The body awaits async I/O (httpx, `asyncio.sleep`, async queues) -> `async def`.
- The body calls anything blocking (astropy, astroquery, pyvo, reproject, photutils, numpy on big arrays, FITS
  read/write, `requests`, `urllib`) -> plain `def`; FastAPI runs it in a threadpool.
- Never mix: an `async def` that calls blocking code is the bug this section exists to prevent.

**Blocking calls from async code**
- I/O-bound or short blocking work: `await anyio.to_thread.run_sync(func, arg1, arg2)`.
- CPU-heavy work (reproject, stacking, photometry over many frames): the GIL makes threads not run in parallel,
  so use a `concurrent.futures.ProcessPoolExecutor` created in `lifespan`, via
  `await loop.run_in_executor(pool, func, *args)`. Arguments and results must be picklable (arrays, paths, models).
- The anyio threadpool has 40 slots shared by all sync endpoints; don't park long jobs there. Bound concurrent
  blocking work with `anyio.CapacityLimiter` or a semaphore.
- Calling back into async code from a worker thread: `anyio.from_thread.run(coro_fn, ...)`. Never `asyncio.run()`
  inside the app, never create a second event loop.

**Inside async code, use the async equivalent**
| Don't (blocks) | Do |
|---|---|
| `time.sleep(x)` | `await asyncio.sleep(x)` |
| `requests`, `httpx.Client`, `urllib`, `astropy.utils.data.download_file` | shared `httpx.AsyncClient` |
| `open(...).read()` / `Path.read_bytes()` of large files, `astropy.io.fits.open` | `anyio.to_thread.run_sync` (or `anyio.Path` for small files) |
| `subprocess.run` | `asyncio.create_subprocess_exec` |
| `threading.Lock` held around `await` | `asyncio.Lock` |

ruff `ASYNC` catches the stdlib cases (sleep, open, subprocess, requests/urllib); it does **not** know astropy or
numpy is blocking - that part is on you.

**Concurrency and tasks**
- Run independent awaits concurrently with `asyncio.TaskGroup` (3.11), not a sequential loop of awaits.
- Wrap groups of outbound calls with `async with asyncio.timeout(seconds):`; every network call has a timeout.
- `asyncio.create_task` results must be kept in a registry (the job store) - an unreferenced task can be
  garbage-collected mid-run. Log exceptions from finished tasks; never let them disappear silently.
- Don't swallow `asyncio.CancelledError` (no `except BaseException`); clean up in `finally` and re-raise.
- Long jobs (building a sequence) never run inside the request: return `202 JobAccepted`, process in the
  background, report via `/api/jobs/{job_id}` (`JobState`, `JobProgress`). Jobs are idempotent per cache key, so a
  repeated request reuses the running/finished job.
- State shared between threads (job registry touched from worker threads) is guarded by a `threading.Lock`;
  state used only on the event loop by an `asyncio.Lock`.

**Detecting blocking**
- Dev server with asyncio debug: `PYTHONASYNCIODEBUG=1 uv run uvicorn app.main:app --reload --port 8000` (PowerShell:
  `$env:PYTHONASYNCIODEBUG=1` first). It logs `Executing <Task ...> took 0.512 seconds` for any step that blocked
  the loop > 100 ms - treat each such line as a bug.
- pytest turns `coroutine ... was never awaited` into an error (`filterwarnings` in `pyproject.toml`).

### Outbound HTTP (IRSA, SIMBAD)

- One shared `httpx.AsyncClient` with an explicit `httpx.Timeout(settings.http_timeout_s)` (>= 120 s), the
  generic User-Agent `settings.user_agent`, and an `asyncio.Semaphore(settings.max_concurrency)` (<= 8) around
  every request.
- Retries with exponential backoff + jitter on network errors / 5xx / 429 only; never retry other 4xx.
- Always have a fallback for flaky services (SIMBAD mirror, `settings.fallback_collections`).
- Stream large downloads to a temp file and rename into `cache/` when complete, so a crash never leaves a
  half-written file that looks valid.
- Never put personal data in requests. Never fetch full-frame FITS in a request path.

## Errors

- Raise `HTTPException` with a correct status and a short, user-facing `detail`: 422 for bad input (mostly
  automatic via `Query`), 404 for unknown ids/objects, 502/503/504 when IRSA/SIMBAD fails or times out,
  501 for unimplemented.
- Domain code raises its own small exception classes (e.g. `class ResolveError(Exception)`); the endpoint layer
  maps them to HTTP. Don't leak tracebacks, local paths or upstream URLs into `detail`.
- Catch specific exceptions only (ruff `BLE`). Re-raise with `raise ... from exc`. A broad catch is allowed only at a
  service boundary with a `# noqa: BLE001 - reason` and the error logged.

## Code style

- ruff is the authority (`ruff.toml` at the root); don't hand-format against it. `# noqa: CODE - reason` only, never
  a blanket `# noqa`.
- **Comments: as few as possible.** Clear names, types and small functions explain *what*; don't restate code
  in a comment. Write one only for a non-obvious *why*: a science/instrument fact, a workaround for an upstream
  bug, a deliberate trade-off. No commented-out code, no section-banner comments, no changelog-style comments.
  Public functions get a one-line docstring when the name alone is not enough (units, shape, side effects).
- `logging.getLogger(__name__)`, never `print` in `app/` (scripts may print). `logger.info("x=%s", x)`, not f-strings.
- `pathlib.Path` for paths. Text files are opened with `encoding="utf-8"`.
- Immutable data: `@dataclass(frozen=True)` or Pydantic models; no mutable default arguments.
- Name science constants once (`PIXEL_SCALE_ARCSEC = 6.2`); no repeated magic numbers.
- Datetimes are timezone-aware (`datetime.now(UTC)`); astronomical times use `astropy.time.Time` / MJD floats.

## Tests

- pytest, files `backend/tests/test_<area>.py`, functions `test_<behavior>() -> None`.
- API tests use `fastapi.testclient.TestClient`. `tests/conftest.py` points the cache at a temp dir before `app`
  is imported - keep that ordering.
- Unit tests never hit the network. Mock outbound calls (`monkeypatch`, or `httpx.MockTransport` on the shared
  client). Tests that need live IRSA/SIMBAD get `@pytest.mark.network`; they are deselected by default and run with
  `uv run pytest -m network`.
- One assertion per fact (ruff `PT018`), `pytest.mark.parametrize` for input tables.
- FITS fixtures: small, in `backend/tests/fixtures/`, EPSF extension stripped.
- Test behavior and the contract (`test_contract.py`), not implementation details. Numeric results:
  `pytest.approx` / `numpy.testing.assert_allclose` with an explicit tolerance.
