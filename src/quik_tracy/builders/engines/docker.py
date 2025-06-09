from dataclasses import dataclass
import logging
from pathlib import Path

from ...tools import Docker
from .base import TracyBuilderBase

logger = logging.getLogger(__name__)


@dataclass
class TracyBuilderDocker(TracyBuilderBase):
    """Docker image builder using Dockerfiles from dockers folder."""

    def build(self) -> bool:
        if not self.is_available():
            raise RuntimeError("Docker is not available")

        try:
            with Docker() as docker:
                # Build base image first if needed
                if not self._build_image(docker, "tracy-base", "tracy-base"):
                    raise RuntimeError("Failed to build base Tracy image")

                # Build the specific tool image
                if not self._build_image(docker, self.tool_name, self.tool_name):
                    raise RuntimeError(f"Failed to build {self.tool_name} image")

                logger.info(f"Successfully built Tracy {self.tool_name} image")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to build {self.tool_name}: {e}")
            raise e
            return False

    @staticmethod
    def is_available() -> bool:
        """Check if Docker is available."""
        try:
            with Docker():
                return True
            return False
        except Exception:
            return False

    def _build_image(self, docker: Docker, image_type: str, tag: str) -> bool:
        """Build an image if it doesn't already exist."""
        # Check if image already exists
        if docker.get_image_info(tag) is not None:
            logger.debug(f"Image {tag} already exists")
            return True

        logger.info(f"Building {tag} image")
        dockerfile_path = self._get_dockerfile_path(image_type)

        if not dockerfile_path.exists():
            logger.error(f"Dockerfile not found for {image_type}: {dockerfile_path}")
            return False

        # Unified build args - all images get branch and ref
        build_args = {
            "TRACY_BRANCH": self.branch,
            "TRACY_REF": self.ref,
        }

        result = docker.build(
            path=dockerfile_path.parent,
            tag=tag,
            dockerfile=dockerfile_path.name,
            build_args=build_args,
        )

        if not result:
            logger.error(f"Docker build failed for {tag}")
            return False

        return True

    def _get_dockerfile_path(self, image_type: str) -> Path:
        """Get the path to the Dockerfile for the given image type."""
        dockers_dir = Path(__file__).parent.parent / "docker"
        # Extract tool name without tracy- prefix for dockerfile naming
        assert image_type.startswith("tracy-"), "Image type must start with 'tracy-'"
        tool_suffix = image_type.replace("tracy-", "")
        dockerfile_name = f"Dockerfile.{tool_suffix}"
        return dockers_dir / dockerfile_name
