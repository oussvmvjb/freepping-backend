import asyncio
from datetime import datetime, timezone
import logging
import os
import re
from typing import Dict, Optional
import uuid

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.trellis.base import Base3DGeneratorService
from app.services.trellis.service import Trellis2Service

logger = logging.getLogger(__name__)

SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")


class TrellisJob(BaseModel):
    job_id: str
    status: str = Field(default="queued")  # queued | processing | completed | failed
    progress: int = Field(default=0)
    message: str = Field(default="Job queued for processing")
    model_url: Optional[str] = None
    status_url: str
    error: Optional[str] = None
    created_at: str
    updated_at: str

    # Internal paths (excluded from public serialization)
    temp_upload_path: Optional[str] = Field(default=None, exclude=True)
    output_glb_path: Optional[str] = Field(default=None, exclude=True)


class TrellisJobManager:
    """
    Manages generation job lifecycles, background execution, and safe local storage.
    Includes concurrency limiting to avoid overloading Hugging Face Spaces.
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        generator_service: Optional[Base3DGeneratorService] = None,
        max_concurrent_jobs: Optional[int] = None,
    ):
        self.storage_dir = os.path.abspath(storage_dir or settings.STORAGE_DIR)
        self.models_dir = os.path.join(self.storage_dir, "models")
        self.temp_dir = os.path.join(self.storage_dir, "temp_uploads")

        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        self.service = generator_service or Trellis2Service()
        self.max_concurrent_jobs = max_concurrent_jobs or settings.TRELLIS_MAX_CONCURRENT_JOBS
        self._semaphore = asyncio.Semaphore(self.max_concurrent_jobs)
        self._jobs: Dict[str, TrellisJob] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def validate_id(self, job_id: str) -> bool:
        """Validate that a job_id does not contain path traversal characters or illegal syntax."""
        return bool(SAFE_ID_REGEX.match(job_id))

    def get_job(self, job_id: str) -> Optional[TrellisJob]:
        """Lookup a job by ID."""
        if not self.validate_id(job_id):
            return None
        return self._jobs.get(job_id)

    def get_active_job_count(self) -> int:
        """Count jobs currently queued or actively processing."""
        return sum(1 for j in self._jobs.values() if j.status in ("queued", "processing"))

    def create_job(
        self,
        image_bytes: bytes,
        original_filename: str,
        seed: Optional[int] = None,
        resolution: str = "1024",
    ) -> TrellisJob:
        """
        Create a new 3D generation job, save upload to disk, and launch background worker.
        """
        job_id = uuid.uuid4().hex
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"

        temp_filename = f"{job_id}{ext}"
        temp_path = os.path.join(self.temp_dir, temp_filename)

        with open(temp_path, "wb") as f:
            f.write(image_bytes)

        output_glb_path = os.path.join(self.models_dir, f"{job_id}.glb")
        now_iso = datetime.now(timezone.utc).isoformat()

        job = TrellisJob(
            job_id=job_id,
            status="queued",
            progress=0,
            message="Job received and queued for 3D generation",
            status_url=f"/api/generate-3d/{job_id}",
            model_url=None,
            created_at=now_iso,
            updated_at=now_iso,
            temp_upload_path=temp_path,
            output_glb_path=output_glb_path,
        )
        self._jobs[job_id] = job

        # Launch background execution task
        task = asyncio.create_task(self._process_job(job_id, seed, resolution))
        self._tasks[job_id] = task

        return job

    async def _process_job(self, job_id: str, seed: Optional[int], resolution: str) -> None:
        """Background worker that waits on concurrency semaphore and executes generation."""
        job = self._jobs.get(job_id)
        if not job:
            return

        async with self._semaphore:
            job.status = "processing"
            job.progress = 10
            job.message = "Acquired generation slot; initializing Hugging Face Space pipeline..."
            job.updated_at = datetime.now(timezone.utc).isoformat()

            def progress_hook(pct: int, msg: str) -> None:
                job.progress = pct
                job.message = msg
                job.updated_at = datetime.now(timezone.utc).isoformat()

            try:
                # Run the blocking Gradio generation in a worker thread so the event loop is never blocked
                await asyncio.to_thread(
                    self.service.generate_3d_glb,
                    image_path=job.temp_upload_path,
                    output_glb_path=job.output_glb_path,
                    seed=seed,
                    resolution=resolution,
                    progress_callback=progress_hook,
                )

                job.status = "completed"
                job.progress = 100
                job.message = "3D model generated and exported successfully"
                job.model_url = f"/api/generate-3d/{job_id}/model"
                job.updated_at = datetime.now(timezone.utc).isoformat()
                logger.info("Job %s completed successfully: %s", job_id, job.output_glb_path)

            except Exception as e:
                logger.error("Job %s failed: %s", job_id, e)
                job.status = "failed"
                job.progress = 0
                job.error = str(e)
                job.message = f"Generation failed: {str(e)}"
                job.updated_at = datetime.now(timezone.utc).isoformat()

            finally:
                # Clean up uploaded image safely
                if job.temp_upload_path and os.path.exists(job.temp_upload_path):
                    try:
                        os.remove(job.temp_upload_path)
                    except Exception as clean_err:
                        logger.warning("Could not remove temp file %s: %s", job.temp_upload_path, clean_err)

    async def wait_for_job(self, job_id: str, timeout: Optional[float] = None) -> Optional[TrellisJob]:
        """Wait for a job to reach a terminal state (completed or failed). No timeout when timeout=None."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        while True:
            if job.status in ("completed", "failed"):
                return job
            await asyncio.sleep(0.5)

    def resolve_model_file(self, job_id: str) -> Optional[str]:
        """
        Safely resolve the filesystem path to a generated GLB model,
        ensuring strict prevention of path traversal attacks.
        """
        if not self.validate_id(job_id):
            return None

        candidate_path = os.path.abspath(os.path.join(self.models_dir, f"{job_id}.glb"))

        # Verify candidate path is strictly inside self.models_dir
        try:
            if os.path.commonpath([candidate_path, self.models_dir]) != self.models_dir:
                return None
        except ValueError:
            return None

        if not os.path.isfile(candidate_path):
            return None

        return candidate_path

    def list_stored_models(self) -> list:
        """
        Scan storage/models directory and return metadata for all valid generated 3D GLB files.
        Sorted newest first.
        """
        import glob
        models = []
        pattern = os.path.join(self.models_dir, "*.glb")
        for file_path in glob.glob(pattern):
            try:
                size_bytes = os.path.getsize(file_path)
                # Filter out empty or test dummy files (< 1KB)
                if size_bytes < 1024:
                    continue
                filename = os.path.basename(file_path)
                job_id = os.path.splitext(filename)[0]
                mtime = os.path.getmtime(file_path)
                created_iso = datetime.fromtimestamp(mtime, timezone.utc).isoformat()
                models.append({
                    "job_id": job_id,
                    "filename": f"clothing_model_{job_id[:8]}.glb",
                    "size_bytes": size_bytes,
                    "size_mb": round(size_bytes / (1024 * 1024), 2),
                    "created_at": created_iso,
                    "model_url": f"/api/generate-3d/{job_id}/model"
                })
            except Exception as e:
                logger.warning("Error reading model file %s: %s", file_path, e)

        # Sort newest first
        models.sort(key=lambda m: m["created_at"], reverse=True)
        return models


# Global default manager instance
trellis_job_manager = TrellisJobManager()
