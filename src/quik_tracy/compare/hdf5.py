from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Sequence

import pandas as pd

from .csv import TracyCompareCSV

logger = logging.getLogger(__name__)


@dataclass
class TracyCompareHdf5(TracyCompareCSV):
    """Generate HDF5 comparison report from multiple Tracy trace files."""

    def compare(self, trace_paths: Sequence[Path], name: str | None = None) -> Path:
        """Load traces, compute comparison metrics, store HDF5."""
        csv_paths = super().compare(trace_paths, name=name)

        dfs = self._load_dataframes(csv_paths)
        combined_df = pd.concat(dfs, ignore_index=True)

        comparison_df = self._calculate_comparison_metrics(combined_df, csv_paths)
        summary = self._compute_summary_metrics(comparison_df, csv_paths)
        top_changes = self._compute_top_changes(comparison_df, csv_paths)

        output_path = self.path / (name or f"tracy_comparison_{len(csv_paths)}_files")
        output_path = output_path.with_suffix(".h5")

        with pd.HDFStore(output_path, "w") as store:
            store.put("raw_data", combined_df, format="table")
            store.put("comparison", comparison_df, format="table")
            store.get_storer("comparison").attrs.summary = summary
            store.get_storer("comparison").attrs.top_changes = top_changes

        logger.info(f"Comparison HDF5 saved to {output_path}")
        return output_path

    def _load_dataframes(self, csv_paths: Sequence[Path]) -> list[pd.DataFrame]:
        """Load each CSV, add source metadata, return list of DataFrames."""
        dfs: list[pd.DataFrame] = []
        for idx, path in enumerate(csv_paths):
            logger.info(f"Loading CSV {idx+1}/{len(csv_paths)}: {path}")
            df = pd.read_csv(path)
            # Use index-based naming to avoid special character issues
            df["_source_idx"] = idx
            df["_source_name"] = path.stem
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

    def _calculate_comparison_metrics(self, combined_df: pd.DataFrame, csv_paths: Sequence[Path]) -> pd.DataFrame:
        """Calculate function-level comparison metrics with baseline approach."""
        logger.info(f"Calculating comparison metrics for columns: {list(combined_df.columns)}")

        # Detect Tracy CSV format columns
        function_col, avg_col, min_col, max_col, count_col = self._detect_columns(list(combined_df.columns))
        if not function_col or not avg_col:
            logger.warning(f"Could not detect Tracy CSV format. Available columns: {list(combined_df.columns)}")
            return combined_df

        logger.info(f"Detected columns: func='{function_col}', avg='{avg_col}', min='{min_col}', max='{max_col}'")

        # Group by function and source index
        grouped = combined_df.groupby([function_col, "_source_idx"]).first().reset_index()
        all_functions = grouped[function_col].unique()

        rows: list[dict] = []
        for func in all_functions:
            func_data = grouped[grouped[function_col] == func]
            row = {"function_name": func}

            # Baseline (index 0)
            baseline = func_data[func_data["_source_idx"] == 0]
            if not baseline.empty:
                b = baseline.iloc[0]
                row["baseline_avg"] = b[avg_col]
                row["baseline_min"] = b.get(min_col, float("nan")) if min_col else float("nan")
                row["baseline_max"] = b.get(max_col, float("nan")) if max_col else float("nan")
                row["baseline_count"] = int(b.get(count_col, 0)) if count_col else 0
            else:
                row["baseline_avg"] = float("nan")
                row["baseline_min"] = float("nan")
                row["baseline_max"] = float("nan")
                row["baseline_count"] = 0

            # Comparisons (indices 1, 2, ...)
            for idx in range(1, len(csv_paths)):
                prefix = f"cmp{idx}"
                cmp_data = func_data[func_data["_source_idx"] == idx]

                if not cmp_data.empty:
                    c = cmp_data.iloc[0]
                    c_avg = c[avg_col]
                    c_min = c.get(min_col, float("nan")) if min_col else float("nan")
                    c_max = c.get(max_col, float("nan")) if max_col else float("nan")
                    c_cnt = int(c.get(count_col, 0)) if count_col else 0
                else:
                    c_avg = c_min = c_max = float("nan")
                    c_cnt = 0

                row[f"{prefix}_avg"] = c_avg
                row[f"{prefix}_min"] = c_min
                row[f"{prefix}_max"] = c_max
                row[f"{prefix}_count"] = c_cnt

                # Compute percent diff vs baseline
                b_avg = row["baseline_avg"]
                if pd.notna(b_avg) and pd.notna(c_avg) and b_avg != 0:
                    row[f"{prefix}_avg_diff_pct"] = ((c_avg - b_avg) / b_avg) * 100
                    row[f"{prefix}_avg_diff_ns"] = c_avg - b_avg
                else:
                    row[f"{prefix}_avg_diff_pct"] = float("nan")
                    row[f"{prefix}_avg_diff_ns"] = float("nan")

            rows.append(row)

        result_df = pd.DataFrame(rows)
        logger.info(f"Generated comparison table: {len(result_df)} functions")
        return result_df

    def _compute_summary_metrics(self, df: pd.DataFrame, csv_paths: Sequence[Path]) -> dict:
        """Compute summary metrics for the comparison."""
        n_files = len(csv_paths)
        total_funcs = len(df)

        # Count significant changes (>5% diff in any comparison)
        diff_cols = [c for c in df.columns if c.endswith("_avg_diff_pct")]
        if diff_cols:
            significant = int(df[diff_cols].abs().gt(5).any(axis=1).sum())
        else:
            significant = 0

        # Compute per-comparison summaries with richer metrics
        summaries = []
        for idx in range(1, n_files):
            base_col = "baseline_avg"
            cmp_col = f"cmp{idx}_avg"
            diff_col = f"cmp{idx}_avg_diff_ns"
            diff_pct_col = f"cmp{idx}_avg_diff_pct"

            if cmp_col not in df.columns:
                continue

            # Functions in common (both have valid data)
            mask = df[base_col].notna() & df[cmp_col].notna()
            funcs_in_common = int(mask.sum())

            # Significant changes for THIS comparison
            sig_mask = mask & (df[diff_pct_col].abs() > 5) if diff_pct_col in df.columns else mask
            sig_count = int(sig_mask.sum()) if diff_pct_col in df.columns else 0

            # Count improvements (negative diff = faster) and regressions (positive = slower)
            if diff_pct_col in df.columns:
                improvements_count = int((mask & (df[diff_pct_col] < -5)).sum())
                regressions_count = int((mask & (df[diff_pct_col] > 5)).sum())
            else:
                improvements_count = regressions_count = 0

            # Total time calculations
            base_sum = df.loc[mask, base_col].sum()
            cmp_sum = df.loc[mask, cmp_col].sum()
            diff_sum = df.loc[mask, diff_col].sum() if diff_col in df.columns else cmp_sum - base_sum
            pct = (diff_sum / base_sum * 100) if base_sum else 0.0

            summaries.append({
                "compare_idx": idx,
                "file_name": csv_paths[idx].stem,
                "baseline_name": csv_paths[0].stem,
                "funcs_in_common": funcs_in_common,
                "significant_changes": sig_count,
                "improvements_count": improvements_count,
                "regressions_count": regressions_count,
                "base_total_ns": float(base_sum),
                "cmp_total_ns": float(cmp_sum),
                "diff_ns": float(diff_sum),
                "diff_pct": float(pct),
            })

        # Backward compatibility with HTML template
        if summaries:
            avg_perf = {
                "human_diff": summaries[0]["diff_ns"],
                "pct_diff": summaries[0]["diff_pct"],
                "base_total": summaries[0]["base_total_ns"],
                "cmp_total": summaries[0]["cmp_total_ns"],
            }
        else:
            avg_perf = {"human_diff": 0.0, "pct_diff": 0.0, "base_total": 0.0, "cmp_total": 0.0}

        return {
            "total_functions": total_funcs,
            "significant_changes": significant,
            "comparisons": summaries,
            "avg_performance": avg_perf,
            "file_names": [p.stem for p in csv_paths],
        }

    def _compute_top_changes(self, df: pd.DataFrame, csv_paths: Sequence[Path], n: int = 10) -> dict:
        """Compute top N improvements and regressions per comparison by absolute time saved/lost."""
        if len(csv_paths) < 2:
            return {"comparisons": []}

        baseline_name = csv_paths[0].stem
        comparisons = []

        for idx in range(1, len(csv_paths)):
            diff_col = f"cmp{idx}_avg_diff_ns"
            pct_col = f"cmp{idx}_avg_diff_pct"
            avg_col = f"cmp{idx}_avg"
            cmp_name = csv_paths[idx].stem

            if diff_col not in df.columns:
                continue

            valid = df[df[diff_col].notna()].copy()

            def to_dict(r, diff_c=diff_col, pct_c=pct_col, avg_c=avg_col):
                return {
                    "function_name": r["function_name"],
                    "diff": float(r.get(pct_c, float("nan"))),
                    "base": float(r["baseline_avg"]),
                    "cmp": float(r[avg_c]),
                    "delta_ns": float(r[diff_c]),
                }

            # Improvements: negative diff (faster)
            improvs = valid[valid[diff_col] < 0].nsmallest(n, diff_col)
            improvements = [to_dict(row) for _, row in improvs.iterrows()]

            # Regressions: positive diff (slower)
            regs = valid[valid[diff_col] > 0].nlargest(n, diff_col)
            regressions = [to_dict(row) for _, row in regs.iterrows()]

            comparisons.append({
                "baseline_name": baseline_name,
                "compare_name": cmp_name,
                "compare_idx": idx,
                "improvements": improvements,
                "regressions": regressions,
            })

        # Backward compatibility: also include flat improvements/regressions from first comparison
        first = comparisons[0] if comparisons else {"improvements": [], "regressions": []}
        return {
            "comparisons": comparisons,
            "improvements": first.get("improvements", []),
            "regressions": first.get("regressions", []),
        }
