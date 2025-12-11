from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Sequence

from ..export.process import TracyExportCSVProcess
from ..export.container import TracyExportCSVDocker
from .base import TracyCompareBase

logger = logging.getLogger(__name__)


@dataclass
class TracyCompareCSV(TracyCompareBase):
    """Ensure all input files are CSV format before comparison."""

    def compare(self, trace_paths: Sequence[Path], name: str | None = None) -> list[Path]:
        """Convert any .tracy files to CSV and return list of CSV paths.

        If already CSV, returns unchanged. Subclasses chain through this.
        """
        csv_paths: list[Path] = []
        for trace_path in trace_paths:
            csv_paths.append(self._ensure_csv(trace_path))
        return csv_paths

    def _ensure_csv(self, trace_path: Path) -> Path:
        """Convert a single file to CSV if needed."""
        if trace_path.suffix == ".csv":
            return trace_path

        logger.info(f"Exporting {trace_path.name} to CSV...")

        if TracyExportCSVProcess.is_available():
            exporter = TracyExportCSVProcess(self.path)
        elif TracyExportCSVDocker.is_available():
            exporter = TracyExportCSVDocker(self.path)
        else:
            raise RuntimeError("No available Tracy export method found (process or Docker).")

        return exporter.export(trace_path)
