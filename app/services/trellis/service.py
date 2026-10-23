import logging
import os
import shutil
import time
from typing import Any, Callable, Optional, Tuple

from app.core.config import settings
from app.services.trellis.base import Base3DGeneratorService

logger = logging.getLogger(__name__)


class TrellisGenerationError(Exception):
    """Raised when 3D model generation fails."""
    pass


class TrellisUnavailableError(TrellisGenerationError):
    """Raised when the Hugging Face Space is offline, overloaded, or unreachable."""
    pass


class Trellis2Service(Base3DGeneratorService):
    """
    Implementation of 3D generation using Microsoft's TRELLIS.2 Hugging Face Space.
    Coordinates image preprocessing, latent 3D sampling, and GLB mesh extraction.
    """

    def __init__(
        self,
        space_name: Optional[str] = None,
        hf_token: Optional[str] = None,
        client_factory: Optional[Callable[[str, Optional[str]], Any]] = None,
    ):
        self.space_name = space_name or settings.TRELLIS_SPACE
        self.hf_token = hf_token or settings.HF_TOKEN
        self._client_factory = client_factory

    def _get_client(self) -> Any:
        """
        Instantiate a Gradio Client connected to the TRELLIS.2 Space.
        NOTE: gradio_client uses `token=` (not `hf_token=`) as the auth kwarg.
        """
        if self._client_factory:
            return self._client_factory(self.space_name, self.hf_token)

        try:
            from gradio_client import Client
            # Use `token=` — correct kwarg for gradio_client (hf_token= does not exist)
            hf_token = self.hf_token if self.hf_token and self.hf_token.strip() else None
            client = Client(self.space_name, token=hf_token)
            # TRELLIS.2 requires a session handshake before any predict calls
            try:
                client.predict(api_name="/start_session")
                logger.info("TRELLIS.2 session started successfully")
            except Exception as sess_err:
                logger.warning("start_session call failed (non-fatal): %s", sess_err)
            return client
        except Exception as e:
            sanitized = self._sanitize_error(str(e))
            logger.error("Failed to connect to Hugging Face Space %s: %s", self.space_name, sanitized)
            raise TrellisUnavailableError(
                f"Cannot connect to 3D generation service ({self.space_name}). "
                f"The Hugging Face Space may be offline or sleeping. Detail: {sanitized}"
            ) from e

    def _sanitize_error(self, message: str) -> str:
        """Strip sensitive credentials like Hugging Face tokens from error messages."""
        if self.hf_token and self.hf_token.strip():
            message = message.replace(self.hf_token.strip(), "[REDACTED_HF_TOKEN]")
        return message

    def _extract_file_path(self, result: Any) -> str:
        """Extract a local filesystem path from a Gradio return value (dict or string)."""
        if isinstance(result, dict) and "path" in result:
            return str(result["path"])
        if isinstance(result, (list, tuple)) and len(result) > 0:
            return self._extract_file_path(result[0])
        return str(result)

    def generate_3d_glb(
        self,
        image_path: str,
        output_glb_path: str,
        seed: Optional[int] = None,
        resolution: str = "1024",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """
        Execute the complete TRELLIS.2 pipeline:
        1. Preprocess input image (remove background / center).
        2. Sample 3D latents via /image_to_3d.
        3. Extract and decimate GLB mesh via /extract_glb.
        4. Save to destination output_glb_path.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Source image not found: {image_path}")

        from gradio_client import handle_file

        def update_progress(pct: int, msg: str) -> None:
            if progress_callback:
                try:
                    progress_callback(pct, msg)
                except Exception as cb_err:
                    logger.warning("Progress callback failed: %s", cb_err)

        update_progress(10, "Connecting to Microsoft TRELLIS.2 Hugging Face Space...")
        client = self._get_client()

        # Step 1: Preprocess Image
        update_progress(25, "Preprocessing image and removing background...")
        try:
            logger.info("Executing /preprocess_image for %s", image_path)
            preprocessed_res = client.predict(
                input=handle_file(image_path),
                api_name="/preprocess_image",
            )
            preprocessed_path = self._extract_file_path(preprocessed_res)
            logger.info("Image preprocessed successfully: %s", preprocessed_path)
        except Exception as e:
            sanitized = self._sanitize_error(str(e))
            logger.warning("Preprocess step failed, attempting direct image input: %s", sanitized)
            preprocessed_path = image_path

        # Step 2: Seed selection
        if seed is None:
            try:
                seed_val = client.predict(
                    randomize_seed=True,
                    seed=0,
                    api_name="/get_seed",
                )
                chosen_seed = int(seed_val) if isinstance(seed_val, (int, float)) else 42
            except Exception:
                chosen_seed = 42
        else:
            chosen_seed = seed

        # Step 3: Run Image to 3D latent generation
        # NOTE: /image_to_3d returns an HTML preview string — the actual 3D data
        # is stored server-side in the session. Result is intentionally not used.
        update_progress(50, "Generating 3D sparse structure and texture latents...")
        valid_resolutions = ["512", "1024", "1536"]
        res_choice = resolution if resolution in valid_resolutions else "1024"

        try:
            logger.info("Executing /image_to_3d with seed=%d, resolution=%s", chosen_seed, res_choice)
            image_to_3d_result = client.predict(
                image=handle_file(preprocessed_path),
                seed=float(chosen_seed),
                resolution=res_choice,
                ss_guidance_strength=7.5,
                ss_guidance_rescale=0.7,
                ss_sampling_steps=12,
                ss_rescale_t=5.0,
                shape_slat_guidance_strength=7.5,
                shape_slat_guidance_rescale=0.5,
                shape_slat_sampling_steps=12,
                shape_slat_rescale_t=3.0,
                tex_slat_guidance_strength=1.0,
                tex_slat_guidance_rescale=0.0,
                tex_slat_sampling_steps=12,
                tex_slat_rescale_t=3.0,
                api_name="/image_to_3d",
            )
            # Returns an HTML string (3D preview widget) — this is expected
            logger.info("3D latents generated successfully in session state (result type: %s)", type(image_to_3d_result).__name__)
        except Exception as e:
            sanitized = self._sanitize_error(str(e))
            logger.error("3D latent generation failed: %s", sanitized)
            if "queue" in sanitized.lower() or "timeout" in sanitized.lower():
                raise TrellisUnavailableError(
                    "The Hugging Face GPU queue timed out. Please try again in a few moments."
                ) from e
            if "gpu" in sanitized.lower() or "quota" in sanitized.lower() or "rate limit" in sanitized.lower():
                raise TrellisUnavailableError(
                    "Hugging Face ZeroGPU quota reached or rate limit exceeded. "
                    "Please use a valid HF_TOKEN with ZeroGPU access."
                ) from e
            raise TrellisGenerationError(f"3D generation failed: {sanitized}") from e

        # Step 4: Extract GLB mesh
        # /extract_glb returns a tuple: (extracted_glb_filepath, download_glb_filepath)
        update_progress(80, "Extracting and decimating 3D GLB mesh...")
        try:
            logger.info("Executing /extract_glb")
            extract_res = client.predict(
                decimation_target=300000,
                texture_size=2048,
                api_name="/extract_glb",
            )
            # extract_res is a tuple (Model3d filepath, Downloadbutton filepath)
            # Take the first element (the actual GLB filepath)
            if isinstance(extract_res, (list, tuple)) and len(extract_res) >= 1:
                raw_glb_path = self._extract_file_path(extract_res[0])
            else:
                raw_glb_path = self._extract_file_path(extract_res)
            logger.info("GLB extracted to temp file: %s", raw_glb_path)
        except Exception as e:
            sanitized = self._sanitize_error(str(e))
            logger.error("GLB extraction failed: %s", sanitized)
            raise TrellisGenerationError(f"Mesh extraction failed: {sanitized}") from e

        if not os.path.exists(raw_glb_path):
            raise TrellisGenerationError(f"Extracted GLB file not found on disk: {raw_glb_path}")

        # Step 5: Save to target destination
        update_progress(95, "Finalizing and storing 3D model...")
        os.makedirs(os.path.dirname(os.path.abspath(output_glb_path)), exist_ok=True)
        shutil.copyfile(raw_glb_path, output_glb_path)
        update_progress(100, "Generation complete")
        logger.info("Saved final GLB to %s", output_glb_path)

        return output_glb_path
