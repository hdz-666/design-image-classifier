# Roadmap — Phases 3 through 8

Phases 1 (skeleton/config/auth) and 2 (catalog scanning + browse endpoints) are **done** — see
`git log`. This document specs out everything remaining in enough detail to build without a
live walkthrough. Read [ARCHITECTURE.md](ARCHITECTURE.md) and
[CATALOG_FORMAT.md](CATALOG_FORMAT.md) first; this doc assumes you already know the decisions
made there and won't repeat the reasoning, only the "what."

**Work through the phases in order.** Each depends on the previous one's deliverables.

## Decisions already made — do not re-ask about these

(Full reasoning in ARCHITECTURE.md. Listed here as a flat checklist so you can quickly confirm
you're not about to re-litigate something.)

- ✅ No role/permission system. API key only. (ARCHITECTURE.md § Authentication model)
- ✅ Thumbnails and photos are served via signed, time-limited URLs from this service directly,
  not proxied byte-for-byte through `tally-analytics-backend`. (§ Signed photo/thumbnail URLs)
- ✅ Every error is `{code, message}`, short and human-readable. (§ Error format)
- ✅ The vector index is local numpy/FAISS files for now, behind an abstraction so it could move
  to a database later — but don't build that migration now, just don't block it. (§ Catalog
  storage)
- ✅ This service never touches Tally stock/price data. Fully decoupled. (§ What's explicitly
  out of scope)
- ✅ Building the `tally-analytics-backend` proxy router **is** in scope (Phase 8 below), in that
  separate repo, on a separate branch.
- ✅ Product type resolution order is fixed: `info.json` → `collection.json` → `company.json` →
  `"unspecified"`. Never change this order.
- ✅ Loose-file → folder-layout conversion on iPhone photo upload is required and must never
  lose data. (CATALOG_FORMAT.md § Loose-file layout)

---

## Phase 3 — Indexing

**Goal**: build the embedding pipeline and the on-disk vector index, plus thumbnails, plus the
CLI to build/rebuild it. No search endpoint yet (that's Phase 4) — this phase is "build the
index," Phase 4 is "query it."

### New dependencies

Add to `requirements.txt`: `torch` (CPU build by default; `run.bat` installs the CUDA build
locally — see Phase 7 for the exact `run.bat` update), `torchvision`, `numpy`, `faiss-cpu` (CPU
FAISS works fine even when the model inference runs on GPU — only the embedding step needs the
GPU, not the vector search itself, which is tiny at this scale), `pillow-heif` (register it with
Pillow at startup so `.heic`/`.heif` files can actually be opened, not just pattern-matched by
extension), `opencv-python-headless` (for white-balance / gray-card detection / texture
flagging — headless because this is a server with no display).

One of, depending on what's easiest to get working for all three required models with
consistent code: `open_clip_torch` (for CLIP ViT-B/32) and `transformers` (for DINOv2-small /
DINOv2-base, via `facebook/dinov2-small` and `facebook/dinov2-base` on Hugging Face). Pick
whichever lets you implement all three behind one clean interface with the least special-casing;
document which you picked and why in a comment at the top of the embedder module.

### Module layout (suggested — adjust if you find a cleaner split, but keep the index storage
behind one narrow interface as ARCHITECTURE.md requires)

```
app/index/
  __init__.py
  embedder.py      Loads one of the 3 supported models, embeds a PIL image -> vector. Picks
                   GPU if available else CPU (torch.cuda.is_available()). Converts to grayscale
                   before embedding (see below).
  store.py         The ONE place that talks to FAISS/numpy files. add(), search(), update_meta(),
                   delete(), load(), save(). Nothing outside this file imports faiss directly.
  color.py         White-balance (gray card detection, gray-world fallback), LAB color
                   signature + small LAB histogram, color distance function.
  texture.py       Plain/solid-color detection (flag designs search should rank mostly by color).
  thumbnails.py    Generates ~400px JPEG thumbnails into THUMBS_DIR, mirroring
                   <company>/<collection>/ structure.
  build.py         Orchestrates: walk the catalog (via app.catalog.fs), decide what's new/
                   changed, embed, update the store, generate thumbnails, report progress.
```

### Embedding pipeline, per photo

1. Open the image (Pillow, with `pillow-heif` registered for HEIC/HEIF).
2. Convert to grayscale **before** embedding — pattern matching must ignore color entirely at
   the embedding stage. (Color is handled entirely separately, see below.)
3. Compute **1 full-image embedding** plus **3 random crops at different scales** (e.g. roughly
   50%, 70%, 90% of the image, random position) — 4 embeddings stored per photo total. The
   rationale: a user's query photo might be zoomed in/out or slightly cropped relative to the
   catalog photo; storing multiple scales improves robustness.
4. **Only for `iphone/` photos** (never `old/`, never loose-file photos — those aren't
   color-trustworthy): white-balance the image, then compute a color signature. See "Color
   handling" below.

### Color handling (iPhone photos only)

1. **Gray card detection**: look for a gray reference card in the frame (the brief assumes
   photos are taken *with* a gray card in frame specifically so this is possible). A reasonable
   approach: look for a roughly-neutral, roughly-uniform rectangular region (low saturation, mid
   brightness) — exact algorithm is your call, but it must have a **fallback**.
2. **Fallback: gray-world assumption** — if no gray card is confidently found, white-balance by
   assuming the average color of the whole image should be neutral gray (standard gray-world
   algorithm). Every photo gets *some* white-balance; never skip it.
3. After white-balancing, compute and store: **mean LAB value** (3 numbers) and a **small LAB
   histogram** (your call on bin count — something like 8 bins per channel is a reasonable
   starting point, not a hard requirement). This is the "color signature" referenced everywhere
   else in this doc and in search re-ranking (Phase 4).

### Plain/solid-color detection

Many acrylic and ASA sheet designs are nearly textureless. Flag these so search can lean on
color instead of pattern for them (actual re-ranking logic is Phase 4; this phase just computes
and stores the flag). A reasonable signal: low edge density / low local variance across the
image (e.g. Laplacian variance, or a simple Sobel-based edge-density measure via OpenCV) below
some threshold you tune empirically against a few real plain vs. patterned photos. Store this as
a boolean per design (or per photo — your call, but it should end up as a single
`is_plain: bool` on the design's metadata, since re-ranking operates per design).

### The index store

Two files per index, both in `INDEX_DIR`:

1. A vector file (FAISS index, or a plain `.npy` if you'd rather start simpler and swap to FAISS
   once correctness is proven — either is fine as long as it's hidden behind `store.py`).
2. A metadata file (JSON or a small SQLite file — your call) with one row per **embedding**
   (remember: up to 4 per photo — full + 3 crops), containing at minimum: `company`,
   `collection`, `design_code`, `product_type` (the *resolved* value, from
   `schema.resolve_product_type` — never re-derive it differently here), `photo_path` (relative
   to `CATALOG_DIR`), `photo_type` (`"old"` or `"iphone"`), `is_plain`, and (for `iphone` photos)
   the color signature.

Record **which model built the index** (e.g. a small `index_meta.json` alongside the vectors,
containing `{"model_name": "dinov2-small", "built_at": "...", "embedding_dim": ...}`). At
search time (Phase 4) and at startup, **refuse to search** if `MODEL_NAME` in the current config
doesn't match what's recorded — raise a clear `AppError` telling the operator to reindex, don't
silently produce garbage results from mismatched vector spaces.

### Incremental indexing

Only re-process files that are new or changed since the last index build. Use file mtime and/or
size (and optionally a content hash if you want to be extra safe against touched-but-unchanged
files) stored per photo in the metadata, compared against the current filesystem state. **A
`product_type` or `info.json` change must update metadata without re-embedding** — i.e., if you
detect that only the resolved `product_type` differs for an already-indexed photo (the photo
file itself is unchanged), just patch that metadata field via `store.py`'s `update_meta()`, don't
re-run the model on it. This is explicitly called out in the original brief as a requirement,
not a nice-to-have — a staff member bulk-setting product types (Phase 5) on thousands of designs
must be fast and must not trigger a full re-embed.

### Thumbnails

~400px (long edge) JPEG, one per design (pick a representative photo — prefer an `iphone/` photo
if one exists, else the first `old/` photo, else the loose file), saved to
`THUMBS_DIR/<company>/<collection>/<design-code>.jpg`. Regenerate when the source photo it was
built from changes or disappears; don't regenerate on every reindex if the source is unchanged.

Expose thumbnail URLs the **same signed-URL way** photos already are (ARCHITECTURE.md) — don't
invent a second mechanism. You'll likely want to add a second signed route or reuse
`/api/v1/photos/{token}` by pointing the token at a path under `THUMBS_DIR` instead of
`CATALOG_DIR` — pick whichever keeps `app/security.py`/`app/routers/media.py` simplest, just
keep it consistent (one signing mechanism, one verification function).

### CLI

Extend `app/cli.py` with a `reindex` subcommand:

```
python -m app.cli reindex [--company X] [--collection Y] [--design Z]
```

- No flags → reindex everything.
- `--company X` → only that company.
- `--company X --collection Y` → only that collection (requires `--company` too).
- `--company X --collection Y --design Z` → only that one design.
- Print progress as it goes (even just "X / Y photos processed" is enough for a CLI). This
  synchronous CLI command is distinct from the **background job** version Phase 5 builds for the
  API (`POST /reindex`) — the CLI can just run inline and block until done.

### Tests

Model loading/embedding is slow and shouldn't run in the main test suite on every `pytest`
invocation (an intern's laptop without a GPU would make the whole suite painfully slow). Pattern
to follow:

- Tests for `color.py`, `texture.py`, `fs`-adjacent logic, and the index store's
  add/search/update/delete *interface* (using small synthetic vectors, not real model output)
  should run in the normal suite — fast, no model loading required.
- Tests that need a real loaded model (actually embedding a real image end-to-end) should be
  marked so they can be skipped by default, e.g. `@pytest.mark.slow`, with a `pytest.ini` marker
  registered and a short note in `CONTRIBUTING.md` on how to run them (`pytest -m slow`). Don't
  make the default `pytest` run download model weights.

### Acceptance criteria

- `python -m app.cli reindex` runs against `scripts/generate_sample_catalog.py`'s output without
  crashing, on CPU (verify this explicitly — don't assume GPU-only works).
- Running it twice in a row the second time does no re-embedding (verify via a log line/counter,
  or by timing — second run should be dramatically faster).
- Changing an `info.json`'s `product_type` and rerunning updates the index's metadata for that
  design without re-embedding its photos.
- Thumbnails exist under `THUMBS_DIR` after indexing and are servable via a signed URL.
- Switching `MODEL_NAME` and trying to search (even a minimal manual check, since full search is
  Phase 4) against an index built with a different model produces a clear, human-readable error,
  not a crash or silently wrong results.

---

## Phase 4 — Search

**Goal**: `POST /search` — the actual "upload a photo, get 3 matches" endpoint.

### Endpoint

```
POST /api/v1/search
```

- `multipart/form-data`: an image file field, plus optional repeated/array fields for filters:
  `product_type` (one or more), `company` (one or more), `collection` (one or more — scoped to
  the given companies; your call on exact param shape, but keep it consistent with how
  `app/routers/browse.py`'s `product_type: list[str] | None = Query(...)` pattern already
  handles repeated query params for filters there).
- Default (no filters) searches everything.
- Max upload size: **10 MB**. Reject anything larger with a clear `AppError` (413 or 400, your
  call — be consistent with how other validation errors are reported) before doing any
  processing.
- Reject non-image content (check actual content, not just the filename extension — e.g. try to
  open it with Pillow and catch the failure cleanly).
- **Basic rate limiting** — this doesn't need to be sophisticated (no Redis, no distributed
  limiter required at this scale/deployment). A simple in-memory token bucket or fixed-window
  counter keyed by caller (API key is the same for every caller right now, so IP address is the
  more useful key) is enough. Pick a limit that's generous for normal staff use but stops a
  runaway script (e.g. something like 30 requests/minute per IP as a starting point — tune as
  you see fit, it's not load-bearing precision).

### Search algorithm

1. Normalize the uploaded photo the same way catalog photos are normalized for color: gray-world
   white balance (no gray-card detection needed here — a casual phone photo from a shop floor
   won't have one in frame; gray-world is the whole story for the query image).
2. Embed it with the **same model** that built the current index (reuse `app/index/embedder.py`
   from Phase 3 — same grayscale-before-embedding treatment, same crop strategy or just the full
   image, your call on whether crops matter for the *query* side).
3. k-NN search the vector store (`app/index/store.py`) for nearest pattern embeddings, applying
   any company/collection/product_type filters as a post-filter (or pre-filter if your store
   supports it — either is fine at this scale).
4. **Group hits by `(company, collection, design_code)`** — a design may have matched via
   several of its own embeddings (full + 3 crops, multiple photos); collapse to one entry per
   design using its best (closest) score.
5. Take the **top 15 designs** by pattern similarity.
6. **Re-rank by color distance, but only for designs that have at least one `iphone/` photo**
   (i.e. `is color-verified`). Designs without a color-verified photo keep their pattern-only
   ranking position. Use the color signature computed in Phase 3 (mean LAB + histogram) and the
   query photo's own white-balanced color, with whatever distance function you implemented in
   `app/index/color.py`.
7. Return the **top 3** (always), and optionally up to **10 more** under a secondary field, so
   the frontend can offer a "show more" affordance.

### Response shape

Per design: `company`, `collection`, `design_code`, `name` (from `info.json`, nullable),
`product_type` (resolved), `similarity_score` (number — your call on exact scale, document it),
`thumbnail_url` (signed, from Phase 3), `color_status`: `"verified"` (has iphone photos, color
distance was used in ranking) or `"approximate"` (pattern-only match, no color-verified photo
exists for this design).

If the same-looking design genuinely exists under multiple companies/collections/product types,
return **each as a separate result** with its own full path — never silently merge or dedupe
across different `(company, collection, design_code)` triples, even if they look identical to
the model. This was explicit in the original brief and is also just... correct, given how
`design_code` collisions are allowed to exist legitimately across collections.

### Performance targets

Under 1 second on GPU, "a few seconds" on CPU, for the full `/search` request (embedding +
k-NN + re-ranking). If you're well outside this on your dev machine, profile before optimizing
blindly — likely culprits are redundant file I/O per candidate (don't re-read `info.json`/
`collection.json` from disk inside the hot loop if you can serve those fields from the index
metadata instead — see the Phase 2 perf note in that phase's summary about browse-endpoint
counts; the same principle applies here, probably more so).

### Tests

- A search with no filters returns up to 3 results from the sample catalog.
- Filters (product_type/company/collection) actually narrow results.
- Oversized upload rejected cleanly.
- Non-image upload rejected cleanly.
- A query image embedded from one design's own photo (e.g. feed it one of
  `scripts/generate_sample_catalog.py`'s own generated images back in) finds that same design in
  the top 3 — this is your basic sanity check that the whole pipeline is wired correctly
  end-to-end, independent of the more rigorous accuracy testing in Phase 6.
- Same-design-code-in-two-collections doesn't collide (reuse the fixture pattern from Phase 2's
  `test_design_code_does_not_collide_across_collections`, extended to search results).

---

## Phase 5 — Manage endpoints & reindex jobs

**Goal**: everything a staff member needs to maintain the catalog through the frontend, plus
wrapping Phase 3's synchronous reindex as an async background job the API can expose.

### Manage endpoints (all under `/api/v1`, all behind the same `require_api_key` dependency —
no separate role check, see Decisions Already Made)

```
POST   /companies                                 create (makes the folder, writes company.json if fields given)
POST   /companies/{company}/collections           create (makes the folder, writes collection.json if fields given)
PATCH  /designs/{company}/{collection}/{code}     edit name/product_type/category/finish/thickness/size/notes -> writes info.json
PATCH  /collections/{company}/{collection}        edit display_name/product_type/year/notes -> writes collection.json
POST   /designs/{company}/{collection}/bulk-type   body: {design_codes: [...], product_type: "..."} -> writes info.json for each
POST   /designs/{company}/{collection}/{code}/photos         multipart upload, field indicating old vs iphone
DELETE /designs/{company}/{collection}/{code}/photos/{photo_id}   photo_id is the "old/filename.jpg" style id from Phase 2's design-detail response
POST   /designs/{company}/{collection}/{code}/move            body: {to_collection: "..."} - moves the whole design folder/file
```

Every one of these must:

- Use `fs.safe_join()` for every path it touches — these endpoints write to disk based on
  user-supplied names, which is exactly the path-traversal surface `safe_join` exists for.
- **Sanitize** any newly-created folder name (company/collection) derived from a display name —
  e.g. if someone creates a company via a `display_name` of `"Acme & Sons / Co."`, the folder
  name on disk must be a safe slug, not that literal string. Store the chosen folder name as the
  canonical id; `display_name` in `company.json` can keep the original. Define and document
  your slugification rule (lowercase, spaces→hyphens, strip anything not alphanumeric/hyphen is
  a reasonable default) in a code comment where you implement it.
- Return the same `{code, message}` error shape for failures (duplicate name, invalid input,
  not found, etc.) as every other endpoint.
- **Update the index incrementally where relevant**, not require a full reindex: a product-type
  edit should patch metadata only (Phase 3's `store.update_meta`); a photo upload/delete/move
  should trigger indexing of just that affected design (small, synchronous, or kick off a
  single-design background job — your call, but don't make a tiny edit block on a full-catalog
  reindex).

### Photo upload → loose-to-folder conversion (critical — covered in detail in
CATALOG_FORMAT.md and ARCHITECTURE.md; restated here as the implementation checklist)

When `POST .../{code}/photos` receives an `iphone` photo for a design that currently exists as a
**loose file**:

1. Create `<collection>/<code>/old/` and move the existing loose file into it, keeping its
   original filename.
2. Create `<collection>/<code>/iphone/` and save the new upload there.
3. Remove the now-empty loose-file location (there's nothing left to remove beyond the file
   itself, which was already moved — just confirm no orphan is left behind).
4. The design's identity (`company`, `collection`, `code`) is unchanged throughout.
5. If anything fails partway, don't leave the catalog in a half-converted, data-losing state —
   either make the move+write atomic-ish (do the filesystem operations in an order where a
   failure midway still leaves the original photo recoverable; e.g. copy before delete, not move
   as delete-then-create) or roll back cleanly on error.

### Reindex as a background job

```
POST   /reindex              body: {scope: "all" | "company" | "collection" | "design", ...identifiers}
                              -> {job_id: "..."}
GET    /reindex/{job_id}     -> {status: "pending"|"running"|"done"|"failed", progress: {...}, errors: [...]}
```

- **Only one job runs at a time** — if a job is already running and a new `POST /reindex` comes
  in, reject it with a clear message (`AppError`, something like "A reindex is already running,
  try again once it finishes") rather than queueing or running concurrently. A simple
  module-level flag/lock is sufficient; no task queue (Celery/RQ/etc.) needed at this scale and
  single-instance deployment.
- Must **never block the request that starts it** — kick it off as a background task
  (`BackgroundTasks` from FastAPI, or a simple thread/asyncio task — your call) and return the
  `job_id` immediately.
- Progress reporting granularity is your call — even "N of M designs processed" is enough; the
  frontend brief (Phase 7) will describe a simple progress bar against this.
- Job records can live in memory (a module-level dict keyed by job_id) — they don't need to
  survive a process restart for this use case.

### Tests

- Each manage endpoint: happy path, and at least one failure path (bad input, not found, name
  collision as applicable).
- Loose-to-folder conversion: upload an iphone photo for a loose-file design (use the sample
  catalog's `AC-102` or similar), then assert the design is now `layout: "folder"`, has both an
  `old/` entry with the original content intact and an `iphone/` entry with the new upload, and
  that a `GET` for that design still returns the same `company/collection/code`.
  Path-traversal rejected on every new endpoint that takes company/collection/code in the path
  or body (extend the pattern from Phase 2's `test_safe_join_rejects_traversal`).
- Reindex job: start one, poll until done, assert progress moved from 0 toward completion; start
  a second one while the first is (artificially, if needed) still "running" and assert it's
  rejected.

---

## Phase 6 — Tests, accuracy script, model comparison

**Goal**: prove the matcher actually works well, not just that the API doesn't crash.

### Accuracy test script

A standalone script (`scripts/test_accuracy.py` or similar — your call on exact name/location,
but put it under `scripts/` next to the catalog generator):

1. Sample **30 designs**, spread across different companies, collections, **and** product
   types (not just 30 random ones — deliberately stratify the sample so every product type and
   several companies/collections are represented; if the real catalog is small in some
   dimension, get as close as reasonably possible and note the gap).
2. For each sampled design, take one of its real photos and generate **distorted variants**:
   brightness shift, color shift, a crop, and a rotation (at minimum one of each per design;
   more variants per distortion type is fine and probably better for a meaningful sample size).
3. Run each distorted variant through `/search` (or call the search pipeline directly in-process
   if that's faster to script against — your call) and check whether the correct design appears
   in the top-1 and top-3 results.
4. Report:
   - Overall top-1 and top-3 accuracy.
   - Split by **plain vs. patterned** designs (using Phase 3's `is_plain` flag).
   - Split by **product type**.
   - Accuracy **with filters applied** (i.e. confirm that scoping a search to the correct
     company/collection/product_type doesn't hurt — and ideally helps — accuracy, since a
     correctly-filtered search has a smaller, easier search space).

This needs **real catalog data** to be meaningful — Hardik will run this against his actual ~4k
designs once it exists; it can and should still be validated to run without crashing against the
synthetic sample catalog during development, but don't tune thresholds/parameters against the
synthetic data and call it done.

### Model comparison mode

Same test, run three times — once per supported model (`clip-vit-b32`, `dinov2-small`,
`dinov2-base`) — each needing its own index built first (reuse Phase 3's CLI). Print a table:

```
model          top-1 acc   top-3 acc   index size   avg search time
clip-vit-b32   ...         ...         ...          ...
dinov2-small   ...         ...         ...          ...
dinov2-base    ...         ...         ...          ...
```

A flag on the same script (e.g. `--compare-models`) is a reasonable way to expose this, rather
than a wholly separate script — your call.

### API tests (extending Phase 2/4/5's suite, not a separate effort)

By the end of this phase the full test suite should additionally cover, if it doesn't already
from earlier phases: auth required on every protected route (should already be true by
construction, but add a sweep test that checks every registered route under `/api/v1` except
the known-public ones actually requires the key — this catches someone accidentally forgetting
the dependency on a new router), roles/permissions is a non-issue (nothing to test, by design),
bad file rejected, every filter combination on `/search` and the browse endpoints, path
traversal blocked everywhere a path is user-supplied, same design code in two collections never
collides (search and browse both), and reindex jobs report progress correctly and reject
concurrent runs.

---

## Phase 7 — Docs, frontend integration kit, deployment extras

**Goal**: everything needed to (a) hand this API to the frontend repo's own Claude Code session
without a meeting, same as this repo was handed to you, and (b) actually deploy it.

### `docs/API.md`

Plain-language description of every endpoint: method, path, what it's for, auth requirement,
request shape (with a realistic example), response shape (with a realistic example), and every
possible error it can return with its `code` and when it happens. Written for someone building a
frontend against it, not for someone reading the source.

### OpenAPI export + generated TS types

- Export the live OpenAPI schema to `docs/openapi.json` (FastAPI generates this automatically at
  `/openapi.json` while the server is running — just save that response to a file; add a tiny
  script or a documented manual step, your call).
- Generate `docs/types.ts` from it (e.g. via `openapi-typescript`, a Node devDependency you'd run
  once and commit the output — document the exact command in a comment at the top of the
  generated file or in API.md, so it can be regenerated later when the API changes).

### `docs/FRONTEND_BRIEF.md`

A **ready-to-paste prompt** for a Claude Code session working in the separate `tally-analytics`
frontend repo, describing exactly what to build against this API — written the same way this
`ROADMAP.md` is written (self-contained, no assumed prior conversation). It must describe:

- **Search page**: big "Upload / Take photo" button (camera on phones via a file input with
  `capture="environment"` or similar), preview before submitting, product-type filter chips
  (multi-select, default "All types" — pull the list from `GET /api/matcher/product-types`
  through the proxy, not hardcoded), company dropdown (default "All companies"), collection
  dropdown once a company is picked, result cards (thumbnail, colored product-type badge,
  breadcrumb "Company > Collection", design code, name, color-verified/approximate label), tap a
  card for a detail view (all photos + info), friendly error messages (e.g. "Matcher is offline,
  try again in a minute" — map from the `{code, message}` responses this API already returns;
  the `message` field is specifically written to be shown as-is).
- **Catalog page** (staff): Companies → Collections → Designs drill-down with a breadcrumb,
  counts (including per-product-type and color-verified counts, already returned by
  `/companies` and `/collections`), type badges everywhere, a searchable/filterable design grid
  ("needs color photo" / "needs product type" filters, already supported server-side), an edit
  form per design, photo upload (triggers the auto-conversion described in Phase 5 — the
  frontend doesn't need to know or care about loose-vs-folder layout, just "upload a photo"),
  bulk product-type setting across selected designs, create-company/create-collection forms,
  move-design-to-another-collection, and a reindex button with a progress indicator (polling
  `GET /api/matcher/reindex/{job_id}`).
- Explicitly note: **the frontend calls `tally-analytics-backend`'s `/api/matcher/*` proxy, never
  this service directly**, except for the signed photo/thumbnail URLs returned inside those
  responses, which it loads with plain `<img>` tags.
- Phone-first layout, no technical jargon anywhere in the UI (this is for shop staff).

### Dockerfile + docker-compose.yml

CPU-based Dockerfile (Railway target). Note clearly in a comment that the GPU path (local
Windows + Cloudflare Tunnel) doesn't use this Dockerfile at all — it runs via `run.bat` and a
real CUDA-enabled `torch` install. `docker-compose.yml` for convenience running it locally in a
container if someone wants to (optional nicety, not the primary local workflow, which stays
`run.bat`).

### `run.bat` update

Phase 1's `run.bat` installs plain `requirements.txt`, which by Phase 3 includes a CPU-default
`torch`. Update `run.bat` to install the **CUDA build of PyTorch** specifically (the exact
`pip install torch --index-url https://download.pytorch.org/whl/cu1xx` command depends on the
CUDA version on Hardik's machine at the time — check `nvidia-smi` output for the driver's
supported CUDA version and pick a matching prebuilt wheel index URL from pytorch.org, don't
guess a version number) before falling through to the rest of `requirements.txt`.

### Cloudflare Tunnel — document the exact steps

In the main `README.md` (not here) — this is referenced from there. Cover: installing
`cloudflared`, authenticating it to Hardik's Cloudflare account/domain, creating a named tunnel,
configuring it to point at `localhost:8000` (or whatever port `run.bat` uses), setting
`PUBLIC_BASE_URL` to the resulting tunnel hostname, and starting the tunnel alongside the API
(two processes, both need to be running). Write it as literal copy-pasteable commands, not a
description of what to do.

### README rewrite (plain language, for Hardik day-to-day, not for a developer)

By the end of this phase, `README.md`'s "how do I actually use this day to day" section should
cover, in plain language with no jargon: how to add a new company/collection/design, how to add
iPhone photos to an existing design, how to set a product type, how to run a reindex (CLI and via
the API once the frontend exists), how to start the service, how to start the tunnel, and what
each env var in `.env.example` does. This is for Hardik, not a future engineer — write it like a
checklist/FAQ, not prose.

---

## Phase 8 — `tally-analytics-backend` proxy router (separate repo!)

**Goal**: wire the real backend up so the frontend can actually reach this service.

**This work happens in `tally-analytics-backend`** (at `D:\Work\tally analytics\
tally-analytics-backend` on Hardik's machine — confirm the path still matches on whatever
machine you're doing this on), not in this repo. Everything above this line is about
`design-matcher-api`; everything in this section is about a different, already-existing,
already-deployed FastAPI service. Treat it with extra care — it's not a greenfield project.

### Before touching anything

- `git status` in that repo first. If there's anything uncommitted that looks like someone's
  in-progress work, stop and ask rather than touching it.
- Create a new branch (e.g. `matcher-proxy`) — **never commit directly to `main`** in that repo.
- Read that repo's existing `app/main.py`, `app/core/auth.py`, `app/core/config.py`, and one
  existing router (e.g. `app/routers/stock.py`) first, to match its exact conventions (it uses
  `asyncpg`, repository-pattern modules, routers with the prefix/auth dependency applied in
  `main.py` — notice this is the **same router-wiring pattern** already used in this repo, not a
  coincidence).

### What to build

A new `app/routers/matcher.py` in that repo, mounted as:

```python
app.include_router(
    matcher.router,
    prefix="/api/matcher",
    tags=["matcher"],
    dependencies=_auth,   # the SAME existing get_current_user dependency every other router
                           # already uses - no new role check, per the decided auth model
)
```

It should expose a thin, 1:1 proxy for every endpoint this service (`design-matcher-api`)
exposes under `/api/v1/*` — `/search`, `/product-types`, `/companies`, `.../collections`,
`.../designs`, the manage endpoints, `/reindex` + `/reindex/{job_id}`. Each proxy route:

1. Receives the request from the frontend (already authenticated as a logged-in Supabase user by
   the existing `get_current_user` dependency — nothing more to check).
2. Forwards it to `f"{settings.matcher_url}/api/v1/{...}"` with an `X-API-Key:
   {settings.matcher_api_key}` header added server-side.
3. For `/search` and the photo-upload endpoints specifically, this means **forwarding a
   multipart body**, not just JSON — use `httpx` (add it as a new dependency to that repo;
   you'll need `httpx.AsyncClient` to stream the forwarded request/response efficiently rather
   than buffering the whole thing in memory, especially since photos are involved).
4. Relays the response back (status code, body, and for the `/api/v1/photos/{token}` case —
   actually, don't proxy that one at all: those signed URLs point directly at
   `design-matcher-api`'s own `PUBLIC_BASE_URL` and the browser hits them directly, bypassing
   this proxy entirely by design — see ARCHITECTURE.md's signed-URL section again if this isn't
   clear).
5. Translates a connection failure/timeout talking to `design-matcher-api` into the same
   `{code, message}` shape the frontend already expects from this service's own errors (reuse
   whatever error convention that repo already has, or introduce the same `{code, message}` shape
   if it doesn't have one yet for other routes — check first).

### New config in that repo

Add to that repo's `app/core/config.py` and its `.env.example`:

- `MATCHER_URL` — base URL of `design-matcher-api` (the Cloudflare Tunnel hostname locally, the
  Railway URL once deployed there).
- `MATCHER_API_KEY` — must equal `design-matcher-api`'s `API_KEY`. **Never** let this reach
  frontend/browser code — it only ever lives in this backend's server-side env.

### Before merging

- Show Hardik the diff/PR before merging to `main`, same as every other change to that repo —
  this is existing, already-deployed, production-adjacent code.
- Confirm `design-matcher-api` is actually reachable (start it locally, point `MATCHER_URL` at
  it, hit a couple of the new `/api/matcher/*` routes by hand) before calling this phase done.
