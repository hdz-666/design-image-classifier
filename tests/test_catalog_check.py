from app.catalog.check import run_catalog_check


def test_catalog_check_flags_missing_iphone_photos(catalog_dir):
    issues = run_catalog_check()
    assert any("no-iphone-photos" in i and "AC-101" in i for i in issues)


def test_catalog_check_flags_missing_product_type(catalog_dir):
    issues = run_catalog_check()
    assert any("no-product-type" in i and "BL-03" in i for i in issues)


def test_catalog_check_no_false_positive_for_complete_design(catalog_dir):
    issues = run_catalog_check()
    assert not any("AC-100" in i for i in issues)


def test_catalog_check_detects_duplicate_photo(tmp_path, monkeypatch):
    import app.catalog.fs as fs_module
    from app.config import settings

    catalog = tmp_path / "dup-catalog"
    (catalog / "acme" / "col" / "D1" / "old").mkdir(parents=True)
    (catalog / "acme" / "col" / "D2" / "old").mkdir(parents=True)
    data = b"same-bytes-not-a-real-image"
    (catalog / "acme" / "col" / "D1" / "old" / "a.jpg").write_bytes(data)
    (catalog / "acme" / "col" / "D2" / "old" / "b.jpg").write_bytes(data)

    monkeypatch.setattr(settings, "catalog_dir", str(catalog))
    assert fs_module.catalog_root() == catalog

    issues = run_catalog_check()
    assert any("duplicate-photo" in i for i in issues)


def test_catalog_check_detects_duplicate_design_code(tmp_path, monkeypatch):
    import app.catalog.fs as fs_module
    from app.config import settings

    catalog = tmp_path / "collide-catalog"
    (catalog / "acme" / "col" / "D1" / "old").mkdir(parents=True)
    (catalog / "acme" / "col" / "D1" / "old" / "a.jpg").write_bytes(b"x")
    (catalog / "acme" / "col" / "D1.jpg").write_bytes(b"y")

    monkeypatch.setattr(settings, "catalog_dir", str(catalog))
    assert fs_module.catalog_root() == catalog

    issues = run_catalog_check()
    assert any("duplicate-code" in i and "D1" in i for i in issues)
