from fastapi.testclient import TestClient

from raspi_deployer_starter.app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"
