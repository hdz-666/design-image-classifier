def test_browse_requires_api_key(client):
    resp = client.get("/api/v1/product-types")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


def test_product_types_includes_defaults_and_unspecified(client, auth_headers):
    resp = client.get("/api/v1/product-types", headers=auth_headers)
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert {"laminate", "louver", "acrylic", "asa", "unspecified"} <= ids


def test_list_companies_counts(client, auth_headers):
    resp = client.get("/api/v1/companies", headers=auth_headers)
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()}

    acme = by_id["acme-surfaces"]
    assert acme["design_count"] == 6
    assert acme["color_verified_count"] == 2
    assert acme["counts_by_type"] == {"laminate": 4, "acrylic": 2}

    brightline = by_id["brightline"]
    assert brightline["design_count"] == 3
    assert brightline["color_verified_count"] == 1
    assert brightline["counts_by_type"] == {"louver": 2, "unspecified": 1}


def test_list_companies_unknown_company_not_included(client, auth_headers):
    resp = client.get("/api/v1/companies", headers=auth_headers)
    ids = {c["id"] for c in resp.json()}
    assert "does-not-exist" not in ids


def test_unknown_company_returns_404(client, auth_headers):
    resp = client.get("/api/v1/companies/does-not-exist/collections", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_list_collections_type_inheritance(client, auth_headers):
    resp = client.get("/api/v1/companies/acme-surfaces/collections", headers=auth_headers)
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()}

    trial = by_id["trial-batch"]
    # no collection.json product_type -> falls back to company default at design level
    assert trial["product_type"] is None
    assert trial["counts_by_type"] == {"laminate": 1}


def test_design_code_does_not_collide_across_collections(client, auth_headers):
    # AC-100..102 live only in classic-woods; modern-acrylics has its own codes
    resp = client.get(
        "/api/v1/companies/acme-surfaces/collections/modern-acrylics/designs",
        headers=auth_headers,
    )
    codes = {d["code"] for d in resp.json()["items"]}
    assert codes == {"AC-200", "AC-201"}


def test_list_designs_filter_by_product_type(client, auth_headers):
    resp = client.get(
        "/api/v1/companies/brightline/collections/louver-series-1/designs",
        params={"product_type": "unspecified"},
        headers=auth_headers,
    )
    items = resp.json()["items"]
    assert [d["code"] for d in items] == ["BL-03"]


def test_list_designs_filter_needs_color_photo(client, auth_headers):
    resp = client.get(
        "/api/v1/companies/brightline/collections/louver-series-1/designs",
        params={"needs_color_photo": True},
        headers=auth_headers,
    )
    codes = {d["code"] for d in resp.json()["items"]}
    assert codes == {"BL-02", "BL-03"}


def test_list_designs_search(client, auth_headers):
    resp = client.get(
        "/api/v1/companies/acme-surfaces/collections/classic-woods/designs",
        params={"search": "golden"},
        headers=auth_headers,
    )
    items = resp.json()["items"]
    assert [d["code"] for d in items] == ["AC-100"]


def test_list_designs_pagination(client, auth_headers):
    resp = client.get(
        "/api/v1/companies/acme-surfaces/collections/classic-woods/designs",
        params={"page": 1, "page_size": 2},
        headers=auth_headers,
    )
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_design_detail_folder_layout(client, auth_headers):
    resp = client.get(
        "/api/v1/designs/acme-surfaces/classic-woods/AC-100",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Golden Oak"
    assert body["product_type"] == "laminate"
    assert body["has_color_photo"] is True
    assert len(body["photos"]) == 2
    assert all(p["url"].startswith("http") for p in body["photos"])


def test_design_detail_unknown_returns_404(client, auth_headers):
    resp = client.get(
        "/api/v1/designs/acme-surfaces/classic-woods/NOPE",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_signed_photo_url_serves_image(client, auth_headers):
    detail = client.get(
        "/api/v1/designs/acme-surfaces/classic-woods/AC-100",
        headers=auth_headers,
    ).json()
    photo_url = detail["photos"][0]["url"]
    path = photo_url.split("/api/v1/photos/", 1)[1]

    # no auth header at all - signed URLs work without the API key
    resp = client.get(f"/api/v1/photos/{path}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_signed_photo_url_rejects_tampered_token(client):
    resp = client.get("/api/v1/photos/not-a-real-token")
    assert resp.status_code == 404
