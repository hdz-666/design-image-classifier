from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_api_key
from app.errors import register_exception_handlers


def _protected_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    async def protected():
        return {"ok": True}

    return app


def test_missing_api_key_rejected():
    resp = TestClient(_protected_app()).get("/protected")
    assert resp.status_code == 401
    assert resp.json() == {"code": "unauthorized", "message": "Missing or invalid API key."}


def test_wrong_api_key_rejected():
    resp = TestClient(_protected_app()).get("/protected", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_correct_api_key_allowed(api_key):
    resp = TestClient(_protected_app()).get("/protected", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
