from __future__ import annotations

import json
from pathlib import Path

from app.catalog.fs import DesignRef

UNSPECIFIED = "unspecified"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_company_json(company_dir: Path) -> dict:
    return _read_json(company_dir / "company.json")


def read_collection_json(collection_dir: Path) -> dict:
    return _read_json(collection_dir / "collection.json")


def read_design_info_json(ref: DesignRef) -> dict:
    if ref.layout != "folder":
        return {}
    return _read_json(ref.path / "info.json")


def resolve_product_type(
    ref: DesignRef,
    *,
    design_info: dict | None = None,
    collection_meta: dict,
    company_meta: dict,
) -> str:
    info = design_info if design_info is not None else read_design_info_json(ref)
    if info.get("product_type"):
        return info["product_type"]
    if collection_meta.get("product_type"):
        return collection_meta["product_type"]
    if company_meta.get("default_product_type"):
        return company_meta["default_product_type"]
    return UNSPECIFIED
