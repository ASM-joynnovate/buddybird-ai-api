from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import create_app
from core.common.errors import ResourceNotFoundError


class EchoRequest(BaseModel):
    value: int


@pytest.fixture
def app() -> FastAPI:
    app_ = create_app()

    @app_.get("/test/custom-error")
    async def raise_custom_error() -> None:
        raise ResourceNotFoundError

    @app_.post("/test/validation")
    async def validate(body: EchoRequest) -> EchoRequest:
        return body

    @app_.get("/test/unhandled")
    async def raise_unhandled() -> None:
        raise RuntimeError("unhandled")

    return app_


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as client_:
        yield client_


def test_healthz_is_available_and_documented(client: TestClient) -> None:
    response = client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/api/healthz" in schema.json()["paths"]
    assert client.get("/docs").status_code == 200


def test_custom_error_returns_error_code_and_message(client: TestClient) -> None:
    response = client.get("/test/custom-error")
    assert response.status_code == 404
    assert response.json() == {
        "error_code": "COMMON__RESOURCE_NOT_FOUND",
        "message": "요청한 리소스를 찾을 수 없습니다.",
    }


def test_request_validation_error_returns_error_code_and_message(
    client: TestClient,
) -> None:
    response = client.post("/test/validation", json={"value": "not-a-number"})
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "COMMON__REQUEST_VALIDATION_ERROR"
    assert body["message"] == "요청값 검증 오류가 발생했습니다."


def test_unhandled_error_returns_error_code_and_message(client: TestClient) -> None:
    response = client.get("/test/unhandled")
    assert response.status_code == 500
    assert response.json() == {
        "error_code": "COMMON__INTERNAL_SERVER_ERROR",
        "message": "서버 내부 오류가 발생했습니다. 관리자에게 문의해주세요.",
    }
