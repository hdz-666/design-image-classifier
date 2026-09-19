from __future__ import annotations

import json
from pathlib import Path

from app.config import settings

DEFAULT_PRODUCT_TYPES = [
    {"id": "laminate", "name": "Laminate", "color": "#8B5E3C"},
    {"id": "louver", "name": "Louver", "color": "#4A7A8C"},
    {"id": "acrylic", "name": "Acrylic", "color": "#5B8C51"},
    {"id": "asa", "name": "ASA", "color": "#8C5B8C"},
]

# Always appended, never editable via config/product_types.json - it's the
# sentinel used when no info.json/collection.json/company.json sets a type.
UNSPECIFIED_TYPE = {"id": "unspecified", "name": "Unspecified", "color": "#9AA0A6"}

REPO_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "product_types.json"


def _config_path() -> Path:
    override = Path(settings.catalog_dir) / "config" / "product_types.json"
    if override.is_file():
        return override
    return REPO_DEFAULT_PATH


def load_product_types(*, include_unspecified: bool = True) -> list[dict]:
    path = _config_path()
    types = DEFAULT_PRODUCT_TYPES
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                types = data
        except (json.JSONDecodeError, OSError):
            pass
    if include_unspecified:
        types = [*types, UNSPECIFIED_TYPE]
    return types


def known_product_type_ids() -> set[str]:
    return {t["id"] for t in load_product_types(include_unspecified=True)}
