import logging
from pathlib import Path

import rich_click as click

from . import api, builders

log = logging.getLogger(__name__)

click.rich_click.SHOW_ARGUMENTS = True

banner = """
╔══════════════════════════╗
║    Q U I K  T R A C Y    ║
╚══════════════════════════╝
"""

click.echo(click.style(banner, fg="green"))


@click.group(name="main")
def main():
    pass


# Add the build command group
main.add_command(builders.cli.build_group)


@main.command()
@click.option("--name", default="capture.tracy", help="Name of the capture file")
@click.option("--host", default="host.docker.internal", help="Host to connect to")
@click.option("--port", default=8086, help="Port to connect to")
@click.option("--mode", type=click.Choice(["local", "docker", "auto"]), default="auto", help="Run mode")
@click.option("--path", type=click.Path(path_type=Path), default=Path.cwd(), help="Directory to save capture file")
def capture(name: str, host: str, port: int, mode: str, path: Path):
    """Capture Tracy profiling data."""
    run_mode = api.RunMode(mode)
    trace_path = api.run_capture(name, host, port, run_mode, path)
    log.info(f"✅ Capture completed: {trace_path}")


@main.command()
@click.argument("trace_path", type=click.Path(exists=True, path_type=Path))
@click.option("--mode", type=click.Choice(["local", "docker", "auto"]), default="auto", help="Run mode")
@click.option("--path", type=click.Path(path_type=Path), default=Path.cwd(), help="Directory to save export file")
def export(trace_path: Path, mode: str, path: Path):
    """Export Tracy trace to CSV format."""
    run_mode = api.RunMode(mode)
    csv_path = api.run_export(trace_path, run_mode, path)
    log.info(f"✅ Export completed: {csv_path}")


@main.command()
@click.argument("trace_path", type=click.Path(exists=True, path_type=Path))
@click.option("--mode", type=click.Choice(["hdf5", "html"]), default="html", help="Report format")
@click.option("--path", type=click.Path(path_type=Path), default=Path.cwd(), help="Directory to save report file")
def report(trace_path: Path, mode: str, path: Path):
    """Generate Tracy report from trace data."""
    report_mode = api.ReportMode(mode)
    report_path = api.run_report(trace_path, report_mode, path)
    log.info(f"✅ Report completed: {report_path}")


@main.command()
@click.argument("trace_path", type=click.Path(exists=True, path_type=Path, dir_okay=False), required=False)
@click.option("--host", default="host.docker.internal", help="Host to connect to (for live profiling)")
@click.option("--port", default=8086, help="Port to connect to (for live profiling)")
@click.option("--mode", type=click.Choice(["local", "docker", "auto"]), default="auto", help="Run mode")
@click.option("--path", type=click.Path(path_type=Path), default=Path.cwd(), help="Base directory for profiler")
def profiler(trace_path: Path | None, host: str, port: int, mode: str, path: Path):
    """Open Tracy trace file in profiler interface or connect to live application."""
    run_mode = api.RunMode(mode)
    success = api.run_profiler(trace_path, run_mode, host, port, path)
    if success:
        if trace_path:
            log.info(f"✅ Profiler started for file: {trace_path}!")
        else:
            log.info(f"✅ Profiler started for live connection: {host}:{port}!")
    else:
        log.info("❌ Failed to start profiler")


@main.command()
@click.option("--name", default="capture.tracy", help="Name of the capture file")
@click.option("--host", default="host.docker.internal", help="Host to connect to")
@click.option("--port", default=8086, help="Port to connect to")
@click.option("--capture-mode", type=click.Choice(["local", "docker", "auto"]), default="auto", help="Capture run mode")
@click.option("--export-mode", type=click.Choice(["local", "docker", "auto"]), default="auto", help="Export run mode")
@click.option("--report-mode", type=click.Choice(["hdf5", "html"]), default="html", help="Report format")
@click.option("--path", type=click.Path(path_type=Path), default=Path.cwd(), help="Base directory for session files")
def session(name: str, host: str, port: int, capture_mode: str, export_mode: str, report_mode: str, path: Path):
    """Run a complete Tracy profiling session (capture + export + report)."""
    trace_path, csv_path, report_path = api.run_session(
        name,
        host,
        port,
        api.RunMode(capture_mode),
        api.RunMode(export_mode),
        api.ReportMode(report_mode),
        path,
    )
    log.info("✅ Tracy session completed successfully!")
    log.info(f"  Trace file: {trace_path}")
    log.info(f"  CSV file: {csv_path}")
    log.info(f"  Report file: {report_path}")


@main.command()
@click.argument("trace_files", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--mode", type=click.Choice(["hdf5", "html"]), default="html", help="Comparison report format")
@click.option("--path", type=click.Path(path_type=Path), default=Path.cwd(), help="Directory to save comparison report")
@click.option("--name", default=None, help="Custom name for the output comparison report file (without extension)")
def compare(trace_files: tuple, mode: str, path: Path, name: str | None):
    """Compare multiple Tracy trace files for performance analysis."""
    compare_mode = api.CompareMode(mode)
    report_path = api.run_compare(list(trace_files), compare_mode, path, name=name)

    log.info(f"✅ Comparison completed: {report_path}")
    log.info(f"  Files compared: {len(trace_files)}")
    log.info(f"  Report format: {mode.upper()}")
