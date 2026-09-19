import pytest

from app.catalog import fs
from app.errors import AppError


def test_list_companies(catalog_dir):
    assert set(fs.list_companies()) == {"acme-surfaces", "brightline"}


def test_list_collections(catalog_dir):
    assert set(fs.list_collections("acme-surfaces")) == {
        "classic-woods",
        "modern-acrylics",
        "trial-batch",
    }


def test_list_designs_mixed_layout(catalog_dir):
    refs = fs.list_designs("acme-surfaces", "classic-woods")
    by_code = {r.code: r for r in refs}
    assert by_code["AC-100"].layout == "folder"
    assert by_code["AC-102"].layout == "loose"


def test_design_photos_folder_layout(catalog_dir):
    ref = fs.find_design("acme-surfaces", "classic-woods", "AC-100")
    photos = fs.design_photos(ref)
    assert len(photos["old"]) == 1
    assert len(photos["iphone"]) == 1


def test_design_photos_loose_layout_has_no_iphone(catalog_dir):
    ref = fs.find_design("acme-surfaces", "classic-woods", "AC-102")
    photos = fs.design_photos(ref)
    assert len(photos["old"]) == 1
    assert photos["iphone"] == []


def test_find_design_missing_returns_none(catalog_dir):
    assert fs.find_design("acme-surfaces", "classic-woods", "NOPE") is None


@pytest.mark.parametrize("bad", ["..", ".", "a/b", "a\\b", ""])
def test_safe_join_rejects_traversal(catalog_dir, bad):
    with pytest.raises(AppError):
        fs.safe_join(bad)


def test_safe_join_stays_inside_catalog_root(catalog_dir):
    # even a validated single segment can't be used to climb out
    resolved = fs.safe_join("acme-surfaces")
    root = fs.catalog_root().resolve()
    assert root == resolved or root in resolved.parents
