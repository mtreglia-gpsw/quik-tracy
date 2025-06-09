import logging
from pathlib import Path

import pandas as pd

from .hdf5 import TracyReportHdf5

logger = logging.getLogger(__name__)


class TracyReportHTML(TracyReportHdf5):
    """Generate per-function min/avg/max table and save HTML."""

    def report(self, csv_path: Path) -> Path:
        """Build the report and return the HTML string."""
        h5_path = super().report(csv_path)
        df = pd.read_hdf(h5_path, "tracy")
        html = df.to_html(index=False, classes="dataframe")
        output_path = h5_path.with_suffix(".html")
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"HTML report saved to {output_path}")
        return output_path
