from dataclasses import dataclass
import logging
from pathlib import Path

from ...tools import CMake, ProcessRunner
from .base import TracyBuilderBase

logger = logging.getLogger(__name__)

REPO = "https://github.com/wolfpld/tracy.git"


@dataclass
class TracyBuilderLocal(TracyBuilderBase):
    """Local builder using git clone + cmake."""

    portable: bool = False

    def build(self) -> bool:
        if not self.is_available():
            raise RuntimeError("Local build tools are not available")

        # Use shared paths for all Tracy tools
        build_path = self._get_path("build")
        install_path = self._get_path("install")
        source_path = build_path / "tracy"

        # Clone Tracy repository once (shared by all tools)
        runner = ProcessRunner()
        if not source_path.exists():
            logger.info(f"Cloning Tracy {self.branch}::{self.ref} into {source_path}")
            runner.run_streaming(["git", "clone", "--branch", self.branch, REPO, str(source_path)])
            runner.run_streaming(["git", "checkout", self.ref], cwd=source_path)
        else:
            logger.debug(f"Tracy repository already exists at {source_path}")

        # Extract tool name without 'tracy-' prefix for directory lookup
        tool_dir = self.tool_name.replace("tracy-", "")
        tool_source_path = source_path / tool_dir

        if not tool_source_path.exists():
            raise RuntimeError(f"Tool directory '{tool_dir}' not found in Tracy repository at {tool_source_path}")

        # Create individual build directory for this tool
        tool_build_path = build_path / f"build-{self.tool_name}"

        # Shared install directory with bin subdirectory
        bin_install_path = install_path / "bin"
        bin_install_path.mkdir(parents=True, exist_ok=True)

        # Shared CPM cache directory (avoids re-downloading packages for each tool)
        cpm_cache_path = build_path / "cpm-cache"
        cpm_cache_path.mkdir(parents=True, exist_ok=True)

        # Build the tool
        cmake = CMake(
            source_path=str(tool_source_path),
            build_path=str(tool_build_path),
            install_path=str(install_path),
            build_type="Release",
            cpm_cache_path=str(cpm_cache_path),
            portable=self.portable,
        )
        logger.info(f"Configuring {self.tool_name}")
        cmake.configure()
        logger.info(f"Building {self.tool_name}")
        cmake.build()
        logger.info(f"Installing {self.tool_name} to {bin_install_path}")
        cmake.install()

        # Verify the executable was installed
        expected_exe = bin_install_path / self.tool_name
        if expected_exe.exists():
            logger.info(f"Successfully built and installed {self.tool_name} at {expected_exe}")
            return True
        else:
            logger.error(f"Expected executable not found at {expected_exe}")
            return False
        return True

    @staticmethod
    def is_available() -> bool:
        """Check if git and cmake are available."""
        return ProcessRunner.which("git") is not None and ProcessRunner.which("cmake") is not None

    def get_executable_path(self) -> Path | None:
        """Get the specific install path for this tool's executable."""
        executable_in_path = ProcessRunner.which(self.tool_name)
        if executable_in_path is None:
            install_path = self._get_path("install")
            tool_path = install_path / "bin" / self.tool_name
            if tool_path.exists():
                logger.debug(f"Found quik-tracy executable {self.tool_name} at {tool_path}")
                executable_in_path = tool_path
            else:
                logger.error(f"{self.tool_name} not found in expected install path: {tool_path}")
                return None
        return executable_in_path
