from fastapi import APIRouter, Query

from app.catalog import fs
from app.catalog.product_types import load_product_types
from app.catalog.schema import (
    UNSPECIFIED,
    read_collection_json,
    read_company_json,
    read_design_info_json,
    resolve_product_type,
)
from app.errors import AppError
from app.schemas.catalog import (
    CollectionSummarySchema,
    CompanySummarySchema,
    DesignDetailSchema,
    DesignPageSchema,
    DesignSummarySchema,
    PhotoRefSchema,
    ProductTypeSchema,
)
from app.security import build_photo_url

router = APIRouter()


def _require_company_dir(company: str):
    company_dir = fs.safe_join(company)
    if not company_dir.is_dir():
        raise AppError(code="not_found", message="Company not found.", status_code=404)
    return company_dir


def _require_collection_dir(company: str, collection: str):
    collection_dir = fs.safe_join(company, collection)
    if not collection_dir.is_dir():
        raise AppError(code="not_found", message="Collection not found.", status_code=404)
    return collection_dir


@router.get("/product-types", response_model=list[ProductTypeSchema])
async def get_product_types():
    return load_product_types()


@router.get("/companies", response_model=list[CompanySummarySchema])
async def list_companies():
    summaries = []
    for company in fs.list_companies():
        summaries.append(_company_summary(company))
    return summaries


def _company_summary(company: str) -> CompanySummarySchema:
    company_dir = _require_company_dir(company)
    company_meta = read_company_json(company_dir)

    total = 0
    color_verified = 0
    counts_by_type: dict[str, int] = {}

    for collection in fs.list_collections(company):
        collection_dir = fs.safe_join(company, collection)
        collection_meta = read_collection_json(collection_dir)
        for ref in fs.list_designs(company, collection):
            total += 1
            pt = resolve_product_type(ref, collection_meta=collection_meta, company_meta=company_meta)
            counts_by_type[pt] = counts_by_type.get(pt, 0) + 1
            if fs.design_photos(ref)["iphone"]:
                color_verified += 1

    return CompanySummarySchema(
        id=company,
        display_name=company_meta.get("display_name") or company,
        design_count=total,
        color_verified_count=color_verified,
        counts_by_type=counts_by_type,
    )


@router.get("/companies/{company}/collections", response_model=list[CollectionSummarySchema])
async def list_collections(company: str):
    company_dir = _require_company_dir(company)
    company_meta = read_company_json(company_dir)
    return [_collection_summary(company, company_meta, collection) for collection in fs.list_collections(company)]


def _collection_summary(company: str, company_meta: dict, collection: str) -> CollectionSummarySchema:
    collection_dir = fs.safe_join(company, collection)
    collection_meta = read_collection_json(collection_dir)

    total = 0
    color_verified = 0
    counts_by_type: dict[str, int] = {}

    for ref in fs.list_designs(company, collection):
        total += 1
        pt = resolve_product_type(ref, collection_meta=collection_meta, company_meta=company_meta)
        counts_by_type[pt] = counts_by_type.get(pt, 0) + 1
        if fs.design_photos(ref)["iphone"]:
            color_verified += 1

    return CollectionSummarySchema(
        id=collection,
        display_name=collection_meta.get("display_name") or collection,
        product_type=collection_meta.get("product_type"),
        design_count=total,
        color_verified_count=color_verified,
        counts_by_type=counts_by_type,
    )


@router.get(
    "/companies/{company}/collections/{collection}/designs",
    response_model=DesignPageSchema,
)
async def list_designs(
    company: str,
    collection: str,
    search: str | None = None,
    product_type: list[str] | None = Query(default=None),
    needs_color_photo: bool | None = None,
    needs_product_type: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    company_dir = _require_company_dir(company)
    _require_collection_dir(company, collection)
    company_meta = read_company_json(company_dir)
    collection_dir = fs.safe_join(company, collection)
    collection_meta = read_collection_json(collection_dir)

    items: list[DesignSummarySchema] = []
    for ref in fs.list_designs(company, collection):
        info = read_design_info_json(ref)
        pt = resolve_product_type(ref, design_info=info, collection_meta=collection_meta, company_meta=company_meta)
        name = info.get("name")

        if search and search.lower() not in f"{ref.code} {name or ''}".lower():
            continue
        if product_type and pt not in product_type:
            continue

        has_color = bool(fs.design_photos(ref)["iphone"])
        if needs_color_photo is True and has_color:
            continue
        if needs_color_photo is False and not has_color:
            continue
        if needs_product_type is True and pt != UNSPECIFIED:
            continue
        if needs_product_type is False and pt == UNSPECIFIED:
            continue

        items.append(
            DesignSummarySchema(
                company=company,
                collection=collection,
                code=ref.code,
                name=name,
                product_type=pt,
                layout=ref.layout,
                has_color_photo=has_color,
            )
        )

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    return DesignPageSchema(items=page_items, page=page, page_size=page_size, total=total)


@router.get("/designs/{company}/{collection}/{code}", response_model=DesignDetailSchema)
async def get_design(company: str, collection: str, code: str):
    company_dir = _require_company_dir(company)
    _require_collection_dir(company, collection)
    company_meta = read_company_json(company_dir)
    collection_dir = fs.safe_join(company, collection)
    collection_meta = read_collection_json(collection_dir)

    ref = fs.find_design(company, collection, code)
    if ref is None:
        raise AppError(code="not_found", message="Design not found.", status_code=404)

    info = read_design_info_json(ref)
    pt = resolve_product_type(ref, design_info=info, collection_meta=collection_meta, company_meta=company_meta)
    photos = fs.design_photos(ref)

    photo_refs = [
        PhotoRefSchema(
            photo_id=f"{kind}/{path.name}",
            photo_type=kind,
            url=build_photo_url(path, catalog_root=fs.catalog_root()),
        )
        for kind, paths in photos.items()
        for path in paths
    ]

    return DesignDetailSchema(
        company=company,
        collection=collection,
        code=code,
        name=info.get("name"),
        product_type=pt,
        layout=ref.layout,
        has_color_photo=bool(photos["iphone"]),
        category=info.get("category"),
        finish=info.get("finish"),
        thickness=info.get("thickness"),
        size=info.get("size"),
        notes=info.get("notes"),
        photos=photo_refs,
    )
