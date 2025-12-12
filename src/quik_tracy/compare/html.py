from __future__ import annotations

import datetime
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Sequence

import pandas as pd

from .hdf5 import TracyCompareHdf5

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────────
#  Constants & helpers
# ────────────────────────────────────────────────────────────────────────────────
US, MS, S = 1_000, 1_000_000, 1_000_000_000  # 1 µs, 1 ms, 1 s in nanoseconds
SUB_100_MS = 100 * MS


def _human_time(ns: float | pd.NA) -> str:
    """Convert nanoseconds to human-readable time string."""
    if pd.isna(ns):
        return "<span class='perf-missing'>N/A</span>"
    abs_ns = abs(ns)
    if abs_ns < US:
        return f"{abs_ns:.0f}\u00a0ns"
    if abs_ns < MS:
        return f"{abs_ns / US:.1f}\u00a0µs"
    if abs_ns < S:
        return f"{abs_ns / MS:.1f}\u00a0ms"
    return f"{abs_ns / S:.2f}\u00a0s"


def _perf_class(pct: float, threshold: float = 2.0) -> str:
    """Return CSS class based on performance percentage change."""
    if pct < -threshold:
        return "perf-good"
    if pct > threshold:
        return "perf-bad"
    return "perf-neutral"


def _fmt_pct(p: float | pd.NA, base_ns: float | pd.NA = pd.NA, cmp_ns: float | pd.NA = pd.NA) -> str:
    """Format percentage diff with time delta and actual measurement.

    Handles cases:
    - Both baseline and comparison present: show "time_diff %diff\\nmeasure_time"
    - Baseline missing, comparison present: show "NEW" + comparison time
    - Comparison missing: show "N/A"
    """
    # If comparison is missing, show N/A
    if pd.isna(cmp_ns):
        return "<span class='perf-missing'>N/A</span>"

    # If baseline is missing but comparison exists, show as NEW function
    if pd.isna(base_ns) or pd.isna(p):
        human_time = _human_time(cmp_ns)
        data_attrs = f" data-cmp-ns='{cmp_ns}'"
        return f"<span class='perf-new'{data_attrs}>NEW<br><span class='measure-time'>{human_time}</span></span>"

    cls: str
    if p < -5:
        cls = "perf-good"
    elif p > 5 and not (pd.notna(base_ns) and pd.notna(cmp_ns) and base_ns < SUB_100_MS and cmp_ns < SUB_100_MS):
        cls = "perf-bad"
    elif p > 5:
        cls = "perf-warning"
    else:
        cls = "perf-neutral"
    sign = "+" if p > 0 else ""
    # Compute absolute time delta
    delta_ns = cmp_ns - base_ns
    human_delta = _human_time(delta_ns)
    human_measure = _human_time(cmp_ns)
    # Store both delta and cmp value - use cmp_ns for time-based sorting
    data_attrs = f" data-delta-ns='{delta_ns}' data-cmp-ns='{cmp_ns}'"
    # Format: "time_diff %diff" on first line, "measure_time" on second line
    return (
        f"<span class='{cls}'{data_attrs}>"
        f"<span class='delta-time'>{human_delta}</span> {sign}{p:.1f}%"
        f"<br><span class='measure-time'>{human_measure}</span>"
        f"</span>"
    )


# ────────────────────────────────────────────────────────────────────────────────
#  Main reporter
# ────────────────────────────────────────────────────────────────────────────────
@dataclass
class TracyCompareHTML(TracyCompareHdf5):
    """Generate an HTML comparison report from multiple Tracy CSV files."""

    def compare(self, csv_paths: Sequence[Path], name: str | None = None) -> Path:  # type: ignore[override]
        h5 = super().compare(csv_paths, name=name)  # reuse parent HDF5 logic, pass name
        with pd.HDFStore(h5, "r") as store:
            df = store["comparison"]
            summary = store.get_storer("comparison").attrs.summary
            top_changes = store.get_storer("comparison").attrs.top_changes
        html = self._render(df, csv_paths, summary, top_changes)
        if name:
            out = h5.parent / f"{name}.html"
        else:
            out = h5.with_suffix(".html")
        out.write_text(html, encoding="utf-8")
        logger.info("Comparison HTML saved to %s", out)
        return out

    # ────────────────────────────────────────────────────────────── html pieces ──
    @staticmethod
    def _files_info(paths: Sequence[Path]) -> str:
        """HTML grid with the list of compared files."""
        cards = [
            f"""
            <div class='file-card'>
              <h4>📁 {'Baseline' if i == 0 else f'Compare {i}'}</h4>
              <p>{p.name}</p>
            </div>"""
            for i, p in enumerate(paths)
        ]
        return "\n".join(cards)

    def _table(self, df: pd.DataFrame, file_names: list[str]) -> str:
        """Return a fully styled HTML <table>."""
        baseline_name = file_names[0] if file_names else "Baseline"
        cmp_names = file_names[1:] if len(file_names) > 1 else ["Compare"]

        # Metric labels mapping
        metric_labels = {
            "min": "Min",
            "avg": "Avg",
            "max": "Max",
            "count": "Calls",
        }

        def _header_text(col: str) -> str:
            if col == "function_name":
                return "Function"
            if col.startswith("baseline_"):
                suffix = col.replace("baseline_", "")
                label = metric_labels.get(suffix, suffix.title())
                return f"<span class='col-baseline'>{label}</span>"
            if col.startswith("cmp"):
                parts = col.split("_", 1)
                idx = int(parts[0].replace("cmp", "")) - 1
                metric = parts[1] if len(parts) > 1 else ""
                if metric == "avg_diff_pct":
                    return f"<span class='col-compare col-compare-{idx + 1}'>Δ%</span>"
                label = metric_labels.get(metric, metric.title())
                return f"<span class='col-compare col-compare-{idx + 1}'>{label}</span>"
            return col

        # Define column order: function, baseline (min/avg/max/count), then comparisons
        baseline_cols = ["baseline_min", "baseline_avg", "baseline_max", "baseline_count"]
        baseline_cols = [c for c in baseline_cols if c in df.columns]

        # Get comparison columns in order
        cmp_prefixes = sorted(set(c.split("_")[0] for c in df.columns if c.startswith("cmp")))
        cmp_cols = []
        for prefix in cmp_prefixes:
            for suffix in ["min", "avg", "max", "count", "avg_diff_pct"]:
                col = f"{prefix}_{suffix}"
                if col in df.columns:
                    cmp_cols.append(col)

        # Filter out _diff_ns columns
        display_cols = ["function_name"] + baseline_cols + cmp_cols
        display_cols = [c for c in display_cols if not c.endswith("_diff_ns")]

        # Track group boundaries for separators
        # Last column index of each group (0-indexed)
        group_last_cols = set()
        if baseline_cols:
            group_last_cols.add(len(baseline_cols))  # After function_name + baseline cols
        col_idx = 1 + len(baseline_cols)  # Start after function + baseline
        for prefix in cmp_prefixes:
            prefix_cols = [c for c in cmp_cols if c.startswith(prefix)]
            col_idx += len(prefix_cols)
            group_last_cols.add(col_idx - 1)

        # Build header with group headers
        baseline_header = (
            f"<th colspan='{len(baseline_cols)}' class='group-header baseline-group'>"
            f"🏁 Baseline<br><em>{baseline_name}</em></th>"
        )

        cmp_headers = []
        for i, prefix in enumerate(cmp_prefixes):
            prefix_cols = [c for c in cmp_cols if c.startswith(prefix)]
            name = cmp_names[i] if i < len(cmp_names) else f"Compare {i + 1}"
            cmp_headers.append(
                f"<th colspan='{len(prefix_cols)}' class='group-header compare-group compare-group-{i + 1}'>"
                f"🔬 Compare {i + 1}<br><em>{name}</em></th>"
            )

        group_header_row = f"<th></th>{baseline_header}{''.join(cmp_headers)}"

        # Build column headers with separator classes
        col_headers = []
        for i, c in enumerate(display_cols):
            sep_class = " group-sep" if i in group_last_cols else ""
            col_headers.append(f"<th class='{sep_class}'>{_header_text(c)}</th>")
        col_header_row = "".join(col_headers)

        body_rows: list[str] = []
        for _, row in df.iterrows():
            cells: list[str] = []
            for col_i, col in enumerate(display_cols):
                val = row[col]
                sep_class = " group-sep" if col_i in group_last_cols else ""
                if col == "function_name":
                    cells.append(f"<td class='col-function{sep_class}'><strong>{val}</strong></td>")
                elif col.endswith("_avg_diff_pct"):
                    prefix = col.replace("_avg_diff_pct", "")
                    base_ns = row.get("baseline_avg", pd.NA)
                    cmp_ns = row.get(f"{prefix}_avg", pd.NA)
                    cells.append(f"<td class='col-diff{sep_class}'>{_fmt_pct(val, base_ns, cmp_ns)}</td>")
                elif col.startswith("cmp") and ("_min" in col or "_avg" in col or "_max" in col):
                    # Compare min/avg/max time - show with percentage diff like Δ% column
                    # Determine which baseline metric to compare against
                    if "_min" in col:
                        base_ns = row.get("baseline_min", pd.NA)
                    elif "_max" in col:
                        base_ns = row.get("baseline_max", pd.NA)
                    else:  # _avg
                        base_ns = row.get("baseline_avg", pd.NA)
                    # Calculate percentage diff for this specific metric
                    if pd.notna(base_ns) and pd.notna(val) and base_ns != 0:
                        metric_diff_pct = ((val - base_ns) / base_ns) * 100
                    else:
                        metric_diff_pct = pd.NA
                    cells.append(f"<td class='col-diff{sep_class}'>{_fmt_pct(metric_diff_pct, base_ns, val)}</td>")
                elif "_min" in col or "_avg" in col or "_max" in col:
                    # Baseline min/avg/max - no coloring, just time value
                    cells.append(f"<td class='time-value{sep_class}'>{_human_time(val)}</td>")
                elif "_count" in col:
                    cells.append(f"<td class='count-value{sep_class}'>{int(val) if pd.notna(val) else '-'}</td>")
                else:
                    cells.append(f"<td class='{sep_class.strip()}'>{val if pd.notna(val) else '-'}</td>")
            body_rows.append("<tr>" + "".join(cells) + "</tr>")

        return (
            f"<thead><tr class='group-headers'>{group_header_row}</tr>"
            f"<tr class='col-headers'>{col_header_row}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody>"
        )

    def _significant_changes(self, top_changes: dict, summary: dict) -> str:
        """Render HTML for top improvements/regressions per comparison with summary stats."""
        comparisons = top_changes.get("comparisons", [])
        summary_comparisons = {s["compare_idx"]: s for s in summary.get("comparisons", [])}

        # Fallback for legacy format (single improvements/regressions lists)
        if not comparisons:
            comparisons = [{
                "baseline_name": "Baseline",
                "compare_name": "Compare",
                "compare_idx": 1,
                "improvements": top_changes.get("improvements", []),
                "regressions": top_changes.get("regressions", []),
            }]

        def _metric_card(icon: str, label: str, value: str, css_class: str = "") -> str:
            cls = f"mini-metric {css_class}" if css_class else "mini-metric"
            return (
                f"<div class='{cls}'>"
                f"<span class='mini-icon'>{icon}</span>"
                f"<span class='mini-value'>{value}</span>"
                f"<span class='mini-label'>{label}</span>"
                f"</div>"
            )

        def _block(title: str, icon: str, data: list, cls: str) -> str:
            section_class = "improvements" if cls == "perf-good" else "regressions"
            action = "saved" if cls == "perf-good" else "lost"

            if not data:
                items = f"<p class='change-item'>No significant {title.lower().replace('top ', '')} found.</p>"
            else:
                item_html = []
                for r in data:
                    diff = r["diff"]
                    delta = _human_time(r["delta_ns"])
                    base = _human_time(r["base"])
                    cmp = _human_time(r["cmp"])
                    item_html.append(
                        f"<div class='change-item'>"
                        f"<span class='change-function'>{r['function_name']}</span>"
                        f"<div class='change-values'>"
                        f"<span class='change-value {cls}'>{diff:+.1f}% ({delta} {action})</span>"
                        f"<span class='change-time-diff'>{base} → {cmp}</span>"
                        f"</div></div>"
                    )
                items = "".join(item_html)

            return f"<div class='change-section {section_class}'><h3>{icon} {title}</h3>{items}</div>"

        sections_html = []
        for cmp in comparisons:
            baseline = cmp.get("baseline_name", "Baseline")
            compare = cmp.get("compare_name", "Compare")
            cmp_idx = cmp.get("compare_idx", 1)
            improvs = cmp.get("improvements", [])
            regs = cmp.get("regressions", [])

            # Get per-comparison summary stats
            stats = summary_comparisons.get(cmp_idx, {})
            funcs_common = stats.get("funcs_in_common", "?")
            sig_changes = stats.get("significant_changes", 0)
            improv_count = stats.get("improvements_count", len(improvs))
            regress_count = stats.get("regressions_count", len(regs))
            diff_ns = stats.get("diff_ns", 0)
            diff_pct = stats.get("diff_pct", 0)

            # Determine performance class
            perf_class = _perf_class(diff_pct)
            perf_sign = "+" if diff_pct > 0 else ""

            header = f"<h3 class='comparison-header'>📊 {baseline} vs {compare}</h3>"

            # Mini metrics row
            metrics_row = (
                "<div class='comparison-metrics'>"
                + _metric_card("🔗", "Functions", str(funcs_common))
                + _metric_card("⚡", "Changed", str(sig_changes), perf_class if sig_changes > 0 else "")
                + _metric_card("🚀", "Faster", str(improv_count), "perf-good" if improv_count > 0 else "")
                + _metric_card("⚠️", "Slower", str(regress_count), "perf-bad" if regress_count > 0 else "")
                + _metric_card("📊", "Overall", f"{_human_time(diff_ns)} ({perf_sign}{diff_pct:.1f}%)", perf_class)
                + "</div>"
            )

            grid = (
                "<div class='changes-grid'>"
                + _block("🚀 Top 10 Improvements", "", improvs, "perf-good")
                + _block("⚠️ Top 10 Regressions", "", regs, "perf-bad")
                + "</div>"
            )
            sections_html.append(f"<div class='comparison-block'>{header}{metrics_row}{grid}</div>")

        return "\n".join(sections_html)

    def _render(self, df: pd.DataFrame, paths: Sequence[Path], summary: dict, top_changes: dict) -> str:
        file_names = summary.get("file_names", [p.stem for p in paths])
        pct_diff = summary["avg_performance"]["pct_diff"]
        perf_class = _perf_class(pct_diff)

        ctx = {
            "total_functions": summary["total_functions"],
            "significant_changes": summary["significant_changes"],
            "avg_performance": f"{_human_time(summary['avg_performance']['human_diff'])} ({pct_diff:+.1f}%)",
            "avg_perf_class": perf_class,
            "overall_class": perf_class if summary["significant_changes"] else "perf-neutral",
            "files_info": self._files_info(paths),
            "comparison_table": self._table(df, file_names),
            "significant_changes_content": self._significant_changes(top_changes, summary),
            "generation_date": datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        }
        return _HTML_TEMPLATE.format(**ctx)


# ────────────────────────────────────────────────────────────────────────── template ──
# HTML template with full CSS
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tracy Performance Comparison Report</title>
  <style>
    /* ── Variables ───────────────────────────────────────────────────────── */
    :root {{
      --bg: #f4f7f9;
      --surface: #ffffff;
      --primary: #4a90e2;
      --primary-dark: #357ABD;
      --text: #333;
      --muted: #6c757d;
      --border: #e9ecef;
      --shadow: 0 4px 12px rgba(0,0,0,0.08);
      --shadow-sm: 0 2px 4px rgba(0,0,0,0.05);

      --success: #28a745;
      --success-bg: #e9f7ef;
      --error:   #dc3545;
      --error-bg:   #fbebed;
      --warning-text: #ffc107;
      --missing-text: #868e96;
    }}

    /* ── Animations ─────────────────────────────────────────────────────-- */
    @keyframes fadeInUp {{
      from {{ opacity: 0; transform: translateY(20px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes popIn {{
      0%   {{ transform: scale(0.95); opacity: 0; }}
      80%  {{ transform: scale(1.3); opacity: 1; }}
      100% {{ transform: scale(1); }}
    }}

    /* ── Base Reset ──────────────────────────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji';
      font-size: 16px;
      color: var(--text);
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}
    body {{ background: var(--bg); line-height: 1.6; }}

    /* Center the container vertically and horizontally */
    body {{
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    img, svg {{ max-width: 100%; height: auto; }}

    /* ── Skip Link ───────────────────────────────────────────────────────── */
    .skip-nav {{
      position: absolute; top: -40px; left: 1rem;
      background: var(--primary-dark); color: #fff; padding: 0.5rem 1rem;
      z-index: 100; text-decoration: none; border-radius: 0.25rem;
    }}
    .skip-nav:focus {{ top: 1rem; }}

    /* ── Container & Layout ─────────────────────────────────────────────── */
    .container {{
      width: auto;
      max-width: 95%;
      margin: 2rem auto;
      background: var(--surface);
      border-radius: 0.75rem;
      box-shadow: var(--shadow);
      overflow-x: auto;
      border: 1px solid var(--border);
      animation: fadeInUp 1.2s cubic-bezier(.39,.575,.565,1) both;
    }}

    header {{
      background: var(--primary);
      color: #fff;
      padding: 2.5rem 2rem;
      border-bottom: 4px solid var(--primary-dark);
      text-align: center;
    }}
    header h1 {{
      font-size: 2.25rem;
      font-weight: 600;
      text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
    }}
    header .subtitle {{
        opacity: 0.8;
        margin-top: 0.5rem;
        font-size: 1rem;
    }}

    .files-info {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1.5rem; justify-content: center; }}
    .file-card {{
      flex: 1 1 calc(50% - 1rem);
      background: rgba(255,255,255,0.15);
      padding: 1rem;
      border-radius: 0.5rem;
      border: 1px solid rgba(255,255,255,0.2);
      text-align: center;
    }}
    .file-card h4 {{
      font-size: 1rem;
      color: #fff;
      margin-bottom: 0.5rem;
      font-weight: 600;
    }}
    .file-card p {{
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 0.9rem;
      opacity: 0.9;
    }}

    /* ── Summary Metrics ───────────────────────────────────────────────── */
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1.5rem;
      background: var(--bg);
      padding: 2rem;
      justify-items: center;
      text-align: center;
    }}
    .metric {{
      text-align: center;
      background: var(--surface);
      padding: 1.5rem;
      border-radius: 0.5rem;
      box-shadow: var(--shadow-sm);
      border: 1px solid var(--border);
      transition: transform 0.2s, box-shadow 0.2s;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      animation: popIn 1.5s cubic-bezier(.39,.575,.565,1) both;
    }}
    .metric:hover {{
      transform: translateY(-3px);
      box-shadow: 0 6px 16px rgba(0,0,0,0.08);
    }}
    .metric h3 {{
      font-size: 1rem;
      margin-bottom: 0.75rem;
      color: var(--muted);
      font-weight: 500;
    }}
    .metric .value {{
      font-size: 2rem;
      font-weight: 600;
    }}
    .metric .value.perf-good,
    .metric .value.perf-bad,
    .metric .value.perf-neutral {{
        background: none;
        padding: 0;
        display: block;
    }}
    .metric .value.perf-good {{ color: var(--success); }}
    .metric .value.perf-bad {{ color: var(--error); }}
    .metric .value.perf-neutral {{ color: var(--text); }}


    /* ── Highlights ─────────────────────────────────────────────────────── */
    .highlights {{
      padding: 2rem;
      background: var(--surface);
      text-align: center;
      animation: fadeInUp 1.7s 0.3s cubic-bezier(.39,.575,.565,1) both;
    }}
    .highlights h2 {{
      font-size: 1.5rem;
      margin-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.75rem;
      color: var(--text);
      font-weight: 600;
      text-align: center;
    }}
    .changes-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 2rem;
      justify-items: center;
    }}
    @media (min-width: 992px) {{
      .changes-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
    .change-section {{
      background: var(--bg);
      padding: 1.5rem;
      border-radius: 0.5rem;
      border: 1px solid var(--border);
      text-align: center;
    }}
    .change-section h3 {{
      font-size: 1.25rem;
      margin-bottom: 1rem;
      font-weight: 600;
      text-align: center;
    }}
    .comparison-block {{
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 2px solid var(--border);
    }}
    .comparison-block:last-child {{
      margin-bottom: 0;
      padding-bottom: 0;
      border-bottom: none;
    }}
    .comparison-header {{
      font-size: 1.35rem;
      font-weight: 600;
      color: var(--primary-dark);
      margin-bottom: 1.25rem;
      padding: 0.75rem 1rem;
      background: linear-gradient(90deg, var(--bg), transparent);
      border-left: 4px solid var(--primary);
      border-radius: 0 0.5rem 0.5rem 0;
    }}
    .comparison-metrics {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      justify-content: center;
    }}
    .mini-metric {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 0.75rem 1rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      min-width: 90px;
      min-height: 80px;
      box-shadow: var(--shadow-sm);
      transition: transform 0.15s, box-shadow 0.15s;
    }}
    .mini-metric:hover {{
      transform: translateY(-2px);
      box-shadow: var(--shadow);
    }}
    .mini-metric.perf-good {{
      border-color: var(--success);
      background: var(--success-bg);
      border-radius: 0.5rem;
    }}
    .mini-metric.perf-bad {{
      border-color: var(--error);
      background: var(--error-bg);
      border-radius: 0.5rem;
    }}
    .mini-icon {{ font-size: 1.1rem; margin-bottom: 0.25rem; }}
    .mini-value {{
      font-size: 1.1rem;
      font-weight: 600;
      color: var(--text);
    }}
    .mini-metric.perf-good .mini-value {{ color: var(--success); }}
    .mini-metric.perf-bad .mini-value {{ color: var(--error); }}
    .mini-label {{
      font-size: 0.75rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }}
    .change-item {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.75rem 0;
      border-bottom: 1px solid var(--border);
      font-size: 0.9rem;
      text-align: center;
      animation: fadeInUp 1.0s cubic-bezier(.39,.575,.565,1) both;
    }}
    .change-item:last-child {{ border-bottom: none; }}
    .change-function {{
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
      color: var(--primary-dark);
      word-break: break-all;
      padding-right: 1rem;
    }}
    .change-value {{ font-weight: bold; }}
    .change-values {{ text-align: right; flex-shrink: 0; }}
    .change-time-diff {{
      font-size: 0.8rem;
      color: var(--muted);
      display: block;
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    }}

    /* ── Table ─────────────────────────────────────────────────────────── */
    .table-container {{
      padding: 0 2rem 2rem;
      overflow-x: auto;
      background: var(--surface);
      text-align: center;
    }}
    .table-container h2 {{
      font-size: 1.5rem;
      margin-bottom: 1.5rem;
      font-weight: 600;
      text-align: center;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      margin-left: auto;
      margin-right: auto;
    }}
    caption {{
      caption-side: top;
      text-align: center;
      font-weight: bold;
      margin-bottom: 1rem;
      font-size: 1.1rem;
      color: var(--muted);
    }}
    th, td {{
      padding: 0.85rem 1rem;
      text-align: left;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
      min-width: 120px;
    }}
    td:first-child, th:first-child {{
        white-space: normal;
        word-break: break-all;
    }}
    thead th {{
      background: var(--bg);
      color: var(--muted);
      font-weight: 600;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      position: sticky;
      top: 0;
      z-index: 2;
      border-top: 1px solid var(--border);
    }}
    tbody tr {{
      /* Remove animation for normal rows */
    }}
    tbody tr:nth-child(even) {{
      background: #f6f8fa;
    }}
    tbody tr:nth-child(odd) {{
      background: #fff;
    }}
    tbody tr:hover {{
      background: #e3eaff;
    }}

    /* ── Table Group Headers ───────────────────────────────────────────── */
    .group-headers th {{
      text-align: center;
      vertical-align: middle;
      padding: 1rem 0.5rem;
      font-size: 1rem;
    }}
    .group-header {{
      border-bottom: 2px solid var(--border);
    }}
    .group-header em {{
      font-size: 0.85rem;
      opacity: 0.8;
    }}
    .baseline-group {{
      background: linear-gradient(180deg, #e3f2fd, #bbdefb);
      border-left: 3px solid #1976d2;
      border-right: 3px solid #1976d2;
    }}
    .compare-group {{
      background: linear-gradient(180deg, #fff3e0, #ffe0b2);
      border-left: 3px solid #f57c00;
      border-right: 3px solid #f57c00;
    }}
    .compare-group-2 {{
      background: linear-gradient(180deg, #f3e5f5, #e1bee7);
      border-left: 3px solid #7b1fa2;
      border-right: 3px solid #7b1fa2;
    }}
    .compare-group-3 {{
      background: linear-gradient(180deg, #e8f5e9, #c8e6c9);
      border-left: 3px solid #388e3c;
      border-right: 3px solid #388e3c;
    }}
    .col-headers th {{
      font-size: 0.8rem;
      padding: 0.5rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .col-baseline {{
      color: #1565c0;
    }}
    .col-compare {{
      color: #e65100;
    }}
    .col-compare-2 {{
      color: #6a1b9a;
    }}
    .col-compare-3 {{
      color: #2e7d32;
    }}
    .col-function {{
      text-align: left;
      max-width: 300px;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .col-diff {{
      text-align: center;
    }}
    .group-sep {{
      border-right: 3px solid var(--border) !important;
    }}
    .col-headers th.group-sep {{
      border-right: 3px solid var(--primary) !important;
    }}
    .count-value {{
      text-align: center;
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    }}

    /* ── Performance Labels ────────────────────────────────────────────── */
    .perf-good, .perf-bad, .perf-neutral, .perf-warning, .perf-missing, .perf-new {{
      padding: 0.25rem 0.5rem;
      border-radius: 999px;
      display: inline-block;
      font-weight: 500;
      font-size: 0.85rem;
      text-align: center;
    }}
    .perf-good {{ background: var(--success-bg); color: var(--success); }}
    .perf-bad {{ background: var(--error-bg); color: var(--error); }}
    .perf-neutral {{ color: var(--muted); background: #f8f9fa; }}

    /* Time value cells with performance coloring */
    td.time-value.perf-good {{ background: var(--success-bg); color: var(--success); font-weight: 600; }}
    td.time-value.perf-bad {{ background: var(--error-bg); color: var(--error); font-weight: 600; }}
    td.time-value.perf-neutral {{ background: #f8f9fa; }}
    .perf-warning {{ color: #856404; background: #fff3cd; }}
    .perf-missing {{ color: var(--missing-text); font-style: italic; background: #f8f9fa; }}
    .perf-new {{ color: #0277bd; background: #e1f5fe; font-weight: 600; }}
    .delta-time {{ font-size: 0.85em; margin-right: 0.3em; white-space: nowrap; }}
    .measure-time {{ font-size: 0.8em; color: var(--muted); white-space: nowrap; font-style: italic; }}
    .time-value {{
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 0.9rem;
    }}
  </style>
</head>
<body>
  <a href="#main-content" class="skip-nav">Skip to main content</a>

  <div class="container">
    <header>
      <h1>Tracy Performance Comparison Report</h1>
      <p class="subtitle">Generated on {generation_date}</p>
      <div class="files-info">{files_info}</div>
    </header>

    <main id="main-content">
      <section class="summary" aria-labelledby="summary-heading">
        <h2 id="summary-heading" hidden>Summary Metrics</h2>
        <div class="metric">
          <h3>📊 Functions Analyzed</h3>
          <div class="value neutral">{total_functions}</div>
        </div>
        <div class="metric">
          <h3>⚡ Significant Changes</h3>
          <div class="value {overall_class}">{significant_changes}</div>
        </div>
        <div class="metric">
          <h3>📈 Avg Performance</h3>
          <div class="value {avg_perf_class}">{avg_performance}</div>
        </div>
      </section>

      <section class="highlights" aria-labelledby="highlights-heading">
        <h2 id="highlights-heading">🎯 Most Significant Changes</h2>
        {significant_changes_content}
      </section>

      <section class="table-container" aria-labelledby="table-heading">
        <h2 id="table-heading">📋 Detailed Function Comparison</h2>
        <table id="comparison-table">
          {comparison_table}
        </table>
      </section>
    </main>
  </div>
  <script>
    // Enhanced table sort for the comparison table: handles time units and delta columns
    document.addEventListener('DOMContentLoaded', function() {{
      const table = document.getElementById('comparison-table');
      if (!table) return;
      const ths = table.querySelectorAll('thead tr.col-headers th');
      ths.forEach((th, idx) => {{
        th.style.cursor = 'pointer';
        th.title = 'Click to sort';
        th.addEventListener('click', function() {{
          const tbody = table.querySelector('tbody');
          const rows = Array.from(tbody.querySelectorAll('tr'));
          const asc = th.classList.toggle('sorted-asc');
          ths.forEach(other => {{ if (other !== th) other.classList.remove('sorted-asc', 'sorted-desc'); }});
          th.classList.toggle('sorted-desc', !asc);
          function parseTime(str) {{
            str = str.replace(/<[^>]*>/g, '').replace(/\xa0/g, ' ').trim();
            if (!str || str === 'N/A') return NaN;
            const m = str.match(/^([+-]?\d+(?:\.\d+)?)\s*([a-zµμ]+)$/i);
            if (!m) return NaN;
            let val = parseFloat(m[1]);
            let unit = m[2].toLowerCase();
            if (unit === 'ns') return val;
            if (unit === 'µs' || unit === 'μs' || unit === 'us') return val * 1e3;
            if (unit === 'ms') return val * 1e6;
            if (unit === 's') return val * 1e9;
            return NaN;
          }}
          rows.sort((a, b) => {{
            // First try data-cmp-ns for actual time value sorting (comparison columns)
            let aCmp = a.children[idx].querySelector('[data-cmp-ns]');
            let bCmp = b.children[idx].querySelector('[data-cmp-ns]');
            if (aCmp && bCmp) {{
              let aVal = parseFloat(aCmp.getAttribute('data-cmp-ns'));
              let bVal = parseFloat(bCmp.getAttribute('data-cmp-ns'));
              if (!isNaN(aVal) && !isNaN(bVal)) {{
                return asc ? aVal - bVal : bVal - aVal;
              }}
            }}
            // Fallback to data-delta-ns for delta-only columns
            let aDelta = a.children[idx].querySelector('[data-delta-ns]');
            let bDelta = b.children[idx].querySelector('[data-delta-ns]');
            if (aDelta && bDelta) {{
              let aVal = parseFloat(aDelta.getAttribute('data-delta-ns'));
              let bVal = parseFloat(bDelta.getAttribute('data-delta-ns'));
              if (!isNaN(aVal) && !isNaN(bVal)) {{
                return asc ? aVal - bVal : bVal - aVal;
              }}
            }}
            let aText = a.children[idx].innerText.trim();
            let bText = b.children[idx].innerText.trim();
            let aTime = parseTime(aText);
            let bTime = parseTime(bText);
            if (!isNaN(aTime) && !isNaN(bTime)) {{
              return asc ? aTime - bTime : bTime - aTime;
            }}
            let aNum = parseFloat(aText.replace(/[^\d.-]+/g, ''));
            let bNum = parseFloat(bText.replace(/[^\d.-]+/g, ''));
            if (!isNaN(aNum) && !isNaN(bNum)) {{
              return asc ? aNum - bNum : bNum - aNum;
            }}
            return asc ? aText.localeCompare(bText) : bText.localeCompare(aText);
          }});
          rows.forEach(row => tbody.appendChild(row));
        }});
      }});
    }});
  </script>
</body>
</html>"""
