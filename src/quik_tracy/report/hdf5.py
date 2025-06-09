from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

import pandas as pd

from .base import TracyReportBase

logger = logging.getLogger(__name__)


@dataclass
class TracyReportHdf5(TracyReportBase):
    """Generate per-function min/avg/max table and save HTML."""

    def report(self, csv_path: Path) -> Path:
        logger.info(f"Building DataFrame from {csv_path}")
        df = pd.read_csv(csv_path)
        output_path = self.path / csv_path.with_suffix(".h5").name
        with pd.HDFStore(output_path, "w") as store:
            store.put("tracy", df, format="table")
        logger.info(f"DataFrame saved to {output_path}")
        return output_path
