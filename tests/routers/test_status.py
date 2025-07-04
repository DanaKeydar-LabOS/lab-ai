from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_status() -> None:
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == {"status": "running"}
