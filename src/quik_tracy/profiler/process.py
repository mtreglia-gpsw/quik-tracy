import logging
from pathlib import Path

from ..builders import api
from ..tools.process import ProcessRunner
from .base import TracyProfilerBase

log = logging.getLogger(__name__)


class TracyProfilerProcess(TracyProfilerBase):
    """Strategy that opens Tracy trace files using the tracy-profiler executable."""

    def profile(self, tracy_path: Path | None) -> bool:
        """Open Tracy trace file in the profiler using the tracy-profiler executable."""
        if not self.is_available():
            raise RuntimeError("tracy-profiler executable not found")

        if tracy_path is not None and not tracy_path.exists():
            raise RuntimeError(f"Tracy trace file not found: {tracy_path}")

        cmd = [str(TracyProfilerProcess.get_executable_path())]
        if tracy_path is not None:
            # Open trace file mode
            cmd.append(str(tracy_path))
            log.debug(f"Running Tracy profiler for file: {tracy_path}")
        else:
            # Live connection mode
            cmd.extend(["-a", self.host, "-p", str(self.port)])
            log.debug(f"Running Tracy profiler for live connection: {self.host}:{self.port}")

        log.debug(f"Running Tracy profiler: {' '.join(cmd)}")
        runner = ProcessRunner()
        # Start profiler in background and return immediately
        runner.run_background(cmd, suppress_output=True)
        if tracy_path is not None:
            log.debug(f"Tracy profiler launched successfully for file: {tracy_path}")
        else:
            log.debug(f"Tracy profiler launched successfully for live connection: {self.host}:{self.port}")
        return True

    @staticmethod
    def is_available() -> bool:
        """Check if the tracy-capture executable is available in PATH."""
        return TracyProfilerProcess.get_executable_path() is not None

    @staticmethod
    def get_executable_path() -> Path | None:
        """Get the path to the tracy-capture executable."""
        return api.get_executable_path("tracy-profiler")
