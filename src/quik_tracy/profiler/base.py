import abc
from dataclasses import dataclass
import logging
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class TracyProfilerBase(abc.ABC):
    """Strategy interface that opens a *.tracy* file with the Tracy profiler."""

    host: str = "localhost"
    port: int = 8086
    path: Path = Path.cwd()

    @abc.abstractmethod
    def profile(self, tracy_path: Path | None) -> bool:
        """Open Tracy trace file in the profiler and return success status."""
        raise NotImplementedError

    @staticmethod
    @abc.abstractmethod
    def is_available() -> bool:
        """Check if the profiler strategy is available."""
        raise NotImplementedError
