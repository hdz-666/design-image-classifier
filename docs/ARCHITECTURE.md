# Architecture & decisions

This document explains **how the pieces fit together and why**, so you don't have to
reverse-engineer intent from the code or ask in a meeting. If you're about to make a design
choice and think "I wonder what Hardik would want here" — check this file first. If it's not
answered here, use your best judgement and match the existing patterns; see
[CONTRIBUTING.md](CONTRIBUTING.md) for what to do if you're genuinely blocked.

## The big picture

There are **three repositories** involved in the full "Design Matcher" feature. Only the first
one lives here.

```
┌─────────────────────────┐      ┌──────────────────────────┐      ┌─────────────────────┐
│  tally-analytics         │      │  tally-analytics-backend  │      │  design-matcher-api  │
│  (frontend, React/Vite)  │ ───► │  (existing FastAPI backend)│ ───► │  (THIS REPO)         │
│                           │      │                            │      │                      │
│  Browser-facing UI.       │      │  Thin proxy router at      │      │  Owns the catalog on │
│  Never talks to           │      │  /api/matcher/*.           │      │  disk, the embedding │
│  design-matcher-api       │      │  Checks the user's         │      │  model, the vector   │
│  directly for JSON/manage │      │  Supabase session, then    │      │  index, and search.  │
│  calls - only for the     │      │  forwards to this service  │      │                      │
│  signed photo URLs this   │      │  with an API key.          │      │  Runs on Hardik's    │
│  service returns (plain   │      │                            │      │  Windows PC (RTX     │
│  <img> tags, no auth      │      │                            │      │  4070) behind a      │
│  needed - see below).     │      │                            │      │  Cloudflare Tunnel   │
└─────────────────────────┘      └──────────────────────────┘      │  for now; deploys to │
                                                                      │  Railway later with  │
                                                                      │  no code changes.    │
                                                                      └─────────────────────┘
```

Repo locations on Hardik's machine (for reference — your checkout may differ):

- Frontend: `D:\Work\tally analytics\tally-analytics`
- Existing backend: `D:\Work\tally analytics\tally-analytics-backend`
- This repo: `D:\Work\design-image-classifier` (conceptually named `design-matcher-api`)

**This repo has no real UI.** It's a pure JSON API plus a signed image-serving endpoint. A
tiny `/test` sanity page is allowed later (Phase 7) for manual smoke-testing, nothing more.

## Why a separate service instead of adding this to the existing backend?

- The existing backend (`tally-analytics-backend`) is a lightweight `asyncpg` + FastAPI service
  with no ML dependencies. This service needs PyTorch, a GPU, and a large on-disk catalog —
  bundling that in would bloat and complicate deploys of a service that otherwise has nothing
  to do with it.
- It needs to run on Hardik's gaming PC (for the GPU) today, and on Railway (CPU-only) later,
  with zero code changes — just config. Keeping it a separate, independently deployable service
  makes that trivial.
- The existing backend becomes a **thin, dumb proxy**: it doesn't know anything about designs,
  embeddings, or the catalog. It just forwards authenticated requests and relays responses. This
  keeps the blast radius of bugs in this (newer, more experimental) service contained.

## Authentication model

**There is no role/permission system anywhere in this stack.** `tally-analytics-backend`'s
existing auth (`app/core/auth.py` in that repo) just checks "is this a valid, logged-in
Supabase user" — there's no admin/staff distinction in the whole app. Hardik explicitly decided
**not** to add one for this feature either. Don't build a roles system. Don't ask the user for
one. If you think you need one, you're over-engineering — stop and re-read this paragraph.

Given that, auth here is intentionally simple, with two layers:

1. **Server-to-server, API key.** Every `/api/v1/*` route (except the two exceptions below)
   requires an `X-API-Key` header matching the `API_KEY` env var. Only `tally-analytics-backend`
   ever sends this key — it is a server-to-server secret and must **never** reach browser code.
   See `app/auth.py` (`require_api_key`) and how it's wired as a router-level dependency in
   `app/main.py`.
2. **No JWT verification here.** We deliberately did **not** build Supabase JWT verification
   into this service, even though the original brief considered it. Because every real request
   comes through the `tally-analytics-backend` proxy (which already verified the Supabase
   session before forwarding), checking the API key here is sufficient. Do not add JWT/JWKS
   handling to this repo — it would be redundant and is explicitly out of scope.

Exceptions to "every route needs the API key":

- `GET /health` — unauthenticated, so Railway/uptime checks and the Cloudflare Tunnel's health
  probe can hit it freely. Matches the pattern in `tally-analytics-backend`.
- `GET /api/v1/photos/{token}` — unauthenticated by design. See below.

## Signed photo/thumbnail URLs (no API key in the browser)

Search results and catalog pages need to render images in `<img src="...">` tags. An `<img>`
tag can't send a custom `X-API-Key` header — and we never want the API key anywhere near the
browser anyway. Two options were on the table:

1. Stream every image byte-for-byte through `tally-analytics-backend` (which *can* attach
   headers server-side), so the browser never talks to `design-matcher-api` at all.
2. Have `design-matcher-api` issue **short-lived, signed URLs** pointing at itself, and let the
   browser load images directly from there.

We went with **(2)**. Reasoning: plain `<img>` tag loads are cross-origin-safe without any CORS
setup (CORS only gates JS reading response *bytes* via `fetch`/XHR/canvas, not simple image
display) — so there's no security downside, and it avoids doubling bandwidth/latency through the
proxy for every thumbnail on a results page. The signed token proves nothing more than "someone
with a link less than 12 hours old" — it reveals no secret and isn't tied to a user, which is an
acceptable tradeoff for catalog photos of laminate sheets (not sensitive data).

Implementation (`app/security.py`):

- `itsdangerous.URLSafeTimedSerializer`, keyed by `API_KEY` itself (no separate secret needed —
  itsdangerous signatures never leak the key they're signed with, so reusing it here is safe).
- `sign_photo_path(relative_path)` → opaque token encoding the path relative to `CATALOG_DIR`.
- `unsign_photo_token(token)` → raises a 410 if expired (`PHOTO_URL_MAX_AGE_SECONDS`, currently
  12 hours) or a 404 if tampered/garbage.
- `build_photo_url(path, catalog_root=...)` → full URL using `PUBLIC_BASE_URL`.
- Served by `app/routers/media.py`, mounted **without** the API-key dependency in `app/main.py`.

**Keep this pattern for thumbnails in Phase 3 too** — thumbnail URLs should go through the same
signing mechanism, not a different one.

## Error format

Every error response is `{"code": "...", "message": "..."}`. `message` must be short and in
plain language — the frontend shows it **directly** to non-technical shop staff (e.g. "Matcher
is offline, try again in a minute"), so don't write anything a developer would write for
themselves ("Internal Server Error", stack traces, etc.).

This is enforced centrally in `app/errors.py`:

- `AppError(code, message, status_code)` — raise this for any expected, user-facing failure
  (not found, bad input, invalid file, etc.). This is what you should reach for in new code.
- A registered handler also normalizes plain `HTTPException` and FastAPI's
  `RequestValidationError` into the same `{code, message}` shape, so even a framework-level 404
  or a bad request body comes back consistently.

Don't let a raw exception/traceback reach the client. If you add a new failure mode, raise
`AppError` with a short, specific `message`.

## Configuration philosophy

Everything is an env var, read once at startup into the `Settings` singleton in `app/config.py`
(`pydantic-settings`, reading `.env`). No hardcoded paths, URLs, hostnames, or secrets anywhere
in the code — if you catch yourself writing a literal path or URL, make it a setting instead.
`.env.example` must always be kept in sync with every field in `Settings` — if you add a setting,
add it there too, with a plain-language comment explaining what it does and why someone would
change it.

`config/product_types.json` (repo-bundled defaults: laminate, louver, acrylic, asa) can be
overridden **without a code change** by dropping a `product_types.json` file at
`<CATALOG_DIR>/config/product_types.json` — see `app/catalog/product_types.py`. This lets Hardik
edit the badge list/colors on his own machine without touching code or redeploying. The
`unspecified` entry is hardcoded in Python and always appended — it can't be removed by editing
the JSON, because the catalog scanner relies on it existing as a fallback sentinel.

## Catalog storage: filesystem now, swappable later

The catalog (companies → collections → designs → photos) lives as **plain folders and JSON
files on disk**, not in a database. See [CATALOG_FORMAT.md](CATALOG_FORMAT.md) for the exact
layout. All reads go through `app/catalog/fs.py` and `app/catalog/schema.py` — **never** read
or `open()` catalog files directly from a router or script. This matters because:

- `fs.safe_join()` is the only sanctioned way to turn user-supplied path segments (company,
  collection, design code) into a real filesystem path. It rejects path traversal (`..`, `/`,
  `\`, null bytes) and verifies the resolved path stays inside `CATALOG_DIR`. Bypassing it to
  "save a function call" is a path-traversal vulnerability waiting to happen.
- Centralizing scanning logic means Phase 3's indexer, Phase 5's manage endpoints, and the
  `catalog-check` CLI all agree on what counts as a company/collection/design. If each one
  re-implements scanning slightly differently, you get ghost results and subtle bugs.

For the **vector index** (embeddings), Hardik's explicit direction: build it as local
numpy/FAISS files for the proof-of-concept now, but structure the code so it could later move to
a database (Supabase/pgvector was mentioned as a possibility, not a commitment). Practically,
this means: **put all index read/write behind a small module (e.g. `app/index/store.py` in
Phase 3) with a narrow interface** (add vectors, search nearest, update metadata for an id,
delete an id, load, save) and have the rest of the app call only that interface. Don't let FAISS
API calls leak into router code. Swapping the backing store later should mean rewriting one
module, not hunting through the codebase.

## Product type resolution (do not change this order)

A design's product type is resolved in this exact priority order, first match wins:

1. The design's own `info.json` → `"product_type"` field (folder-layout designs only).
2. The collection's `collection.json` → `"product_type"` field.
3. The company's `company.json` → `"default_product_type"` field.
4. Otherwise: the literal string `"unspecified"`.

This is implemented in `app/catalog/schema.py::resolve_product_type`. Every place that needs a
design's product type (browse endpoints, search ranking, indexing metadata, `catalog-check`)
must call this function — never re-derive it ad hoc.

## Two design layouts, one identity

A design can be stored two ways on disk, and **both must keep working side by side forever**:

1. **Folder layout**: `<collection>/<design-code>/` containing an `old/` subfolder (pattern-only
   photos, color not trustworthy), an optional `iphone/` subfolder (true-color photos taken with
   a gray card), and an optional `info.json`.
2. **Loose-file layout**: a single image file directly inside the collection folder, named
   `<design-code>.<ext>`. Treated as a single pattern-only ("old") photo. Cannot have an
   `info.json`, cannot have iPhone photos, in this state.

A design's **unique identity is always the triple `(company, collection, design-code)`** —
never a database-generated ID, never a slug derived some other way. The same design code can
legitimately exist under different collections or companies and must never collide or merge.

**Phase 5 requirement, decided already — don't re-ask**: when a staff member uploads an iPhone
photo for a currently loose-file design, the API must *automatically* convert it to folder
layout: create `<design-code>/old/` and move the existing loose file into it unchanged, create
`<design-code>/iphone/` and put the new upload there, then remove the now-empty loose file
location. No photos may be lost in this process. The design code and its identity do not change.

## Deployment targets

Must run, with **zero code changes**, in two places — only `.env` differs:

- **Now**: Hardik's Windows PC, RTX 4070, exposed to the internet via a Cloudflare Tunnel, so
  `tally-analytics-backend` (which may itself be on Railway) can reach it.
- **Later**: Railway, CPU-only, via a Dockerfile. GPU detection must fall back to CPU
  automatically (e.g. `torch.cuda.is_available()`), never hard-fail if no GPU is present.

See [ROADMAP.md](ROADMAP.md) Phase 7 for the Dockerfile/Cloudflare Tunnel deliverables.

## What's explicitly out of scope right now

- Any role/permission system beyond the single API key (see Authentication model above).
- Stock levels / pricing data. `tally-analytics-backend`'s database has Tally-derived stock
  tables (`mst_stock_item` etc.) with no `design_code` column and no established relationship to
  this catalog. This service stays fully decoupled from that data. If the frontend later wants
  to cross-reference a design code against a stock item name, that happens client-side in the
  frontend repo — not here.
- Building the actual `/api/matcher/*` proxy router is **in scope** but lives in a different
  repository (`tally-analytics-backend`). See [ROADMAP.md](ROADMAP.md) Phase 8. Do that work on
  a separate git branch in that repo, never directly on `main`, and treat it as a distinct
  deliverable from everything else in this repo.
