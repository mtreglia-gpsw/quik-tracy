import abc
from dataclasses import dataclass
import logging
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class TracyExportCSVBase(abc.ABC):
    """Strategy interface that converts a *.tracy* → *.csv*."""

    path: Path = Path.cwd()

    @abc.abstractmethod
    def export(self, tracy_path: Path) -> Path:
        raise NotImplementedError

    @staticmethod
    @abc.abstractmethod
    def is_available() -> bool:
        """Check if the capture strategy is available."""
        raise NotImplementedError
