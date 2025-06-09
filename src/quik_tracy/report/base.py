import abc
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TracyReportBase:
    """Base class for report generation strategies."""

    path: Path = Path.cwd()

    @abc.abstractmethod
    def report(self, csv_path: Path) -> Path:
        raise NotImplementedError("Subclasses must implement this method.")
