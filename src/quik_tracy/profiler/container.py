import logging
from pathlib import Path
import platform

from rich.pretty import pretty_repr

from ..tools import ContainerConfig, Docker
from .base import TracyProfilerBase

log = logging.getLogger(__name__)


class TracyProfilerDocker(TracyProfilerBase):
    """Docker implementation using *tracy-profiler* web interface."""

    host: str = "host.docker.internal" if platform.system() != "Linux" else "localhost"

    def profile(self, tracy_path: Path | None) -> bool:
        """Open Tracy trace file using the tracy-profiler Docker container web interface."""
        if not self.is_available():
            raise RuntimeError("tracy-profiler Docker image is not available")

        if tracy_path is not None and not tracy_path.exists():
            raise RuntimeError(f"Tracy trace file not found: {tracy_path}")

        volume_path = str(self.path) if tracy_path is None else str(tracy_path.parent)

        cfg = ContainerConfig(
            image_tag="tracy-profiler",
            command=[],
            volumes={str(volume_path): {"bind": "/data", "mode": "ro"}},
            ports={"8000/tcp": 8000},
            detach=True,
        )

        log.debug("Starting tracy-profiler web interface with config: %s", cfg)
        with Docker() as dk:
            log.info("Starting tracy-profiler web interface...")
            container_id = dk.run(cfg)
            if not container_id:
                raise RuntimeError("tracy-profiler container failed to start")

            log.info("Tracy profiler web interface available at http://localhost:8000")
            log.info(f"Container ID: {container_id}")
            return True
        return False

    @staticmethod
    def is_available() -> bool:
        """Check if the tracy-profiler Docker image is available."""
        with Docker() as dk:
            try:
                image_info = dk.get_image_info("tracy-profiler")
                log.debug("tracy-profiler image info: %s", pretty_repr(image_info))
                return image_info is not None
            except Exception as exc:
                log.debug("tracy-profiler image not available: %s", exc)
        return False
