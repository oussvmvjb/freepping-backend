import io
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image

from app.core.config import settings
from app.services.trellis.job_manager import trellis_job_manager

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/pjpeg",
    "image/webp",
}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def validate_image_bytes(contents: bytes, filename: str, content_type: Optional[str]) -> str:
    """
    Validate that uploaded file is within allowed size and is a valid image (PNG, JPEG, WebP).
    Returns normalized extension (e.g. '.png').
    """
    max_bytes = settings.TRELLIS_MAX_FILE_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded file exceeds maximum limit of {settings.TRELLIS_MAX_FILE_SIZE_MB}MB.",
        )

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Validate filename extension
    ext = os.path.splitext(filename)[1].lower() if filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )

    # Validate image bytes integrity using PIL
    try:
        with Image.open(io.BytesIO(contents)) as img:
            img.verify()
            format_name = (img.format or "").upper()
            if format_name not in ("PNG", "JPEG", "WEBP"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid image format '{format_name}'. Allowed formats: PNG, JPEG, WebP.",
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a readable image.",
        ) from e

    return ext


@router.get("/health", summary="Health Check & Trellis Status")
async def health_check() -> Dict[str, Any]:
    """
    Endpoint A:
    Returns service health and configuration status for Microsoft TRELLIS.2 integration.
    """
    hf_configured = bool(settings.HF_TOKEN and settings.HF_TOKEN.strip() and settings.HF_TOKEN != "your_hugging_face_token")
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "trellis": {
            "configured": True,
            "space": settings.TRELLIS_SPACE,
            "hf_token_configured": hf_configured,
            "max_concurrent_jobs": settings.TRELLIS_MAX_CONCURRENT_JOBS,
            "max_file_size_mb": settings.TRELLIS_MAX_FILE_SIZE_MB,
            "active_jobs": trellis_job_manager.get_active_job_count(),
        },
    }


@router.post(
    "/generate-3d",
    summary="Generate 3D Model from Image",
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_3d(
    response: Response,
    image: UploadFile = File(..., description="Clothing photo (PNG, JPEG, WebP)"),
    resolution: str = Query("1024", pattern="^(512|1024|1536)$", description="Latent resolution"),
    seed: Optional[int] = Query(None, description="Optional seed for reproducibility"),
    wait: bool = Query(False, description="If true, wait for generation to finish before returning"),
) -> Dict[str, Any]:
    """
    Endpoint B:
    Accepts multipart/form-data image upload.
    Validates file, queues 3D generation with Microsoft TRELLIS.2,
    and returns job status and model URL.
    """
    filename = image.filename or "upload.png"
    contents = await image.read()

    validate_image_bytes(contents, filename, image.content_type)

    job = trellis_job_manager.create_job(
        image_bytes=contents,
        original_filename=filename,
        seed=seed,
        resolution=resolution,
    )

    if wait:
        # Wait up to TRELLIS_TIMEOUT_SECONDS
        finished_job = await trellis_job_manager.wait_for_job(
            job.job_id, timeout=float(settings.TRELLIS_TIMEOUT_SECONDS)
        )
        if finished_job:
            job = finished_job

        if job.status == "failed":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=job.error or "3D model generation failed on Hugging Face Space.",
            )

    if job.status == "completed":
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = status.HTTP_202_ACCEPTED

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "status_url": job.status_url,
        "model_url": job.model_url,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("/generate-3d/models", summary="List All Generated 3D Models")
async def list_generated_models():
    """
    Returns a list of all successfully generated 3D GLB models stored on the server.
    """
    models = trellis_job_manager.list_stored_models()
    return {
        "count": len(models),
        "models": models
    }


@router.get("/generate-3d/{job_id}", summary="Get 3D Generation Status")
async def get_generation_status(job_id: str) -> Dict[str, Any]:
    """
    Endpoint C:
    Reports the status of an ongoing or completed 3D generation job.
    """
    job = trellis_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "model_url": job.model_url,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("/generate-3d/{job_id}/model", summary="Retrieve Generated 3D GLB Model")
async def get_generated_model(
    job_id: str,
    download: bool = Query(False, description="Force download attachment header"),
) -> FileResponse:
    """
    Endpoint D:
    Securely serves the generated .glb file for visualization in Three.js or download.
    Protected against path traversal attacks.
    """
    file_path = trellis_job_manager.resolve_model_file(job_id)
    if not file_path:
        # Check if job is still processing
        job = trellis_job_manager.get_job(job_id)
        if job and job.status in ("queued", "processing"):
            raise HTTPException(
                status_code=status.HTTP_425_TOO_EARLY,
                detail=f"Job '{job_id}' is still {job.status}. Model is not ready yet.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model for job '{job_id}' not found.",
        )

    filename = f"clothing_model_{job_id[:8]}.glb"
    disposition = "attachment" if download else "inline"

    return FileResponse(
        path=file_path,
        media_type="model/gltf-binary",
        filename=filename,
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
    )
