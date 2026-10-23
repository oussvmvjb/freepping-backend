import io
import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services.trellis.job_manager import TrellisJobManager
from app.services.trellis.service import Trellis2Service, TrellisGenerationError

client = TestClient(app)


def create_test_image(format_name: str = "PNG", size: tuple = (32, 32)) -> bytes:
    """Helper to generate in-memory valid image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=(0, 255, 0))
    img.save(buf, format=format_name)
    return buf.getvalue()


def test_health_check_endpoint():
    """Verify GET /api/health and /api/v1/health report status and Trellis configuration."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "trellis" in data
    assert data["trellis"]["configured"] is True
    assert "space" in data["trellis"]
    assert "microsoft/TRELLIS.2" in data["trellis"]["space"]

    # Also test /api/v1/health
    response_v1 = client.get("/api/v1/health")
    assert response_v1.status_code == 200


def test_invalid_file_type_rejected():
    """Verify that non-image uploads (e.g., text, shell script) are rejected with 400."""
    fake_file = io.BytesIO(b"Hello world not an image")
    response = client.post(
        "/api/generate-3d",
        files={"image": ("malicious.txt", fake_file, "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"] or "Invalid image" in response.json()["detail"]


def test_oversized_upload_rejected(monkeypatch):
    """Verify that uploads exceeding TRELLIS_MAX_FILE_SIZE_MB return 413."""
    # Temporarily set limit to 1MB for the test
    from app.core.config import settings
    monkeypatch.setattr(settings, "TRELLIS_MAX_FILE_SIZE_MB", 1)

    # 1.5MB file
    huge_bytes = b"x" * (1500 * 1024)
    huge_file = io.BytesIO(huge_bytes)
    response = client.post(
        "/api/generate-3d",
        files={"image": ("oversized.png", huge_file, "image/png")},
    )
    assert response.status_code == 413
    assert "exceeds maximum limit" in response.json()["detail"]


def test_invalid_job_id_traversal():
    """Verify that path traversal attempts or malformed job IDs are rejected."""
    traversal_ids = ["../etc/passwd", "..\\boot.ini", "invalid/id", "../../secret"]
    for bad_id in traversal_ids:
        response = client.get(f"/api/generate-3d/{bad_id}")
        assert response.status_code in (400, 404)

        model_resp = client.get(f"/api/generate-3d/{bad_id}/model")
        assert model_resp.status_code in (400, 404)


def test_successful_generation_mocked(tmp_path):
    """Verify end-to-end flow with a mocked TRELLIS.2 service."""
    # Create a mock service that writes a fake .glb file
    class MockTrellisService:
        def generate_3d_glb(self, image_path, output_glb_path, seed=None, resolution="1024", progress_callback=None):
            if progress_callback:
                progress_callback(50, "Generating mock mesh...")
            os.makedirs(os.path.dirname(output_glb_path), exist_ok=True)
            with open(output_glb_path, "wb") as f:
                f.write(b"glTF mock binary model data")
            if progress_callback:
                progress_callback(100, "Done")
            return output_glb_path

    # Swap the service in the global job manager
    from app.services.trellis.job_manager import trellis_job_manager
    orig_service = trellis_job_manager.service
    trellis_job_manager.service = MockTrellisService()

    try:
        img_bytes = create_test_image("PNG")
        response = client.post(
            "/api/generate-3d?wait=true",
            files={"image": ("tshirt.png", io.BytesIO(img_bytes), "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["job_id"] is not None
        assert data["model_url"] is not None

        job_id = data["job_id"]

        # Check status endpoint
        status_resp = client.get(f"/api/generate-3d/{job_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "completed"

        # Check GLB download endpoint
        model_resp = client.get(f"/api/generate-3d/{job_id}/model")
        assert model_resp.status_code == 200
        assert model_resp.content == b"glTF mock binary model data"
        assert "model/gltf-binary" in model_resp.headers["content-type"]
    finally:
        trellis_job_manager.service = orig_service


def test_failed_generation_mocked():
    """Verify that Hugging Face generation errors are caught and surfaced cleanly."""
    class FailingTrellisService:
        def generate_3d_glb(self, image_path, output_glb_path, seed=None, resolution="1024", progress_callback=None):
            raise TrellisGenerationError("Hugging Face ZeroGPU quota exceeded.")

    from app.services.trellis.job_manager import trellis_job_manager
    orig_service = trellis_job_manager.service
    trellis_job_manager.service = FailingTrellisService()

    try:
        img_bytes = create_test_image("JPEG")
        response = client.post(
            "/api/generate-3d?wait=true",
            files={"image": ("jacket.jpg", io.BytesIO(img_bytes), "image/jpeg")},
        )
        assert response.status_code == 502
        assert "ZeroGPU quota exceeded" in response.json()["detail"]
    finally:
        trellis_job_manager.service = orig_service
