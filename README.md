# design-matcher-api

A photo-matching API for a laminate/louver/acrylic/ASA sheet catalog. A shop assistant takes a
photo of a design on a customer's wall or sample board; this service finds the **3 closest
matching designs** in a ~4,000-design catalog spanning multiple companies, each with multiple
collections, each with multiple designs. It also exposes catalog browsing and management
endpoints so a separate frontend can build a search page and a staff admin page against it.

This repo is a **standalone backend service only**. There is no real UI here (a tiny `/test`
sanity page is planned for later, nothing more) — the actual frontend lives in a separate
repository and talks to this service **through** another existing backend, never directly. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture of how the three repositories
fit together and why.

## Status

| Phase | What | Status |
| --- | --- | --- |
| 1 | Skeleton, config, API-key auth, `/health` | ✅ Done |
| 2 | Catalog scanning (filesystem), browse endpoints, `catalog-check` CLI | ✅ Done |
| 3 | Embedding/indexing pipeline, thumbnails, `reindex` CLI | ⬜ Not started |
| 4 | `/search` endpoint | ⬜ Not started |
| 5 | Manage endpoints (create/edit/upload/move), background reindex jobs | ⬜ Not started |
| 6 | Accuracy test script, model comparison, expanded API tests | ⬜ Not started |
| 7 | API docs, OpenAPI/TS types, frontend integration brief, Dockerfile, deploy docs | ⬜ Not started |
| 8 | Proxy router in the `tally-analytics-backend` repo | ⬜ Not started |

**If you're picking this up next**, full specs for every remaining phase — detailed enough to
build without a meeting — are in [docs/ROADMAP.md](docs/ROADMAP.md). Read that before writing
any code. See also [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for dev setup, conventions, and
what to do if something's genuinely ambiguous.

## Documentation map

| Doc | What's in it |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the 3 repos fit together, and **why** every non-obvious decision was made (auth model, signed image URLs, error format, config philosophy, storage approach). Read this first. |
| [docs/CATALOG_FORMAT.md](docs/CATALOG_FORMAT.md) | The exact on-disk catalog layout, every JSON metadata file's schema, and the product-type resolution order, with a worked example. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phases 3–8, specced in full — what to build, exact endpoint contracts, acceptance criteria. |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Dev environment setup, project layout tour, coding conventions, testing patterns, what to do when blocked. |

## Quickstart

Requires Python 3.11+.

```powershell
copy .env.example .env
# edit .env - at minimum, set API_KEY to any random string

run.bat
```

`run.bat` creates a virtual environment on first run, installs dependencies, and starts the
server with auto-reload on `http://localhost:8000`. Open `http://localhost:8000/docs` for the
interactive (auto-generated) API docs.

There's no real catalog data in this repo (and shouldn't ever be — see `.gitignore`). To get
something to look at locally:

```powershell
.venv\Scripts\python.exe scripts\generate_sample_catalog.py --out .\data\catalog
```

This writes a small synthetic catalog (2 companies, 4 collections, 9 designs, mixing both
design layouts and every metadata combination) to `./data/catalog`, which is `CATALOG_DIR`'s
default. Then hit, for example:

```
GET http://localhost:8000/api/v1/companies
Header: X-API-Key: <whatever you put in .env>
```

### Running tests

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -v
```

Tests build their own temporary synthetic catalog automatically (see `tests/conftest.py`) — you
don't need `.env` or real catalog data to run them.

### Checking catalog health

```powershell
.venv\Scripts\python.exe -m app.cli catalog-check
```

Scans `CATALOG_DIR` and reports problems: empty folders, designs with no photos, designs
missing iPhone (color) photos, duplicate photos (by content, even across collections),
duplicate design codes, unreadable files, stray files at the wrong folder depth, and designs or
collections with no resolvable product type. Exit code `1` if anything was found, `0` if clean —
safe to use in a script or CI step.

## Configuration

Every setting is an environment variable, read from `.env` (see `.env.example` for the
canonical, documented list — keep both files in sync whenever you add a setting).

| Variable | Default | What it's for |
| --- | --- | --- |
| `API_KEY` | *(required)* | Server-to-server secret. Every `/api/v1/*` route except signed photo URLs requires this as the `X-API-Key` header. Never put it in frontend/browser code. |
| `ALLOWED_ORIGINS` | *(empty)* | Comma-separated origins allowed to call this API directly with JS. Mostly relevant for the future `/test` page — normal traffic is proxied, and plain `<img>` loads of signed URLs don't need CORS at all. |
| `CATALOG_DIR` | `./data/catalog` | Where the company/collection/design folders and JSON metadata live. |
| `INDEX_DIR` | `./data/index` | Where the generated vector index lives (Phase 3+). |
| `THUMBS_DIR` | `./data/thumbs` | Where generated design thumbnails live (Phase 3+). |
| `MODEL_NAME` | `dinov2-small` | Embedding model. One of `clip-vit-b32`, `dinov2-small`, `dinov2-base` (Phase 3+). |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | The URL this service is reachable at from the outside (your Cloudflare Tunnel hostname, or the Railway URL in production) — used to build signed photo/thumbnail URLs returned in API responses. |

## Current API (Phases 1–2)

Full endpoint-by-endpoint documentation with examples arrives in Phase 7 (`docs/API.md`) — this
is a quick reference for what already exists. Interactive docs are always available live at
`/docs` while the server is running.

All routes below are under `/api/v1` and require the `X-API-Key` header, **except** `GET
/health` and `GET /api/v1/photos/{token}`, which are intentionally public (see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#signed-photothumbnail-urls-no-api-key-in-the-browser)
for why).

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/health` | Unauthenticated health check. |
| `GET` | `/api/v1/product-types` | List configured product types (+ the always-present `unspecified`). |
| `GET` | `/api/v1/companies` | List companies with design counts, per-product-type counts, color-verified counts. |
| `GET` | `/api/v1/companies/{company}/collections` | Same counts, scoped to one company's collections. |
| `GET` | `/api/v1/companies/{company}/collections/{collection}/designs` | Paginated design list. Query params: `search`, `product_type` (repeatable), `needs_color_photo`, `needs_product_type`, `page`, `page_size`. |
| `GET` | `/api/v1/designs/{company}/{collection}/{code}` | Full design detail, including signed URLs for every photo. |
| `GET` | `/api/v1/photos/{token}` | Serves an actual photo file given a signed token (public, time-limited, obtained from the other endpoints' responses). |

Every error response is `{"code": "...", "message": "..."}`, with `message` written to be shown
directly to non-technical staff in the frontend.

## Project layout

```
app/                   The FastAPI application. See docs/CONTRIBUTING.md for a module-by-module tour.
config/product_types.json   Repo-bundled default product type list (overridable per-catalog).
scripts/generate_sample_catalog.py   Synthetic catalog generator, used by tests and local dev.
tests/                 pytest suite - builds its own synthetic catalog, no real data needed.
docs/                  Everything described in the table above.
data/                  Local catalog/index/thumbnail storage (gitignored, not committed).
run.bat                One-command local dev: creates venv, installs deps, starts the server.
.env.example           Canonical list of every environment variable, documented.
```

## License

MIT — see [LICENSE](LICENSE).
