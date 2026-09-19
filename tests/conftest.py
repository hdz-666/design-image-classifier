import os
import tempfile
from pathlib import Path

os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

_TEST_CATALOG_DIR = Path(tempfile.mkdtemp(prefix="design-matcher-test-catalog-"))
os.environ["CATALOG_DIR"] = str(_TEST_CATALOG_DIR)

from scripts.generate_sample_catalog import generate_sample_catalog  # noqa: E402

generate_sample_catalog(_TEST_CATALOG_DIR)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key():
    return os.environ["API_KEY"]


@pytest.fixture
def auth_headers(api_key):
    return {"X-API-Key": api_key}


@pytest.fixture
def catalog_dir():
    return _TEST_CATALOG_DIR
