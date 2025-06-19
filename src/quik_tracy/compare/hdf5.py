from dataclasses import dataclass
import logging
from pathlib import Path
from typing import List

import pandas as pd

from .base import TracyCompareBase

logger = logging.getLogger(__name__)


@dataclass
class TracyCompareHdf5(TracyCompareBase):
    """Generate HDF5 comparison report from multiple Tracy CSV files."""

    def compare(self, csv_paths: List[Path], name: str | None = None) -> Path:
        """Main entry: load CSVs, compute comparison, store HDF5 and metrics."""
        if len(csv_paths) < 2:
            raise ValueError("At least 2 CSV files required for comparison")

        dfs = self._load_dataframes(csv_paths)
        combined_df = pd.concat(dfs, ignore_index=True)

        comparison_df = self._calculate_comparison_metrics(combined_df, csv_paths)
        summary = self._compute_summary_metrics(comparison_df, csv_paths)
        top_changes = self._compute_top_changes(comparison_df, csv_paths)

        if name:
            output_path = self.path / f"{name}.h5"
        else:
            output_path = self.path / f"tracy_comparison_{len(csv_paths)}_files.h5"
        with pd.HDFStore(output_path, "w") as store:
            store.put("raw_data", combined_df, format="table")
            store.put("comparison", comparison_df, format="table")
            store.get_storer("comparison").attrs.summary = summary
            store.get_storer("comparison").attrs.top_changes = top_changes

        logger.info(f"Comparison HDF5 saved to {output_path}")
        return output_path

    def _load_dataframes(self, csv_paths: List[Path]) -> list[pd.DataFrame]:
        """Load each CSV, add source metadata, return list of DataFrames."""
        dfs: list[pd.DataFrame] = []
        for idx, path in enumerate(csv_paths):
            logger.info(f"Loading CSV {idx+1}/{len(csv_paths)}: {path}")
            df = pd.read_csv(path)
            df["source_file"] = path.stem
            df["source_index"] = idx
            dfs.append(df)
        return dfs

    def _detect_columns(self, columns: list[str]) -> tuple[str | None, str | None, str | None, str | None, str | None]:
        """Detect and return common Tracy CSV columns: function, avg, min, max, count."""
        function_col = next((c for c in ["name", "function", "zone_name", "symbol"] if c in columns), None)
        avg_col = next((c for c in ["mean_ns", "avg_ns", "average_ns"] if c in columns), None)
        min_col = next((c for c in ["min_ns", "minimum_ns"] if c in columns), None)
        max_col = next((c for c in ["max_ns", "maximum_ns"] if c in columns), None)
        count_col = next((c for c in ["counts", "count", "calls"] if c in columns), None)
        return function_col, avg_col, min_col, max_col, count_col

    def _calculate_comparison_metrics(self, combined_df: pd.DataFrame, csv_paths: List[Path]) -> pd.DataFrame:
        """Calculate function-level comparison metrics with baseline approach."""
        logger.info(f"Calculating comparison metrics for dataframe with columns: {list(combined_df.columns)}")

        # Detect Tracy CSV format columns
        function_col, avg_col, min_col, max_col, count_col = self._detect_columns(list(combined_df.columns))
        if not function_col or not avg_col or not min_col or not max_col:
            logger.warning(f"Could not detect Tracy CSV format. Available columns: {list(combined_df.columns)}")
            logger.info("Returning raw combined data without function-level analysis")
            return combined_df

        logger.info(f"Using function column: '{function_col}', timing columns: avg='{avg_col}', min='{min_col}', max='{max_col}'")
        baseline, comparisons = csv_paths[0].stem, [p.stem for p in csv_paths[1:]]
        grouped = combined_df.groupby([function_col, "source_file", "source_index"]).first().reset_index()

        rows: list[dict] = []
        for func in grouped[function_col].unique():
            func_data = grouped[grouped[function_col] == func].sort_values("source_index")
            row = {"function_name": func}
            self._populate_baseline(row, func_data, baseline, avg_col, min_col, max_col, count_col)
            for idx, cmp_name in enumerate(comparisons, start=1):
                self._populate_comparison(row, func_data, idx, baseline, cmp_name, avg_col, min_col, max_col, count_col)
            rows.append(row)

        result_df = pd.DataFrame(rows)
        logger.info(f"Generated comparison table: {len(result_df)} functions")
        return result_df

    def _populate_baseline(self, row, func_data, base_name, avg, mn, mx, cnt):
        """Add baseline metrics to a comparison row dict."""
        data = func_data[func_data["source_index"] == 0]
        values = data.iloc[0] if not data.empty else {}
        row[f"{base_name}_avg_time"] = values.get(avg, float("nan"))
        row[f"{base_name}_min_time"] = values.get(mn, float("nan"))
        row[f"{base_name}_max_time"] = values.get(mx, float("nan"))
        row[f"{base_name}_call_count"] = values.get(cnt, 0)

    def _populate_comparison(self, row, func_data, idx, base_name, cmp_name, avg, mn, mx, cnt):
        """Add comparison metrics and percent differences to a row dict."""
        data = func_data[func_data["source_index"] == idx]
        values = data.iloc[0] if not data.empty else {}
        b_avg = row[f"{base_name}_avg_time"]
        c_avg = values.get(avg, float("nan"))
        row[f"{cmp_name}_avg_time"] = c_avg
        row[f"{cmp_name}_min_time"] = values.get(mn, float("nan"))
        row[f"{cmp_name}_max_time"] = values.get(mx, float("nan"))
        row[f"{cmp_name}_call_count"] = values.get(cnt, 0)
        # percent diff for avg
        if b_avg and pd.notna(b_avg) and pd.notna(c_avg):
            avg_diff = (c_avg - b_avg) / b_avg * 100
        else:
            avg_diff = float("nan")
        row[f"{cmp_name}_avg_perf_diff"] = avg_diff
        # percent diff for min
        base_min = row[f"{base_name}_min_time"]
        c_min = values.get(mn, float("nan"))
        if pd.notna(base_min) and pd.notna(c_min) and base_min != 0:
            min_diff = (c_min - base_min) / base_min * 100
        else:
            min_diff = float("nan")
        row[f"{cmp_name}_min_perf_diff"] = min_diff
        # percent diff for max
        base_max = row[f"{base_name}_max_time"]
        c_max = values.get(mx, float("nan"))
        if pd.notna(base_max) and pd.notna(c_max) and base_max != 0:
            max_diff = (c_max - base_max) / base_max * 100
        else:
            max_diff = float("nan")
        row[f"{cmp_name}_max_perf_diff"] = max_diff

    def _compute_summary_metrics(self, df: pd.DataFrame, csv_paths: List[Path]) -> dict:
        """Compute summary metrics for the comparison."""
        baseline = csv_paths[0].stem
        compare = csv_paths[1].stem if len(csv_paths) > 1 else None
        base_col = f"{baseline}_avg_time"
        cmp_col = f"{compare}_avg_time" if compare else None

        # Only compute differences for functions that exist in both traces (intersection)
        if cmp_col:
            intersection_mask = df[base_col].notna() & df[cmp_col].notna()
            intersection_df = df[intersection_mask]
            base_total = intersection_df[base_col].sum(skipna=True)
            cmp_total = intersection_df[cmp_col].sum(skipna=True)
            time_diff = cmp_total - base_total
            pct_diff = (time_diff / base_total * 100) if base_total else 0
        else:
            base_total = cmp_total = time_diff = pct_diff = 0

        # Significant changes
        diff_cols = df.filter(regex="_avg_perf_diff$")
        significant_changes = int(diff_cols.stack(dropna=True).abs().gt(5).sum())

        return {
            "total_functions": int(len(df)),
            "significant_changes": significant_changes,
            "avg_performance": {
                "human_diff": float(time_diff),
                "pct_diff": float(pct_diff),
                "base_total": float(base_total),
                "cmp_total": float(cmp_total),
            },
        }

    def _compute_top_changes(self, df: pd.DataFrame, csv_paths: List[Path], n: int = 10) -> dict:
        """Compute top N improvements and regressions by absolute time saved/lost."""
        import numpy as np

        compare = csv_paths[1].stem if len(csv_paths) > 1 else None
        if not compare:
            return {"improvements": [], "regressions": []}
        # Melt to long format for diffs
        diffs = df.melt(
            "function_name", value_vars=df.filter(regex="_avg_perf_diff$").columns, var_name="metric", value_name="diff"
        ).dropna()
        significant = diffs.loc[diffs["diff"].abs() > 0]
        if significant.empty:
            return {"improvements": [], "regressions": []}

        # Attach times
        def _attach_times(row):
            comp = row.metric.replace("_avg_perf_diff", "")
            base_col = next((c for c in df.columns if c.endswith("_avg_time") and comp not in c), None)
            if base_col is None:
                base_col = next(c for c in df.columns if c.endswith("_avg_time"))
            cmp_col = f"{comp}_avg_time"
            func_row = df.loc[df.function_name == row.function_name]
            if func_row.empty:
                return pd.Series({"base": np.nan, "cmp": np.nan, "delta_ns": np.nan})
            base_ns = func_row[base_col].iat[0]
            cmp_ns = func_row[cmp_col].iat[0]
            delta_ns = cmp_ns - base_ns if pd.notna(cmp_ns) and pd.notna(base_ns) else np.nan
            return pd.Series(
                {
                    "base": base_ns,
                    "cmp": cmp_ns,
                    "delta_ns": delta_ns,
                }
            )

        times = significant.apply(_attach_times, axis=1)
        significant = pd.concat([significant, times], axis=1)
        significant = significant[pd.notna(significant["delta_ns"])]
        # Split before taking top N
        improvs = significant[significant["delta_ns"] < 0].sort_values("delta_ns").head(n)
        regs = significant[significant["delta_ns"] > 0].sort_values("delta_ns", ascending=False).head(n)

        # Return improvements and regressions as list of dicts

        def _to_dicts(df):
            return [
                {
                    "function_name": r.function_name,
                    "diff": r.diff,
                    "base": r.base,
                    "cmp": r.cmp,
                    "delta_ns": r.delta_ns,
                }
                for r in df.itertuples()
            ]

        return {
            "improvements": _to_dicts(improvs),
            "regressions": _to_dicts(regs),
        }
