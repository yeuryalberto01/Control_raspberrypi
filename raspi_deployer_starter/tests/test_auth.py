import os
import pytest
from fastapi.testclient import TestClient

from raspi_deployer_starter.app import deps
from raspi_deployer_starter.app.main import app


@pytest.fixture(autouse=True, scope="module")
def configure_env():
    os.environ.setdefault("ADMIN_USER", "admin")
    os.environ.setdefault("ADMIN_PASS", "secret123")
    os.environ.setdefault("JWT_SECRET", "test-secret")
    os.environ.setdefault("READONLY_USER", "viewer")
    os.environ.setdefault("READONLY_PASS", "viewer123")
    deps.get_settings.cache_clear()
    yield
    deps.get_settings.cache_clear()


client = TestClient(app)


def test_login_failure_rate_limit():
    for _ in range(3):
        response = client.post("/auth/login", json={"username": "wrong", "password": "nope"})
        assert response.status_code == 401


def test_login_success():
    response = client.post("/auth/login", json={"username": "admin", "password": "secret123"})
    assert response.status_code == 200
    payload = response.json()
    assert "token" in payload and payload["role"] == "admin"
