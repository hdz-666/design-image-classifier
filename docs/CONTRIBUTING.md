# Contributing / dev guide

Read this before writing any code. It covers environment setup, how the existing code is
organized, the conventions to follow, and — importantly — **what to do when something is
ambiguous**, since this project is handed off without a live walkthrough.

## If you're blocked

This repo is being handed off without a verbal meeting, on purpose. That means:

1. **First, check [ARCHITECTURE.md](ARCHITECTURE.md), [CATALOG_FORMAT.md](CATALOG_FORMAT.md),
   and [ROADMAP.md](ROADMAP.md).** Most "what should this do?" questions are already answered
   in one of those three files. Re-read the relevant phase section in ROADMAP.md fully before
   assuming something's undecided — several things that look like open questions are actually
   resolved in a "decided already" callout.
2. **If it's genuinely not decided**, make the most consistent choice given the patterns already
   in the codebase, write a one-line comment explaining the assumption (`# ASSUMPTION: ...`),
   and add a line to a file called `OPEN_QUESTIONS.md` at the repo root (create it if it doesn't
   exist) describing the question and the assumption you made. Keep moving — don't block on it.
3. **Never guess on anything involving money, deleting data, or secrets.** If a decision could
   destroy catalog photos, expose the API key, or similar, stop and add it to
   `OPEN_QUESTIONS.md` instead of guessing, even if that means leaving that one piece undone.

## Environment setup

Requires Python 3.11+ (3.12/3.13/3.14 all fine) and, from Phase 3 onward, an NVIDIA GPU is
recommended but not required (CPU fallback is a hard requirement — see ARCHITECTURE.md).

```bat
REM From the repo root (PowerShell or cmd):
copy .env.example .env
REM edit .env - at minimum set API_KEY to something random

run.bat
```

`run.bat` creates `.venv` on first run, installs `requirements.txt`, and starts the server with
`--reload` on `http://localhost:8000`. It refuses to start if `.env` doesn't exist (checks
`API_KEY` is set).

To run tests instead of the server:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -v
```

Tests **do not** require a real `.env` or real catalog data — `tests/conftest.py` sets a fake
`API_KEY` and points `CATALOG_DIR` at a temporary directory it populates using
`scripts/generate_sample_catalog.py` before the app is even imported. Never make a test depend
on Hardik's real catalog data living at a specific path; always use the generated sample catalog
or a `tmp_path` fixture (see `tests/test_catalog_check.py` for examples of both patterns).

To generate a sample catalog you can click around in a browser / hit with `curl`:

```powershell
.venv\Scripts\python.exe scripts\generate_sample_catalog.py --out .\data\catalog
```

Then set `CATALOG_DIR=./data/catalog` in `.env` (already the default) and `run.bat`.

## Project layout

```
app/
  main.py              FastAPI app wiring: middleware, exception handlers, router mounting.
  config.py            Settings (pydantic-settings), reads .env. Add new env vars here.
  auth.py              require_api_key dependency.
  errors.py            AppError + exception handlers -> {code, message} responses.
  security.py          Signed photo URL signing/verification (itsdangerous).
  cli.py                `python -m app.cli <command>` entry point.
  catalog/
    fs.py              Filesystem scanning: list_companies/list_collections/list_designs,
                       safe_join (path-traversal defense), design_photos. THE source of truth
                       for "what counts as a design" - reuse this, don't reimplement.
    schema.py          Reads info.json/collection.json/company.json, resolve_product_type.
    product_types.py   Loads config/product_types.json (with catalog-dir override).
    check.py           catalog-check logic (used by the CLI).
  schemas/
    catalog.py         Pydantic response models for browse endpoints.
  routers/
    health.py          GET /health (unauthenticated).
    media.py            GET /api/v1/photos/{token} (unauthenticated, signed).
    browse.py            /api/v1/product-types, /companies, /collections, /designs/... (all
                         behind the API key).

config/
  product_types.json   Repo-bundled default product type list.

scripts/
  generate_sample_catalog.py   Synthetic catalog for tests and local dev - no real photos.

tests/
  conftest.py          Builds the fake catalog + TestClient fixtures once per test session.
  test_*.py            One file per concern - mirror this when you add new ones.

docs/
  ARCHITECTURE.md       Decisions and why. Read this first.
  CATALOG_FORMAT.md     On-disk catalog spec.
  ROADMAP.md             Remaining phases, in detail.
  CONTRIBUTING.md        This file.
```

## Conventions to follow

These match the style already in the code (and in the sibling `tally-analytics-backend` repo,
written by the same person — consistency across both matters):

- **Plain `pydantic.BaseModel` schemas**, snake_case fields, suffixed `...Schema` (see
  `app/schemas/catalog.py`). Don't introduce a different ORM/schema style.
- **`pydantic-settings` for all config**, one flat `Settings` class in `app/config.py`, a
  module-level `settings = Settings()` singleton. Don't read `os.environ` directly anywhere
  else in the app.
- **Routers are plain `APIRouter()`** with no prefix/auth baked into the router file itself —
  the prefix and the `dependencies=[Depends(require_api_key)]` are applied where the router is
  `include_router`'d in `app/main.py`. This is so it's obvious, in one place, which routes are
  public vs. API-key-gated. Keep that pattern for every new router.
- **Every expected failure raises `AppError`** (see `app/errors.py`), never a bare
  `HTTPException` with a developer-facing message, never an uncaught exception.
- **Never touch the filesystem directly from a router** — go through `app/catalog/fs.py` /
  `schema.py`. If you need a new scanning primitive, add it there, not inline in a router.
- **`fs.safe_join()` for every path built from user input.** No exceptions. This is the one
  piece of security-critical code in the repo; review it carefully before changing it, and
  never bypass it "just this once."
- **Comments**: default to none. Only write one when the *why* isn't obvious from the code
  itself (a non-obvious constraint, a workaround, a deliberately-counterintuitive choice). Don't
  write comments that restate what the line does.
- **No speculative abstraction.** If the Roadmap says "support 3 models," write code that
  supports exactly those 3 named models (even if it's a few `if`/`elif` branches), not a generic
  plugin system for hypothetical future models. Three similar lines beat a premature framework.
- **Tests**: one test file per module/router (`tests/test_<thing>.py`), using the `client`,
  `auth_headers`, and `catalog_dir` fixtures from `conftest.py`. Add fixtures to `conftest.py`
  only when multiple test files need them; otherwise build test-specific state inline (see
  `test_catalog_check.py`'s `tmp_path` + `monkeypatch` tests for a pattern that doesn't touch the
  shared sample catalog).
- **Every new env var** must be added to both `app/config.py` (the `Settings` class) and
  `.env.example` (with a plain-language comment), in the same change. If you don't do this, the
  intern after you (or Hardik) won't know it exists.

## Before you consider a phase "done"

- All new/changed behavior has tests, and `pytest` passes in full — not just your new tests, the
  whole suite (`.venv\Scripts\python.exe -m pytest -v`).
- You've actually started the server and hit the new endpoint(s) by hand at least once (curl,
  `/docs`, or a PowerShell `Invoke-WebRequest` — see earlier phases' commits for examples) —
  passing tests are not proof the feature works end to end against a real running process.
- `.env.example` is up to date.
- You've updated `docs/ROADMAP.md` to mark the phase complete and noted anything you deviated
  from or any `OPEN_QUESTIONS.md` entries you added as a result.
- You haven't broken anything in an earlier phase (rerun the full test suite — see above).

## Git

- Work on a feature branch per phase (e.g. `phase-3-indexing`), not directly on `main`.
- Commit messages: short, present-tense, explain *why* not just *what* (match the existing log —
  `git log --oneline`).
- Open a PR per phase (or ask Hardik how he wants them bundled) rather than one giant PR at the
  end — easier to review incrementally.
- **Never** commit `.env`, real catalog photos, or anything under `data/` — all already covered
  by `.gitignore`, but double-check `git status` before committing if you're ever unsure.
