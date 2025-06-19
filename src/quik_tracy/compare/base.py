import abc
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class TracyCompareBase(abc.ABC):
    """Base class for Tracy trace comparison strategies."""

    path: Path = Path.cwd()

    @abc.abstractmethod
    def compare(self, csv_paths: List[Path]) -> Path:
        """Compare multiple Tracy CSV files and return path to comparison report."""
        raise NotImplementedError("Subclasses must implement this method.")
