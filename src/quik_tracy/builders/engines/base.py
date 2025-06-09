from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class TracyBuilderBase(ABC):
    """
    Abstract base class for Tracy tool builders.

    Follows the same pattern as TracyCaptureBase, TracyExportBase, etc.
    """

    tool_name: str
    branch: str = "master"
    ref: str = "7e833e7ddce8bb36476b0452b2823c000dfad02b"

    @abstractmethod
    def build(self) -> bool:
        """
        Build the Tracy tool and return the path to the built executable.

        Returns:
            Path: Path to the built executable

        Raises:
            RuntimeError: If the build fails
        """
        pass

    @staticmethod
    @abstractmethod
    def is_available() -> bool:
        """
        Check if the builder is available (e.g., docker installed, cmake available).

        Returns:
            bool: True if the builder can be used
        """
        pass

    def _get_path(self, folder_name: str) -> Path:
        """Get shared build path for Tracy tools."""
        build_path = Path.home() / ".quik-tracy" / folder_name
        build_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Shared {folder_name} path for Tracy tools: {build_path}")
        return build_path
