import logging
from pathlib import Path

from rich.pretty import pretty_repr

from ..tools import ContainerConfig, Docker
from .base import TracyExportCSVBase

log = logging.getLogger(__name__)


class TracyExportCSVDocker(TracyExportCSVBase):
    """Docker implementation using *tracy-csvexport* image."""

    def export(self, tracy_path: Path) -> Path:
        if not self.is_available():
            raise RuntimeError("tracy-csvexport Docker Image not found")

        csv_path = tracy_path.with_suffix(".csv")
        cfg = ContainerConfig(
            image_tag="tracy-csvexport",
            command=[f"/data/{tracy_path.name}"],
            volumes={str(self.path): {"bind": "/data", "mode": "rw"}},
            detach=False,
        )

        with Docker() as dk:
            success, stdout = dk.run_with_output(cfg)
            if not success:
                raise RuntimeError("tracy-csvexport container failed")

            # Write the CSV output from stdout to the file
            if not stdout.strip():
                raise RuntimeError("tracy-csvexport produced no output")

            csv_path.write_text(stdout, encoding="utf-8")

            if not csv_path.exists() or csv_path.stat().st_size == 0:
                raise RuntimeError(f"Tracy CSV export failed to create valid output file: {csv_path}")

        log.info("CSV written to %s", csv_path)
        return csv_path

    @staticmethod
    def is_available() -> bool:
        """Check if the tracy-csvexport Docker image is available."""
        with Docker() as dk:
            try:
                image_info = dk.get_image_info("tracy-csvexport")
                log.debug("tracy-csvexport image info: %s", pretty_repr(image_info))
                return image_info is not None
            except Exception as exc:
                log.debug("tracy-csvexport image not available: %s", exc)
        return False
