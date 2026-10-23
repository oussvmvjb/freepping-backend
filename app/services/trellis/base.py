from abc import ABC, abstractmethod
from typing import Optional, Callable


class Base3DGeneratorService(ABC):
    """
    Abstract interface for 3D model generation providers.
    Ensures modularity so alternative providers (e.g. Tripo3D, Meshy) can be plugged in easily.
    """

    @abstractmethod
    def generate_3d_glb(
        self,
        image_path: str,
        output_glb_path: str,
        seed: Optional[int] = None,
        resolution: str = "1024",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """
        Generate a 3D model in GLB format from an input image.

        Args:
            image_path: Path to the validated local input image.
            output_glb_path: Destination path where the resulting .glb will be stored.
            seed: Random seed or None for random generation.
            resolution: Resolution preset ('512', '1024', or '1536').
            progress_callback: Optional callback taking (progress_pct: int, status_message: str).

        Returns:
            str: Path to the generated .glb file.
        """
        pass
