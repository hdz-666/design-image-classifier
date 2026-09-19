from __future__ import annotations

import hashlib
from collections import defaultdict

from app.catalog import fs
from app.catalog.schema import UNSPECIFIED, read_collection_json, read_company_json, resolve_product_type


def _hash_file(path) -> str | None:
    try:
        with path.open("rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def run_catalog_check() -> list[str]:
    issues: list[str] = []
    photo_hashes: dict[str, list[str]] = defaultdict(list)

    root = fs.catalog_root()
    if not root.is_dir():
        return [f"[missing] catalog directory does not exist: {root}"]

    for entry in root.iterdir():
        if entry.name.startswith(".") or entry.name in fs.RESERVED_TOP_LEVEL_NAMES:
            continue
        if not entry.is_dir():
            issues.append(f"[wrong-depth] unexpected file at catalog root: {entry.name}")

    companies = fs.list_companies()
    if not companies:
        issues.append("[empty] catalog has no companies")

    for company in companies:
        company_dir = fs.safe_join(company)
        company_meta = read_company_json(company_dir)

        for entry in company_dir.iterdir():
            if entry.name.startswith(".") or entry.name == "company.json":
                continue
            if not entry.is_dir():
                issues.append(f"[wrong-depth] unexpected file in company '{company}': {entry.name}")

        collections = fs.list_collections(company)
        if not collections:
            issues.append(f"[empty] {company}: no collections")

        for collection in collections:
            collection_dir = fs.safe_join(company, collection)
            collection_meta = read_collection_json(collection_dir)

            entries = [e for e in collection_dir.iterdir() if not e.name.startswith(".")]
            dir_names = {e.name for e in entries if e.is_dir()}
            loose_stems = {e.stem for e in entries if e.is_file() and fs.is_image_file(e)}
            for code in dir_names & loose_stems:
                issues.append(
                    f"[duplicate-code] {company}/{collection}/{code}: "
                    "both a folder and a loose image use this design code"
                )

            refs = fs.list_designs(company, collection)
            if not refs:
                issues.append(f"[empty] {company}/{collection}: no designs")

            for ref in refs:
                photos = fs.design_photos(ref)
                all_photos = photos["old"] + photos["iphone"]

                if not all_photos:
                    issues.append(f"[no-photos] {company}/{collection}/{ref.code}")
                if not photos["iphone"]:
                    issues.append(f"[no-iphone-photos] {company}/{collection}/{ref.code}")

                for p in all_photos:
                    digest = _hash_file(p)
                    if digest is None:
                        issues.append(f"[unreadable] {p}")
                        continue
                    photo_hashes[digest].append(str(p))

                pt = resolve_product_type(ref, collection_meta=collection_meta, company_meta=company_meta)
                if pt == UNSPECIFIED:
                    issues.append(f"[no-product-type] {company}/{collection}/{ref.code}")

    for digest, paths in photo_hashes.items():
        if len(paths) > 1:
            issues.append("[duplicate-photo] " + ", ".join(paths))

    return issues
