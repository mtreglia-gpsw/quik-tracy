import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass
class TracyCompareBase(abc.ABC):
    """Base class for Tracy trace comparison strategies."""

    path: Path = Path.cwd()

    @abc.abstractmethod
    def compare(self, trace_paths: Sequence[Path], name: str | None = None) -> Path:
        """Compare multiple Tracy trace/CSV files and return path to comparison report."""
        raise NotImplementedError("Subclasses must implement this method.")
