"""
Clean OOP subprocess execution utilities for quik-tracy.

Provides a simple, consistent interface for all subprocess operations
with proper logging, error handling, and timeout support.
"""

import logging
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Optional, TextIO

logger = logging.getLogger(__name__)


class ProcessRunner:
    """Main class for executing subprocess operations with consistent error handling."""

    def __init__(self, cwd: Optional[Path] = None, timeout: int | None = None):
        """
        Initialize ProcessRunner.

        Args:
            cwd: Default working directory for commands
            timeout: Default timeout None
        """
        self.cwd = cwd or Path.cwd()
        self.timeout = timeout

    def run(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        """
        Execute a command synchronously with full output capture.

        Args:
            cmd: Command as list of strings
            **kwargs: Override defaults (cwd, timeout, check, etc.)
        """
        options = {
            "cwd": self.cwd,
            "timeout": self.timeout,
            "check": True,
            "capture_output": True,
            "text": True,
        }
        options.update(kwargs)

        logger.debug("Executing: %s", " ".join(cmd))

        try:
            result = subprocess.run(cmd, **options)
            logger.debug("Command completed with exit code: %d", result.returncode)
            if result.stdout:
                logger.debug("stdout: %s", result.stdout.strip())
            if result.stderr:
                logger.warning("stderr: %s", result.stderr.strip())
            return result
        except subprocess.CalledProcessError as e:
            logger.error("Command failed with exit code %d: %s", e.returncode, " ".join(cmd))
            raise
        except subprocess.TimeoutExpired:
            logger.error("Command timed out after %d seconds: %s", options["timeout"], " ".join(cmd))
            raise

    def run_background(self, cmd: list[str], suppress_output: bool = True, **kwargs) -> subprocess.Popen[str]:
        """
        Execute a command in the background (detached).

        Args:
            cmd: Command as list of strings
            suppress_output: Whether to suppress stdout/stderr
            **kwargs: Override defaults (cwd, etc.)
        """
        options = {
            "cwd": self.cwd,
            "text": True,
            "stdout": subprocess.DEVNULL if suppress_output else None,
            "stderr": subprocess.DEVNULL if suppress_output else None,
        }
        options.update(kwargs)

        logger.debug("Executing background: %s", " ".join(cmd))

        try:
            proc = subprocess.Popen(cmd, **options)
            logger.debug("Background process started with PID: %d", proc.pid)
            return proc
        except Exception as e:
            logger.error("Failed to start background process: %s", e)
            raise

    def run_to_file(self, cmd: list[str], output_file: Path, **kwargs) -> subprocess.CompletedProcess[str]:
        """
        Execute a command and write stdout to a file.

        Args:
            cmd: Command as list of strings
            output_file: Path where to write stdout
            **kwargs: Override defaults
        """
        logger.debug("Executing with output to %s: %s", output_file, " ".join(cmd))

        result = self.run(cmd, **kwargs)

        if result.stdout:
            output_file.write_text(result.stdout, encoding="utf-8")
            logger.debug("Output written to: %s", output_file)

        return result

    def run_streaming(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        """
        Execute a command with real-time output streaming to logger.

        This method streams stdout/stderr in real-time while the command runs,
        and also returns the complete output in the CompletedProcess object.

        Args:
            cmd: Command as list of strings
            **kwargs: Override defaults (cwd, timeout, check, etc.)
        """

        options = {
            "cwd": self.cwd,
            "timeout": self.timeout,
            "check": True,
        }
        options.update(kwargs)

        logger.debug("Executing streaming: %s", " ".join(cmd))

        # Prepare accumulators for building CompletedProcess
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        # Start the process with pipes for real-time streaming
        with subprocess.Popen(
            cmd,
            cwd=options["cwd"],
            env=os.environ.copy(),
            text=True,
            bufsize=1,  # line-buffered
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:

            def _stream_output(pipe: TextIO | None, sink: list[str], stream_type: str) -> None:
                """Read pipe line-by-line, log it, and save it."""
                if pipe is None:
                    return

                for line in iter(pipe.readline, ""):
                    sink.append(line)
                    clean_line = line.rstrip()
                    if stream_type == "STDOUT":
                        logger.debug("%s", clean_line)
                    elif stream_type == "STDERR":
                        logger.warning("%s", clean_line)
                pipe.close()

            # Start threads to stream both stdout and stderr concurrently
            stdout_thread = threading.Thread(target=_stream_output, args=(proc.stdout, stdout_lines, "STDOUT"), daemon=True)
            stderr_thread = threading.Thread(target=_stream_output, args=(proc.stderr, stderr_lines, "STDERR"), daemon=True)

            stdout_thread.start()
            stderr_thread.start()

            try:
                proc.wait(timeout=options.get("timeout"))
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_thread.join()
                stderr_thread.join()
                logger.error("Streaming command timed out: %s", " ".join(cmd))
                raise

            # Ensure threads complete
            stdout_thread.join()
            stderr_thread.join()

        # Build CompletedProcess result
        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
        )

        logger.debug("Streaming command completed with exit code: %d", result.returncode)

        if options.get("check", True) and result.returncode != 0:
            logger.error("Streaming command failed with exit code %d: %s", result.returncode, " ".join(cmd))
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)

        return result

    @staticmethod
    def which(executable: str) -> Path | None:
        """Check if an executable is available in PATH."""
        if ProcessRunner.is_available(executable):
            return Path(shutil.which(executable))
        else:
            logger.error("Executable not found in PATH: %s", executable)
            return None

    @staticmethod
    def is_available(executable: str) -> bool:
        """Check if an executable is available in PATH."""
        return shutil.which(executable) is not None
