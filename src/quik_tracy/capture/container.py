from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import platform

from rich.pretty import pretty_repr

from ..tools import ContainerConfig, Docker
from .base import TracyCaptureBase

log = logging.getLogger(__name__)


@dataclass
class TracyCaptureDocker(TracyCaptureBase):
    """Docker-based capture using *tracy-capture* image.*"""

    host: str = "host.docker.internal" if platform.system() != "Linux" else "localhost"

    def capture(self, trace_name: str) -> Path:
        if not self.is_available():
            raise RuntimeError("tracy-capture Docker image is not available")

        cfg = ContainerConfig(
            image_tag="tracy-capture",
            command=[
                "-o",
                f"/data/{trace_name}",
                "-a",
                self.host,
                "-p",
                str(self.port),
            ],
            volumes={str(self.path): {"bind": "/data", "mode": "rw"}},
            network_mode="host",
            extra_hosts={"host.docker.internal": "host-gateway"},
            detach=False,
        )
        log.debug("Starting tracy-capture with config: %s", cfg)
        with Docker() as dk:
            log.info("Running tracy-capture container ...")
            if not dk.run(cfg):
                raise RuntimeError("tracy-capture container failed")
        trace_path = self.path / trace_name
        if not trace_path.is_file():
            raise FileNotFoundError(trace_path)
        log.info("Trace written to %s", trace_path)
        return trace_path

    @staticmethod
    def is_available() -> bool:
        """Check if the tracy-capture Docker image is available."""
        with Docker() as dk:
            try:
                image_info = dk.get_image_info("tracy-capture")
                log.debug("tracy-capture image info: %s", pretty_repr(image_info))
                return image_info is not None
            except Exception as exc:
                log.debug("tracy-capture image not available: %s", exc)
        return False
