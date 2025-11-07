import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Configure environment variables before importing the app so settings pick them up.
os.environ.setdefault("ADMIN_PASS", "secret123")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("READONLY_USER", "viewer")
os.environ.setdefault("READONLY_PASS", "viewer123")

_registry_tmp = tempfile.NamedTemporaryFile(delete=False)
_registry_tmp.close()
os.environ["DEVICES_REG_PATH"] = _registry_tmp.name

from raspi_deployer_starter.app import deps

deps.get_settings.cache_clear()

from raspi_deployer_starter.app.main import app

client = TestClient(app)


def _admin_headers():
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "secret123"}
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _readonly_headers():
    response = client.post(
        "/auth/login", json={"username": "viewer", "password": "viewer123"}
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def cleanup_registry():
    yield
    Path(_registry_tmp.name).unlink(missing_ok=True)


def test_login_success():
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "secret123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["role"] == "admin"


def test_login_failure():
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert response.status_code == 401


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"
    assert isinstance(payload.get("uptime_seconds"), int)


def test_info_requires_auth():
    response = client.get("/info")
    assert response.status_code == 401


def test_info_with_token():
    response = client.get("/info", headers=_readonly_headers())
    assert response.status_code == 200
    payload = response.json()
    assert "hostname" in payload


@patch("raspi_deployer_starter.app.main.ifaddr.get_adapters")
def test_get_local_networks_success(mock_get_adapters):
    adapters = MagicMock()
    ip1 = MagicMock()
    ip1.ip = "192.168.1.100"
    ip1.network_prefix = 24
    ip1.is_IPv4 = True

    ip2 = MagicMock()
    ip2.ip = "127.0.0.1"
    ip2.network_prefix = 8
    ip2.is_IPv4 = True

    adapter1 = MagicMock()
    adapter1.ips = [ip1, ip2]

    mock_get_adapters.return_value = [adapter1]

    response = client.get("/api/local-networks")
    assert response.status_code == 200
    assert response.json() == ["192.168.1.0/24"]


def test_get_local_networks_not_found():
    with patch("raspi_deployer_starter.app.main.ifaddr.get_adapters", return_value=[]):
        response = client.get("/api/local-networks")
        assert response.status_code == 404
        assert "No se pudo detectar" in response.json()["detail"]


@patch("raspi_deployer_starter.app.main.fabric.Connection")
def test_get_device_details_success(mock_fabric_connection):
    mock_conn = MagicMock()

    mock_df_result = MagicMock()
    mock_df_result.stdout = "15401940  8334424   6489820    57%"

    mock_uptime_result = MagicMock()
    mock_uptime_result.stdout = "up 2 hours, 30 minutes"

    mock_temp_result = MagicMock()
    mock_temp_result.ok = True
    mock_temp_result.stdout = "temp=45.5'C"

    mock_conn.run.side_effect = [
        mock_df_result,
        mock_uptime_result,
        mock_temp_result,
    ]

    mock_fabric_connection.return_value = mock_conn

    response = client.post(
        "/api/device/details/192.168.1.50",
        json={"user": "pi", "password": "fake_password"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["storage"]["total"] == "14.7G"
    assert data["storage"]["used"] == "7.9G"
    assert data["storage"]["percent"] == 57
    assert data["uptime"] == "2 hours, 30 minutes"
    assert data["temp"] == "45.5'C"


@patch("raspi_deployer_starter.app.main.fabric.Connection")
def test_get_device_details_ssh_failure(mock_fabric_connection):
    mock_conn = MagicMock()
    mock_conn.open.side_effect = Exception("Authentication failed.")
    mock_fabric_connection.return_value = mock_conn

    response = client.post(
        "/api/device/details/192.168.1.51",
        json={"user": "pi", "password": "wrong_password"},
    )

    assert response.status_code == 400
    assert "Error en 192.168.1.51: Authentication failed." in response.json()["detail"]


def test_registry_upsert_and_list():
    headers = _admin_headers()
    payload = {
        "id": "test-pi",
        "name": "Test Pi",
        "base_url": "http://example.com",
    }
    response = client.post("/registry/devices", json=payload, headers=headers)
    assert response.status_code == 200

    response = client.get("/registry/devices", headers=_readonly_headers())
    assert response.status_code == 200
    devices = response.json()["devices"]
    assert any(device["id"] == "test-pi" for device in devices)

    response = client.delete("/registry/devices/test-pi", headers=headers)
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_registry_proxy_unknown_device():
    response = client.get(
        "/registry/unknown/proxy/metrics",
        headers=_readonly_headers(),
    )
    assert response.status_code == 404


def test_reboot_requires_confirmation():
    response = client.post("/system/reboot", headers=_admin_headers())
    assert response.status_code == 400
