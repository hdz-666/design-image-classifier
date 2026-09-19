from typing import Literal

from pydantic import BaseModel


class ProductTypeSchema(BaseModel):
    id: str
    name: str
    color: str


class CompanySummarySchema(BaseModel):
    id: str
    display_name: str
    design_count: int
    color_verified_count: int
    counts_by_type: dict[str, int]


class CollectionSummarySchema(BaseModel):
    id: str
    display_name: str
    product_type: str | None
    design_count: int
    color_verified_count: int
    counts_by_type: dict[str, int]


class DesignSummarySchema(BaseModel):
    company: str
    collection: str
    code: str
    name: str | None
    product_type: str
    layout: Literal["folder", "loose"]
    has_color_photo: bool


class DesignPageSchema(BaseModel):
    items: list[DesignSummarySchema]
    page: int
    page_size: int
    total: int


class PhotoRefSchema(BaseModel):
    photo_id: str
    photo_type: Literal["old", "iphone"]
    url: str


class DesignDetailSchema(DesignSummarySchema):
    category: str | None = None
    finish: str | None = None
    thickness: str | None = None
    size: str | None = None
    notes: str | None = None
    photos: list[PhotoRefSchema]
