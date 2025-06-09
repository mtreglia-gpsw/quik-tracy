from dataclasses import dataclass
import logging
from pathlib import Path

from ..tools.process import ProcessRunner
from ..builders import api
from .base import TracyExportCSVBase

log = logging.getLogger(__name__)


@dataclass
class TracyExportCSVProcess(TracyExportCSVBase):
    """Strategy interface that converts a *.tracy* → *.csv*."""

    def export(self, tracy_path: Path) -> Path:
        """Export Tracy trace file to CSV format using the tracy-csvexport executable."""
        if not self.is_available():
            raise RuntimeError("tracy-csvexport executable not found")

        executable_path = api.get_executable_path("tracy-csvexport")
        if not executable_path:
            raise RuntimeError("tracy-csvexport executable not found in PATH")

        csv_path = tracy_path.with_suffix(".csv")
        cmd = [str(TracyExportCSVProcess.get_executable_path()), str(tracy_path)]

        log.debug(f"Running Tracy CSV export: {' '.join(cmd)}")
        runner = ProcessRunner()
        result = runner.run_to_file(cmd, csv_path)

        if result.stderr:
            log.warning("%s", result.stderr)

        if not csv_path.exists() or csv_path.stat().st_size == 0:
            raise RuntimeError(f"Tracy CSV export failed to create valid output file: {csv_path}")

        log.debug(f"Tracy CSV export completed successfully: {csv_path}")
        return csv_path.resolve()

    @staticmethod
    def is_available() -> bool:
        """Check if the tracy-capture executable is available in PATH."""
        return TracyExportCSVProcess.get_executable_path() is not None

    @staticmethod
    def get_executable_path() -> Path | None:
        """Get the path to the tracy-capture executable."""
        return api.get_executable_path("tracy-csvexport")
