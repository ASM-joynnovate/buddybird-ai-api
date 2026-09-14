from fastapi.testclient import TestClient

from app.main import app


def test_health_is_available_and_documented() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/health" in schema.json()["paths"]
        response_schema = schema.json()["components"]["schemas"]["HealthResponse"]
        assert "status" in response_schema["required"]
        assert client.get("/docs").status_code == 200
