from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import settings
from app.errors import AppError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
RESERVED_TOP_LEVEL_NAMES = {"config"}
PHOTO_KINDS = ("old", "iphone")


def catalog_root() -> Path:
    return Path(settings.catalog_dir)


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def validate_segment(name: str, *, label: str = "name") -> str:
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        raise AppError(code="invalid_path", message=f"That {label} isn't valid.", status_code=400)
    return name


def safe_join(*segments: str) -> Path:
    root = catalog_root().resolve()
    path = root
    for seg in segments:
        validate_segment(seg)
        path = path / seg
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise AppError(code="invalid_path", message="That path isn't valid.", status_code=400)
    return resolved


def _child_dirs(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(
        (e for e in path.iterdir() if e.is_dir() and not e.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )


def list_companies() -> list[str]:
    return [
        d.name
        for d in _child_dirs(catalog_root())
        if d.name not in RESERVED_TOP_LEVEL_NAMES
    ]


def list_collections(company: str) -> list[str]:
    return [d.name for d in _child_dirs(safe_join(company))]


@dataclass(frozen=True)
class DesignRef:
    company: str
    collection: str
    code: str
    layout: Literal["folder", "loose"]
    path: Path


def list_designs(company: str, collection: str) -> list[DesignRef]:
    collection_dir = safe_join(company, collection)
    if not collection_dir.is_dir():
        return []

    entries = [e for e in collection_dir.iterdir() if not e.name.startswith(".")]
    dirs = sorted((e for e in entries if e.is_dir()), key=lambda p: p.name.lower())
    files = sorted(
        (e for e in entries if e.is_file() and is_image_file(e)),
        key=lambda p: p.name.lower(),
    )

    refs: dict[str, DesignRef] = {}
    for d in dirs:
        refs[d.name] = DesignRef(company, collection, d.name, "folder", d)
    for f in files:
        if f.stem not in refs:
            refs[f.stem] = DesignRef(company, collection, f.stem, "loose", f)

    return sorted(refs.values(), key=lambda r: r.code.lower())


def find_design(company: str, collection: str, code: str) -> DesignRef | None:
    for ref in list_designs(company, collection):
        if ref.code == code:
            return ref
    return None


def design_photos(ref: DesignRef) -> dict[str, list[Path]]:
    if ref.layout == "loose":
        return {"old": [ref.path], "iphone": []}

    def _list(sub: str) -> list[Path]:
        d = ref.path / sub
        if not d.is_dir():
            return []
        return sorted(
            (p for p in d.iterdir() if is_image_file(p)),
            key=lambda p: p.name.lower(),
        )

    return {"old": _list("old"), "iphone": _list("iphone")}
