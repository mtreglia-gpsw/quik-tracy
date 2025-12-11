from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from ..export.process import TracyExportCSVProcess
from ..export.container import TracyExportCSVDocker
from .base import TracyReportBase

logger = logging.getLogger(__name__)


@dataclass
class TracyReportCSV(TracyReportBase):
    """Export .tracy files to CSV format."""

    def report(self, trace_path: Path) -> Path:
        """Export a .tracy file to CSV and return the path to the CSV file.

        If already a CSV, returns the path unchanged.
        """
        if trace_path.suffix == ".csv":
            return trace_path

        logger.info(f"Exporting {trace_path} to CSV...")

        # Try local process first, then Docker
        if TracyExportCSVProcess.is_available():
            exporter = TracyExportCSVProcess(self.path)
        elif TracyExportCSVDocker.is_available():
            exporter = TracyExportCSVDocker(self.path)
        else:
            raise RuntimeError("No available Tracy export method found (process or Docker).")

        csv_path = exporter.export(trace_path)
        logger.info(f"CSV exported to {csv_path}")
        return csv_path
