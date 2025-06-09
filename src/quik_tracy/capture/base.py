from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TracyCaptureBase(abc.ABC):
    """Strategy interface that produces a *.tracy* file in *work_dir*."""

    host: str = "localhost"
    port: int = 8086
    path: Path = Path.cwd()

    @abc.abstractmethod
    def capture(self, trace_name: str) -> Path:
        raise NotImplementedError

    @staticmethod
    @abc.abstractmethod
    def is_available() -> bool:
        """Check if the capture strategy is available."""
        raise NotImplementedError
