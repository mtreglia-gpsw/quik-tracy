import logging
from pathlib import Path

from ..tools.process import ProcessRunner
from ..builders import api
from .base import TracyCaptureBase

log = logging.getLogger(__name__)


class TracyCaptureProcess(TracyCaptureBase):
    def capture(self, trace_name: str) -> Path:
        """Capture Tracy profiling data using the tracy-capture executable."""
        if not self.is_available():
            raise RuntimeError("tracy-capture executable not found")

        self.path.mkdir(parents=True, exist_ok=True)
        trace_path = self.path / trace_name

        cmd = [
            str(TracyCaptureProcess.get_executable_path()),
            "-a",
            self.host,
            "-p",
            str(self.port),
            "-o",
            str(trace_path),
        ]

        log.debug(f"Running Tracy capture: {' '.join(cmd)}")
        runner = ProcessRunner()
        result = runner.run_streaming(cmd)
        log.debug(f"Tracy capture stdout: {result.stdout}")
        if result.stderr:
            log.warning(f"Tracy capture stderr: {result.stderr}")

        if not trace_path.exists():
            raise RuntimeError(f"Tracy capture completed but output file not found: {trace_path}")

        log.debug(f"Tracy capture completed successfully: {trace_path}")
        return trace_path.resolve()

    @staticmethod
    def is_available() -> bool:
        """Check if the tracy-capture executable is available in PATH."""
        return TracyCaptureProcess.get_executable_path() is not None

    @staticmethod
    def get_executable_path() -> Path | None:
        """Get the path to the tracy-capture executable."""
        return api.get_executable_path("tracy-capture")
