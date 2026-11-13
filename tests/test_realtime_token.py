from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.deps import require_authenticated_user
from app.core.config import settings
from app.main import app
from app.v1.endpoints.realtime_token import token_rate_limit

client = TestClient(app)
ALLOWED_ORIGIN = "http://localhost:4200"


def _authorize_test_user():
    app.dependency_overrides[require_authenticated_user] = lambda: object()
    app.dependency_overrides[token_rate_limit] = lambda: None


def _clear_test_overrides():
    app.dependency_overrides.pop(require_authenticated_user, None)
    app.dependency_overrides.pop(token_rate_limit, None)


def test_realtime_token_requires_authenticated_user():
    app.dependency_overrides[token_rate_limit] = lambda: None
    try:
        response = client.post("/api/realtime-token", headers={"Origin": ALLOWED_ORIGIN})
    finally:
        app.dependency_overrides.pop(token_rate_limit, None)
    assert response.status_code == 401


def test_realtime_token_requires_server_key(monkeypatch):
    _authorize_test_user()
    monkeypatch.setattr(settings, "DECART_API_KEY", None)
    try:
        response = client.post("/api/realtime-token", headers={"Origin": ALLOWED_ORIGIN})
    finally:
        _clear_test_overrides()

    assert response.status_code == 503


def test_realtime_token_is_model_and_origin_restricted(monkeypatch):
    _authorize_test_user()
    monkeypatch.setattr(settings, "DECART_API_KEY", "server-secret")

    class MockResponse:
        is_success = True

        @staticmethod
        def json():
            return {"apiKey": "short-lived-client-token", "expiresAt": "2030-01-01T00:05:00Z"}

    class MockAsyncClient:
        def __init__(self, timeout):
            assert timeout == 10.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, headers, json):
            assert url == "https://api.decart.ai/v1/client/tokens"
            assert headers == {"X-API-KEY": "server-secret"}
            assert json == {
                "expiresIn": 300,
                "allowedModels": ["lucy-vton-3.6"],
                "allowedOrigins": [ALLOWED_ORIGIN],
            }
            return MockResponse()

    try:
        with patch("app.v1.endpoints.realtime_token.httpx.AsyncClient", MockAsyncClient):
            response = client.post("/api/realtime-token", headers={"Origin": ALLOWED_ORIGIN})
    finally:
        _clear_test_overrides()

    assert response.status_code == 200
    assert response.json() == {
        "apiKey": "short-lived-client-token",
        "expiresAt": "2030-01-01T00:05:00Z",
    }


def test_realtime_token_rejects_unconfigured_origin(monkeypatch):
    _authorize_test_user()
    monkeypatch.setattr(settings, "DECART_API_KEY", "server-secret")
    try:
        response = client.post("/api/realtime-token", headers={"Origin": "https://untrusted.example"})
    finally:
        _clear_test_overrides()

    assert response.status_code == 403
