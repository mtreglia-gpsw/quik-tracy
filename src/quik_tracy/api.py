from datetime import datetime
from enum import Enum
import logging
from pathlib import Path
from typing import Sequence

from .capture import TracyCaptureDocker, TracyCaptureProcess
from .export import TracyExportCSVDocker, TracyExportCSVProcess
from .profiler import TracyProfilerDocker, TracyProfilerProcess
from .report import TracyReportHdf5, TracyReportHTML
from .compare import TracyCompareHdf5, TracyCompareHTML

log = logging.getLogger(__name__)


class RunMode(Enum):
    AUTO = "auto"
    LOCAL = "process"
    DOCKER = "docker"


class ReportMode(Enum):
    HDF5 = "hdf5"
    HTML = "html"


class CompareMode(Enum):
    HDF5 = "hdf5"
    HTML = "html"


def run_capture(
    name: str = "capture.tracy",
    host: str = "host.docker.internal",
    port: int = 8086,
    mode: RunMode = RunMode.AUTO,
    path: Path = Path.cwd(),
) -> Path:
    """Functional helper—runs a Tracy capture process and returns the path to the capture file."""
    log.debug(f"Starting Tracy capture with name: {name}, host: {host}, port: {port}, mode: {mode.value}")
    if mode == RunMode.AUTO:
        log.debug("Auto mode selected, checking available capture methods...")
        if TracyCaptureProcess.is_available():
            mode = RunMode.LOCAL
        elif TracyCaptureDocker.is_available():
            mode = RunMode.DOCKER
        else:
            raise RuntimeError("No available Tracy capture method found (process or Docker).")

    match mode:
        case RunMode.LOCAL:
            if host == "host.docker.internal":
                log.warning("Using 'host.docker.internal' with process mode may not work as expected. Falling back to localhost.")
                host = "localhost"
            return TracyCaptureProcess(host, port, path).capture(name)
        case RunMode.DOCKER:
            return TracyCaptureDocker(host, port, path).capture(name)
        case _:
            raise ValueError(f"Unsupported run mode: {mode}")


def run_export(trace_path: Path, mode: RunMode = RunMode.AUTO, path: Path = Path.cwd()) -> Path:
    """Functional helper—runs a Tracy export process and returns the path to the exported CSV file."""
    log.debug(f"Starting Tracy export for trace: {trace_path}, mode: {mode.value}")
    if mode == RunMode.AUTO:
        log.debug("Auto mode selected, checking available capture methods...")
        if TracyExportCSVProcess.is_available():
            mode = RunMode.LOCAL
        elif TracyExportCSVDocker.is_available():
            mode = RunMode.DOCKER
        else:
            raise RuntimeError("No available Tracy capture method found (process or Docker).")
    match mode:
        case RunMode.LOCAL:
            return TracyExportCSVProcess(path).export(trace_path)
        case RunMode.DOCKER:
            return TracyExportCSVDocker(path).export(trace_path)
        case _:
            raise ValueError(f"Unsupported run mode: {mode}")


def run_report(trace_path: Path, mode: ReportMode = ReportMode.HTML, path: Path = Path.cwd()) -> Path:
    """Functional helper—runs a Tracy report process and returns the path to the report file."""
    log.debug(f"Starting Tracy report for trace: {trace_path}, mode: {mode.value}")
    match mode:
        case ReportMode.HDF5:
            return TracyReportHdf5(path).report(trace_path)
        case ReportMode.HTML:
            return TracyReportHTML(path).report(trace_path)
        case _:
            raise ValueError(f"Unsupported report mode: {mode}")


def run_profiler(
    trace_path: Path | None = None,
    mode: RunMode = RunMode.AUTO,
    host: str = "host.docker.internal",
    port: int = 8086,
    path: Path = Path.cwd(),
) -> bool:
    """Functional helper—runs a Tracy profiler and returns success status."""
    log.debug(f"Starting Tracy profiler for trace: {trace_path}, mode: {mode.value}, host: {host}, port: {port}")
    if mode == RunMode.AUTO:
        log.debug("Auto mode selected, checking available profiler methods...")
        if TracyProfilerProcess.is_available():
            mode = RunMode.LOCAL
        elif TracyProfilerDocker.is_available():
            mode = RunMode.DOCKER
        else:
            raise RuntimeError("No available Tracy profiler method found (process or Docker).")
    match mode:
        case RunMode.LOCAL:
            if host == "host.docker.internal":
                log.warning("Using 'host.docker.internal' with process mode may not work as expected. Falling back to localhost.")
                host = "localhost"
            return TracyProfilerProcess(host, port, path).profile(trace_path)
        case RunMode.DOCKER:
            return TracyProfilerDocker(host, port, path).profile(trace_path)
        case _:
            raise ValueError(f"Unsupported run mode: {mode}")


def run_session(
    name: str = "session.tracy",
    host: str = "host.docker.internal",
    port: int = 8086,
    capture_mode: RunMode = RunMode.AUTO,
    export_mode: RunMode = RunMode.AUTO,
    report_mode: ReportMode = ReportMode.HTML,
    path: Path = Path.cwd(),
) -> tuple[Path, Path, Path]:
    """Functional helper—runs a complete Tracy session and returns the session result."""
    log.debug("Starting Tracy session")
    date = datetime.now().strftime("%Y.%m.%d_%H.%M.%S")
    session_path = path / f"tracy_session_{date}"
    session_path.mkdir(parents=True, exist_ok=True)
    trace_path = run_capture(name, host, port, capture_mode, session_path)
    csv_path = run_export(trace_path, export_mode, session_path)
    report_path = run_report(csv_path, report_mode, session_path)
    log.debug(f"Tracy session completed: trace={trace_path}, csv={csv_path}, report={report_path}")
    return trace_path, csv_path, report_path


def run_compare(
    trace_paths: Sequence[Path],
    mode: CompareMode = CompareMode.HTML,
    path: Path = Path.cwd(),
    name: str | None = None,
) -> Path:
    """Functional helper—compare multiple Tracy trace files and return path to comparison report.

    Accepts .tracy or .csv files; conversion is handled automatically.
    """
    log.debug(f"Starting Tracy comparison for {len(trace_paths)} files, mode: {mode.value}")

    match mode:
        case CompareMode.HDF5:
            return TracyCompareHdf5(path).compare(trace_paths, name=name)
        case CompareMode.HTML:
            return TracyCompareHTML(path).compare(trace_paths, name=name)
        case _:
            raise ValueError(f"Unsupported compare mode: {mode}")
