# Catalog format reference

The exact on-disk layout `CATALOG_DIR` must follow, and the JSON schema for every metadata
file. This is the ground truth — `app/catalog/fs.py` and `app/catalog/schema.py` implement
exactly what's described here. If code and this doc ever disagree, that's a bug in one of them;
fix it, don't just pick one silently.

## Directory layout

```
<CATALOG_DIR>/
├── config/
│   └── product_types.json          # optional override of the repo's config/product_types.json
│
├── <company>/                      # one folder per company, e.g. "acme-surfaces"
│   ├── company.json                # optional
│   │
│   ├── <collection>/                # one folder per collection/series/catalog book
│   │   ├── collection.json          # optional
│   │   │
│   │   ├── <design-code>/           # "folder layout" design
│   │   │   ├── info.json            # optional
│   │   │   ├── old/                 # pattern-only photos, color NOT trustworthy
│   │   │   │   ├── photo1.jpg
│   │   │   │   └── ...
│   │   │   └── iphone/              # true-color photos (gray card used), optional
│   │   │       ├── photo1.jpg
│   │   │       └── ...
│   │   │
│   │   └── <design-code>.jpg        # "loose file layout" design - just one image file
│   │
│   └── <another-collection>/
│       └── ...
│
└── <another-company>/
    └── ...
```

Reserved name: `config` is not treated as a company (see `RESERVED_TOP_LEVEL_NAMES` in
`app/catalog/fs.py`). Don't name a real company "config".

## Supported image formats

`.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`, `.heif` (case-insensitive extension match — see
`IMAGE_EXTENSIONS` in `app/catalog/fs.py`). HEIC/HEIF (iPhone's native format) needs
`pillow-heif` registered with Pillow before you can actually open/process one — this isn't
installed yet as of Phase 2; add it in Phase 3 when you start opening files for real, not just
listing them by extension.

## The two design layouts

### 1. Folder layout

```
<company>/<collection>/<design-code>/
    info.json       (optional)
    old/
        *.jpg|png|webp|heic
    iphone/
        *.jpg|png|webp|heic
```

- `old/` holds legacy photos. Pattern is usable; **color is not trustworthy** (bad lighting,
  old scans, etc.) — never use `old/` photos for color matching.
- `iphone/` holds new photos taken with a gray card in frame. Both pattern *and* color are
  trustworthy once white-balanced (Phase 3). A design with at least one `iphone/` photo is
  "color-verified" (`has_color_photo: true` in API responses).
- A design with neither `old/` nor `iphone/` photos (or no folder contents at all) is flagged by
  `catalog-check` as `[no-photos]` — this is a data problem, not a code problem, but the code
  must handle it gracefully (empty list, not a crash).

### 2. Loose-file layout

A single image file sitting directly inside a collection folder, e.g.
`acme-surfaces/classic-woods/AC-102.jpg`. The design code is the filename **without** its
extension (`AC-102`). Treated identically to a folder-layout design whose `old/` contains that
one file and whose `iphone/` is empty — i.e. always `has_color_photo: false`, and it can't have
an `info.json` (there's no folder to put one in) until it's converted.

**Conversion to folder layout happens automatically** (Phase 5) the moment a staff member
uploads an iPhone photo for a loose-file design — see
[ARCHITECTURE.md](ARCHITECTURE.md#two-design-layouts-one-identity) for the exact required
behavior. Never lose the original file in that process.

### Design code collisions within one collection

If a collection somehow has both a folder named `D1` *and* a loose file `D1.jpg`, that's invalid
data — `app/catalog/fs.py::list_designs` resolves it deterministically (folder always wins, the
loose file is ignored) so nothing crashes, but `catalog-check` flags it as `[duplicate-code]` so
a human fixes it. Don't try to "merge" the two automatically.

## JSON metadata files

All three are **entirely optional**. A missing file means "nothing set here, fall through to
the next level" — never treat a missing file as an error. Unknown/extra keys in these files are
ignored (forwards-compatible); malformed JSON is treated as if the file didn't exist (logged,
not fatal) — see `app/catalog/schema.py::_read_json`.

### `company.json`

```json
{
  "display_name": "Acme Surfaces",
  "logo": null,
  "notes": null,
  "default_product_type": "laminate"
}
```

| field                   | type          | meaning                                                           |
| ----------------------- | ------------- | ------------------------------------------------------------------ |
| `display_name`          | string ⎮ null | Shown in the UI instead of the raw folder name. Falls back to the folder name if absent. |
| `logo`                  | string ⎮ null | Not yet used by any endpoint. Reserved for Phase 5+.               |
| `notes`                 | string ⎮ null | Free text, staff-only, not currently surfaced anywhere.            |
| `default_product_type`  | string ⎮ null | Product type id (see below) used as the **last** fallback for every design in this company that has no other type set. |

### `collection.json`

```json
{
  "display_name": "Classic Woods",
  "product_type": "laminate",
  "year": 2023,
  "notes": null
}
```

| field           | type          | meaning |
| --------------- | ------------- | ------- |
| `display_name`  | string ⎮ null | Shown in the UI instead of the raw folder name. |
| `product_type`  | string ⎮ null | Product type id applied to every design in this collection unless the design's own `info.json` overrides it. |
| `year`          | number ⎮ string ⎮ null | Not yet used by any endpoint. |
| `notes`         | string ⎮ null | Free text, staff-only. |

The UI label for "collection" (the middle level) must be configurable per the original brief —
not yet implemented. When you build the frontend brief (Phase 7) or any UI-facing string, treat
the word "Collection" as a display label that should come from config, not be hardcoded in
multiple places.

### `info.json` (one per folder-layout design)

```json
{
  "name": "Golden Oak",
  "product_type": "laminate",
  "category": null,
  "finish": null,
  "thickness": null,
  "size": null,
  "notes": null
}
```

| field          | type          | meaning |
| -------------- | ------------- | ------- |
| `name`         | string ⎮ null | Human-readable design name shown alongside the code. |
| `product_type` | string ⎮ null | Highest-priority override — wins over collection and company. |
| `category`     | string ⎮ null | Free text, staff-defined. |
| `finish`       | string ⎮ null | Free text, e.g. "matte", "gloss". |
| `thickness`    | string ⎮ null | Free text (not a number — real-world values like `"0.8mm"` or `"1 mm"` appear as typed by staff). |
| `size`         | string ⎮ null | Free text. |
| `notes`        | string ⎮ null | Free text. |

### `config/product_types.json`

A JSON **array** (not an object), checked first at `<CATALOG_DIR>/config/product_types.json`,
falling back to the repo's bundled `config/product_types.json` if that override doesn't exist:

```json
[
  { "id": "laminate", "name": "Laminate", "color": "#8B5E3C" },
  { "id": "louver",   "name": "Louver",   "color": "#4A7A8C" },
  { "id": "acrylic",  "name": "Acrylic",  "color": "#5B8C51" },
  { "id": "asa",      "name": "ASA",      "color": "#8C5B8C" }
]
```

| field   | type   | meaning |
| ------- | ------ | ------- |
| `id`    | string | Stable identifier used everywhere else (`info.json`'s `product_type`, API filters, etc.). Treat as case-sensitive, lowercase, no spaces by convention. |
| `name`  | string | Display label for the badge. |
| `color` | string | Hex color for the badge background, e.g. `"#8B5E3C"`. |

`unspecified` is **not** stored in this file — it's hardcoded in
`app/catalog/product_types.py::UNSPECIFIED_TYPE` and always appended to the list returned by
`GET /api/v1/product-types`, so the frontend always has a badge definition for it. Don't add an
`"unspecified"` entry to the JSON file; it'll just be ignored/duplicated.

## Product type resolution order (restated — see ARCHITECTURE.md for the "why")

```
design info.json "product_type"
        │  (if null/missing)
        ▼
collection.json "product_type"
        │  (if null/missing)
        ▼
company.json "default_product_type"
        │  (if null/missing)
        ▼
"unspecified"
```

## Worked example

Given:

```
data/catalog/
├── acme-surfaces/
│   ├── company.json                 {"display_name": "Acme Surfaces", "default_product_type": "laminate"}
│   ├── classic-woods/
│   │   ├── collection.json           {"display_name": "Classic Woods", "product_type": "laminate"}
│   │   ├── AC-100/
│   │   │   ├── info.json             {"name": "Golden Oak"}
│   │   │   ├── old/AC-100_1.jpg
│   │   │   └── iphone/AC-100_iphone_1.jpg
│   │   └── AC-102.jpg                (loose file)
│   └── trial-batch/
│       └── AC-300.jpg                (loose file, no collection.json)
```

- `AC-100` → product_type resolves to `"laminate"` (from `collection.json`, since its own
  `info.json` doesn't set one). `has_color_photo: true`.
- `AC-102` → product_type resolves to `"laminate"` (from `collection.json`). `has_color_photo:
  false` (loose file, can't have an iphone/ folder).
- `AC-300` → `trial-batch` has no `collection.json` at all, so it falls through to the company's
  `default_product_type`: `"laminate"`. If `company.json` had also been missing, this would
  resolve to `"unspecified"`.

A ready-made version of this exact scenario (plus a second company with a genuine
`"unspecified"` case) is generated by `scripts/generate_sample_catalog.py` — run it and poke
around rather than hand-building fixtures from scratch.
