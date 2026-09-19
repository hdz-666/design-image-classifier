"""Generates a small synthetic catalog for local testing and dev.

No real product photos - just solid-color squares with a few random lines
so images differ from each other. Enough to exercise both design layouts
(folder-with-old/iphone vs. loose file), info.json/collection.json/
company.json presence, and the product-type resolution order.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw

# (code, layout, has_iphone_photo, info.json content or None)
_CATALOG_PLAN = {
    "acme-surfaces": {
        "meta": {"display_name": "Acme Surfaces", "default_product_type": "laminate"},
        "collections": {
            "classic-woods": {
                "meta": {"display_name": "Classic Woods", "product_type": "laminate"},
                "designs": [
                    ("AC-100", "folder", True, {"name": "Golden Oak"}),
                    ("AC-101", "folder", False, {"name": "Walnut Grain"}),
                    ("AC-102", "loose", False, None),
                ],
            },
            "modern-acrylics": {
                "meta": {"display_name": "Modern Acrylics", "product_type": "acrylic"},
                "designs": [
                    ("AC-200", "folder", True, {"name": "Pearl White", "notes": "plain finish"}),
                    ("AC-201", "loose", False, None),
                ],
            },
            "trial-batch": {
                "meta": {},
                "designs": [
                    ("AC-300", "loose", False, None),
                ],
            },
        },
    },
    "brightline": {
        "meta": {"display_name": "Brightline Panels"},
        "collections": {
            "louver-series-1": {
                "meta": {},
                "designs": [
                    ("BL-01", "folder", True, {"name": "Slat Grey", "product_type": "louver"}),
                    ("BL-02", "folder", False, {"product_type": "louver"}),
                    ("BL-03", "loose", False, None),
                ],
            },
        },
    },
}


def _make_image(path: Path, color: tuple[int, int, int], size: int = 300) -> None:
    img = Image.new("RGB", (size, size), color)
    draw = ImageDraw.Draw(img)
    inverse = tuple(255 - c for c in color)
    for _ in range(6):
        x0, y0 = random.randint(0, size), random.randint(0, size)
        x1, y1 = random.randint(0, size), random.randint(0, size)
        draw.line((x0, y0, x1, y1), fill=inverse, width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=85)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def generate_sample_catalog(root: Path, seed: int = 0) -> None:
    random.seed(seed)
    root.mkdir(parents=True, exist_ok=True)

    for company, company_data in _CATALOG_PLAN.items():
        company_dir = root / company
        company_dir.mkdir(parents=True, exist_ok=True)
        if company_data["meta"]:
            _write_json(company_dir / "company.json", company_data["meta"])

        for collection, collection_data in company_data["collections"].items():
            collection_dir = company_dir / collection
            collection_dir.mkdir(parents=True, exist_ok=True)
            if collection_data["meta"]:
                _write_json(collection_dir / "collection.json", collection_data["meta"])

            for code, layout, has_iphone, info in collection_data["designs"]:
                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                if layout == "folder":
                    design_dir = collection_dir / code
                    _make_image(design_dir / "old" / f"{code}_1.jpg", color)
                    if has_iphone:
                        _make_image(design_dir / "iphone" / f"{code}_iphone_1.jpg", color)
                    if info:
                        _write_json(design_dir / "info.json", info)
                else:
                    _make_image(collection_dir / f"{code}.jpg", color)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="./data/catalog", help="Output catalog directory")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    generate_sample_catalog(Path(args.out), seed=args.seed)
    print(f"Sample catalog written to {args.out}")


if __name__ == "__main__":
    main()
