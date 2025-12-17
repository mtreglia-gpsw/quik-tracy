from dataclasses import dataclass
from pathlib import Path
from enum import Enum
import logging
import shutil
from typing import Optional

from .engines import TracyBuilderLocal, TracyBuilderDocker

logger = logging.getLogger(__name__)

BRANCH = "master"
REF = "3258599899ecfd0d5d901b577cbc555fa645d6e4"


class BuildMode(Enum):
    LOCAL = "local"
    DOCKER = "docker"
    AUTO = "auto"


@dataclass
class BuilderAvailability:
    """Status of available builders."""

    local: bool
    docker: bool


@dataclass
class LocalToolStatus:
    """Status of a tool for local building."""

    builder_available: bool
    executable_available: bool
    executable_path: Optional[str]


@dataclass
class DockerToolStatus:
    """Status of a tool for Docker building."""

    builder_available: bool
    image_available: bool


@dataclass
class ToolStatus:
    """Complete status of a specific tool."""

    local: LocalToolStatus
    docker: DockerToolStatus


@dataclass
class DetailedBuildStatus:
    """Comprehensive build status information."""

    builders: BuilderAvailability
    tools: dict[str, ToolStatus]


def build_tracy_tool(
    tool_name: str,
    mode: BuildMode = BuildMode.AUTO,
    branch: str = BRANCH,
    ref: str = REF,
    portable: bool = False,
) -> bool:
    """
    Build a Tracy tool using the specified mode.

    Args:
        tool_name: Name of the Tracy tool to build (e.g., 'capture', 'csvexport', 'profiler')
        mode: Build mode (local, image, or auto)
        branch: Git branch to use for building
        ref: Git commit reference to use for building
        portable: If True, build with static linking for portable binaries

    Returns:
        bool: True if build was successful

    Raises:
        RuntimeError: If the build fails or no suitable builder is available
    """
    logger.debug(f"Building Tracy tool '{tool_name}' with mode: {mode.value}")

    if mode == BuildMode.LOCAL:
        builder = TracyBuilderLocal(tool_name, branch, ref, portable=portable)
    elif mode == BuildMode.DOCKER:
        builder = TracyBuilderDocker(tool_name, branch, ref)
    elif mode == BuildMode.AUTO:
        # Try local first, fallback to image
        local_builder = TracyBuilderLocal(tool_name, branch, ref, portable=portable)
        if local_builder.is_available():
            builder = local_builder
        else:
            image_builder = TracyBuilderDocker(tool_name, branch, ref)
            if image_builder.is_available():
                builder = image_builder
            else:
                raise RuntimeError("No suitable builder available (neither local nor Docker)")
    else:
        raise ValueError(f"Unsupported build mode: {mode}")

    logger.info(f"Using {builder.__class__.__name__} to build {tool_name}")
    return builder.build()


# Convenience functions for specific tools
def build_capture_tool(mode: BuildMode = BuildMode.AUTO, branch: str = BRANCH, ref: str = REF, portable: bool = False) -> bool:
    """Build the Tracy capture tool."""
    return build_tracy_tool("tracy-capture", mode, branch, ref, portable=portable)


def build_csvexport_tool(mode: BuildMode = BuildMode.AUTO, branch: str = BRANCH, ref: str = REF, portable: bool = False) -> bool:
    """Build the Tracy CSV export tool."""
    return build_tracy_tool("tracy-csvexport", mode, branch, ref, portable=portable)


def build_profiler_tool(mode: BuildMode = BuildMode.AUTO, branch: str = BRANCH, ref: str = REF, portable: bool = False) -> bool:
    """Build the Tracy profiler tool."""
    return build_tracy_tool("tracy-profiler", mode, branch, ref, portable=portable)


def get_available_builders() -> BuilderAvailability:
    """
    Check which builders are available on the current system.

    Returns:
        BuilderAvailability: Status of available builders
    """
    # Create dummy builders to check availability
    dummy_local = TracyBuilderLocal("dummy")
    dummy_image = TracyBuilderDocker("dummy")

    return BuilderAvailability(
        local=dummy_local.is_available(),
        docker=dummy_image.is_available(),
    )


def get_executable_path(tool_name: str) -> Optional[Path]:
    """
    Get the executable path for a specific Tracy tool.

    Args:
        tool_name: Name of the Tracy tool (e.g., 'tracy-capture', 'tracy-csvexport', 'tracy-profiler')

    Returns:
        Optional[Path]: Path to the tool's executable if available, otherwise None
    """
    return TracyBuilderLocal(tool_name).get_executable_path()


def list_supported_tools() -> list[str]:
    """
    List all supported Tracy tools that can be built.

    Returns:
        list: List of supported tool names
    """
    return ["tracy-capture", "tracy-csvexport", "tracy-profiler"]


def get_build_directory() -> Path:
    """
    Get the base build directory for Tracy tools.

    Returns:
        Path: Path to the build directory (~/.quik-tracy)
    """
    return Path.home() / ".quik-tracy"


def clean_build(remove_install: bool = False) -> tuple[bool, list[str]]:
    """
    Clean the Tracy build directory to force a fresh rebuild.

    This removes cached CMake configurations, build artifacts, and optionally
    the installed executables. Useful when encountering build issues due to
    stale SDK paths, outdated caches, or after Xcode updates.

    Args:
        remove_install: If True, also remove installed executables.
                       If False (default), only remove build cache.

    Returns:
        tuple[bool, list[str]]: (success, list of removed directories)
    """
    base_path = get_build_directory()
    removed = []

    if not base_path.exists():
        logger.info("No build directory found, nothing to clean")
        return True, removed

    # Always remove the build directory (contains CMake cache and build artifacts)
    build_path = base_path / "build"
    if build_path.exists():
        try:
            shutil.rmtree(build_path)
            removed.append(str(build_path))
            logger.info(f"Removed build cache: {build_path}")
        except Exception as e:
            logger.error(f"Failed to remove build cache: {e}")
            return False, removed

    # Optionally remove installed executables
    if remove_install:
        install_path = base_path / "install"
        if install_path.exists():
            try:
                shutil.rmtree(install_path)
                removed.append(str(install_path))
                logger.info(f"Removed installed tools: {install_path}")
            except Exception as e:
                logger.error(f"Failed to remove installed tools: {e}")
                return False, removed

    return True, removed


def get_detailed_build_status() -> DetailedBuildStatus:
    """
    Get detailed status information about build environment and available tools.

    Returns:
        DetailedBuildStatus: Status information including builders and tools availability
    """
    return DetailedBuildStatus(builders=get_available_builders(), tools=get_tools_status())


def get_tools_status() -> dict[str, ToolStatus]:
    """Get status of each tool across different builders."""
    tools_status = {}

    for tool in list_supported_tools():
        # Check for executable in the shared bin directory
        shared_install_path = get_executable_path(tool)
        executable_available = shared_install_path is not None and shared_install_path.exists() and shared_install_path.is_file()

        local_status = LocalToolStatus(
            builder_available=TracyBuilderLocal.is_available(),
            executable_available=executable_available,
            executable_path=str(shared_install_path),
        )

        docker_status = DockerToolStatus(
            builder_available=TracyBuilderDocker.is_available(), image_available=_check_docker_image_exists(tool)
        )

        tools_status[tool] = ToolStatus(local=local_status, docker=docker_status)

    return tools_status


def _check_docker_image_exists(image_name: str) -> bool:
    """Check if a Docker image exists."""
    try:
        from ..tools import Docker

        with Docker() as dk:
            image_info = dk.get_image_info(image_name)
            return image_info is not None
        return False
    except Exception:
        return False
