from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
import logging
from pathlib import Path
import subprocess
from types import TracebackType
from typing import Any, Iterable

import docker as docker_sdk
from docker.errors import (
    BuildError,
    DockerException,
    ImageNotFound,
)

from .process import ProcessRunner

log = logging.getLogger(__name__)

# Module-level cached Docker client
_cached_client: docker_sdk.DockerClient | None = None


def get_docker_client() -> docker_sdk.DockerClient:
    """Get a cached Docker client instance."""
    global _cached_client
    if _cached_client is None:
        _cached_client = docker_sdk.from_env()
    return _cached_client


@dataclass(slots=True)
class ImageInfo:
    id: str
    tags: list[str]
    created: datetime | None = None
    size: int | None = None
    architecture: str | None = None
    os: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContainerConfig:
    image_tag: str
    command: str | list[str] | None = None
    environment: dict[str, str] = field(default_factory=dict)
    volumes: dict[str, dict[str, str]] = field(default_factory=dict)
    detach: bool = True
    network_mode: str | None = None
    extra_hosts: dict[str, str] = field(default_factory=dict)
    ports: dict[str, int | list[int] | tuple[str, int] | None] = field(default_factory=dict)


class Docker(AbstractContextManager["Docker"]):
    """Thin wrapper around *docker-py* with uniform bool return values."""

    _client: docker_sdk.DockerClient

    # ───── context protocol ─────

    def __enter__(self) -> "Docker":
        self._client = get_docker_client()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        # Don't close the cached client - let it be reused
        # let any exception propagate
        return False

    # ─────────── public API ────────────

    def pull(self, image: str) -> bool:
        try:
            stream = self._client.api.pull(repository=image, stream=True, decode=True)
            self._consume_json(stream)
            return True
        except DockerException as exc:
            log.error("Pull failed: %s", exc)
            return False

    def build(
        self,
        path: Path,
        *,
        tag: str,
        build_args: dict[str, str] | None = None,
        platform: str | None = None,
        dockerfile: str | None = None,
    ) -> bool:
        """`docker build`; returns `True` on success."""
        # Make a copy of build_args to avoid modifying the original
        final_build_args = dict(build_args or {})

        # Auto-detect platform and set TARGETARCH if not already set
        if "TARGETARCH" not in final_build_args:
            import platform as platform_module

            machine = platform_module.machine().lower()

            if machine in ("arm64", "aarch64"):
                final_build_args["TARGETARCH"] = "arm64"
                if platform is None:
                    platform = "linux/arm64"
            elif machine in ("x86_64", "amd64"):
                final_build_args["TARGETARCH"] = "amd64"
                if platform is None:
                    platform = "linux/amd64"
            else:
                # Default to amd64 for unknown architectures
                final_build_args["TARGETARCH"] = "amd64"
                if platform is None:
                    platform = "linux/amd64"
                log.warning(f"Unknown architecture {machine}, defaulting to amd64")

        # Check if Dockerfile uses BuildKit features (--mount, --cache, etc.)
        # or has multi-stage platform-specific builds
        dockerfile_path = path / (dockerfile or "Dockerfile")
        needs_buildkit = False

        if dockerfile_path.exists():
            content = dockerfile_path.read_text()
            # Check for BuildKit features or multi-stage platform-specific builds
            has_buildkit_features = "--mount=" in content or "--cache=" in content or "--secret=" in content
            # Check for multi-platform builds
            has_platform_builds = "arm64" in content

            if has_buildkit_features or has_platform_builds:
                needs_buildkit = True
                log.debug("Dockerfile requires BuildKit features or multi-platform builds, using buildx")

        # Use buildx for BuildKit features, otherwise use regular build
        if needs_buildkit:
            return self.buildx(
                path=path,
                tag=tag,
                build_args=final_build_args,
                platform=platform,
                dockerfile=dockerfile,
            )

        kwargs: dict[str, Any] = {
            "path": str(path),
            "tag": tag,
            "buildargs": final_build_args,
            "rm": True,
            "platform": platform,
        }
        if dockerfile:
            kwargs["dockerfile"] = dockerfile

        try:
            # Use low-level API for regular builds
            stream = self._client.api.build(**kwargs, decode=True)
            self._consume_json(stream)
            return True
        except (BuildError, DockerException) as exc:
            log.error("Build failed: %s", exc)
            return False

    def buildx(
        self,
        path: Path,
        *,
        tag: str,
        build_args: dict[str, str] | None = None,
        platform: str | None = None,
        dockerfile: str | None = None,
    ) -> bool:
        """`docker buildx build`; returns `True` on success."""
        cmd = [
            "docker",
            "buildx",
            "build",
            "--load",  # Load the image into the local Docker daemon
            "--tag",
            tag,
        ]

        if platform:
            cmd.extend(["--platform", platform])

        if dockerfile:
            cmd.extend(["--file", str(path / dockerfile)])

        # Add build arguments
        if build_args:
            for key, value in build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])

        cmd.append(str(path))

        try:
            # Use ProcessRunner for better streaming output
            runner = ProcessRunner(cwd=path)
            runner.run_streaming(cmd)
            log.debug("Buildx successful for tag: %s", tag)
            return True
        except subprocess.CalledProcessError as exc:
            log.error("Buildx failed: %s", exc)
            return False
        except Exception as exc:
            log.error("Buildx failed with unexpected error: %s", exc)
            return False

    def run(self, cfg: ContainerConfig) -> bool:
        """
        Start a container.
        * In `detach=True` mode we just start it and return.
        * In attached mode we stream logs to DEBUG until it exits.
        """
        try:
            container = self._client.containers.run(
                cfg.image_tag,
                command=cfg.command,
                environment=cfg.environment,
                volumes=cfg.volumes,
                network_mode=cfg.network_mode,
                extra_hosts=cfg.extra_hosts,
                ports=cfg.ports if cfg.ports else None,
                detach=cfg.detach,
                remove=not cfg.detach,
            )

            if not cfg.detach:
                # When detach=False, container.run() returns the output directly
                if isinstance(container, bytes):
                    log.debug("%s", container.decode().rstrip())
                else:
                    log.debug("%s", str(container).rstrip())
            else:
                # When detach=True, container is a Container object
                pass  # Container is running in background
            return True
        except DockerException as exc:
            log.error("Run failed: %s", exc)
            return False

    def run_with_output(self, cfg: ContainerConfig) -> tuple[bool, str]:
        """
        Start a container and capture its stdout.
        Returns (success, stdout_content).
        """
        try:
            container = self._client.containers.run(
                cfg.image_tag,
                command=cfg.command,
                environment=cfg.environment,
                volumes=cfg.volumes,
                network_mode=cfg.network_mode,
                extra_hosts=cfg.extra_hosts,
                detach=True,
                remove=False,  # don't auto-remove so we can get logs
            )

            # Wait for container to finish
            result = container.wait()

            # Get the logs (stdout)
            logs = container.logs(stdout=True, stderr=False).decode("utf-8")

            # Clean up container
            container.remove()

            # Check exit code
            if result["StatusCode"] != 0:
                log.error("Container exited with code %d", result["StatusCode"])
                return False, logs

            return True, logs
        except DockerException as exc:
            log.error("Run with output failed: %s", exc)
            return False, ""

    def logs(self, container_id: str, *, follow: bool = True) -> bool:
        """Mirror `docker logs` to DEBUG; always returns `bool`."""
        try:
            container = self._client.containers.get(container_id)
            for line in container.logs(stream=follow, follow=follow):
                if isinstance(line, bytes):
                    log.debug("%s", line.decode().rstrip())
                else:
                    log.debug("%s", str(line).rstrip())
            return True
        except DockerException as exc:
            log.error("Logs failed: %s", exc)
            return False

    def remove_image(self, image: str, *, force: bool = False) -> bool:
        try:
            self._client.images.remove(image, force=force)
            return True
        except DockerException as exc:
            log.error("Remove failed: %s", exc)
            return False

    # ─────── read‑only helpers ───────

    def get_image_info(self, image: str) -> ImageInfo | None:
        try:
            img = self._client.images.get(image)
        except ImageNotFound:
            return None
        return ImageInfo(
            id=img.id or "",
            tags=img.tags,
            created=self._parse_iso(img.attrs.get("Created")),
            size=img.attrs.get("Size"),
            architecture=img.attrs.get("Architecture"),
            os=img.attrs.get("Os"),
            config=img.attrs.get("Config", {}),
        )

    def list_images(self, **filters: str) -> list[ImageInfo]:
        result: list[ImageInfo] = []
        for img in self._client.images.list(filters=filters):
            result.append(
                ImageInfo(
                    id=img.id or "",
                    tags=img.tags,
                    created=self._parse_iso(img.attrs.get("Created")),
                    size=img.attrs.get("Size"),
                )
            )
        return result

    # ─────── internals ───────

    @staticmethod
    def _consume_json(stream: Iterable[dict[str, Any]]) -> None:
        """Write each Docker JSON event to DEBUG; raise on build errors."""
        for chunk in stream:
            match chunk:
                case {"stream": s}:
                    log.debug("%s", str(s).rstrip())

                case {"status": status, "id": cid, **rest}:
                    msg = f"{cid}: {status}"
                    if "progress" in rest:
                        msg += f' {rest["progress"]}'
                    log.debug("%s", msg)

                case {"status": status, **rest}:
                    log.debug("%s", status)

                case {"error": msg} | {"errorDetail": {"message": msg}}:
                    raise BuildError(str(msg), build_log=iter([]))

                case _:
                    log.debug("%s", chunk)

    @staticmethod
    def _parse_iso(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            from dateutil import parser

            return parser.isoparse(ts)
        except ValueError:
            log.warning("Unparsable timestamp %s", ts)
            return None
