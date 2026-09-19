def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_health_has_no_error_envelope(client):
    resp = client.get("/health")
    assert "code" not in resp.json()
