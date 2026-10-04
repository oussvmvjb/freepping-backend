import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "docs_url" in data


def test_health_check_endpoint():
    async def mock_db():
        class MockSession:
            async def execute(self, stmt):
                return True
        yield MockSession()

    app.dependency_overrides[get_db] = mock_db
    try:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "database" in data
    finally:
        app.dependency_overrides.clear()
