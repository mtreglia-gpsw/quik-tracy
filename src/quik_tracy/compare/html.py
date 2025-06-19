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
NS, US, MS, S = 1, 1_000, 1_000_000, 1_000_000_000  # 1 ns, 1 µs, 1 ms, 1 s
SUB_100_MS = 100 * MS


def _human_time(ns: float | pd.NA) -> str:
    if pd.isna(ns):
        return "<span class='perf-missing'>N/A</span>"
    US, MS, S = 1_000, 1_000_000, 1_000_000_000
    if ns < 0:
        ns = abs(ns)
    if ns < US:
        return f"{ns:.0f}\u00a0ns"
    if ns < MS:
        return f"{ns / US:.1f}\u00a0µs"
    if ns < S:
        return f"{ns / MS:.1f}\u00a0ms"
    return f"{ns / S:.2f}\u00a0s"


def _fmt_pct(p: float | pd.NA, base_ns: float | pd.NA = pd.NA, cmp_ns: float | pd.NA = pd.NA) -> str:
    if pd.isna(p):
        return "<span class='perf-missing'>N/A</span>"

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
    if pd.notna(base_ns) and pd.notna(cmp_ns):
        delta_ns = cmp_ns - base_ns
        human_delta = _human_time(delta_ns)
        delta_attr = f" data-delta-ns='{delta_ns}'"
        # Show percent and time delta on separate lines for clarity
        delta_str = f"<br><span class='delta-time'>{human_delta}</span>"
    else:
        delta_attr = ""
        delta_str = ""
    return f"<span class='{cls}'{delta_attr}>{sign}{p:.1f}%{delta_str}</span>"


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

    def _table(self, df: pd.DataFrame, baseline: str) -> str:
        """Return a fully styled HTML <table>."""

        def _header_text(col: str) -> str:
            mapping = {
                "function_name": "Function Name",
                "avg_time": "Avg",
                "min_time": "Min",
                "max_time": "Max",
                "call_count": "Calls",
                "avg_perf_diff": "Avg Δ%",
                "min_perf_diff": "Min Δ%",
                "max_perf_diff": "Max Δ%",
            }
            for key, txt in mapping.items():
                if col.endswith(key):
                    if baseline in col:
                        return txt.replace("Avg", "Baseline Avg") if "Avg" in txt else txt.replace(" ", " Baseline ")
                    if any(col.endswith(f"_{suffix}") for suffix in ("avg_time", "min_time", "max_time", "call_count")):
                        return txt.replace("Avg", "Compare Avg") if "Avg" in txt else txt.replace(" ", " Compare ")
                    return txt
            return col  # fallback

        header_row = "".join(f"<th>{_header_text(c)}</th>" for c in df.columns)

        body_rows: list[str] = []
        for _, row in df.iterrows():
            cells: list[str] = []
            for col, val in row.items():
                if col == "function_name":
                    cells.append(f"<td><strong>{val}</strong></td>")
                elif "perf_diff" in col:
                    metric = col.replace("_perf_diff", "_time")
                    base_ns = row.get(metric.replace(col.split("_")[0], baseline), pd.NA)
                    cmp_ns = row.get(metric, pd.NA)
                    cells.append(f"<td>{_fmt_pct(val, base_ns, cmp_ns)}</td>")
                elif "time" in col:
                    cells.append(f"<td class='time-value'>{_human_time(val)}</td>")
                else:
                    cells.append(f"<td>{val if pd.notna(val) else '-'}</td>")
            body_rows.append("<tr>" + "".join(cells) + "</tr>")

        return f"<thead><tr>{header_row}</tr></thead><tbody>{''.join(body_rows)}</tbody>"

    def _significant_changes(self, top_changes: dict) -> str:
        """Render HTML for top improvements/regressions from precomputed dict."""
        improvs = top_changes.get("improvements", [])
        regs = top_changes.get("regressions", [])

        def _block(title: str, icon: str, data: list, cls: str) -> str:
            if not data:
                items = f"<p class='change-item'>No significant {title.lower().replace('top ', '')} found.</p>"
            else:
                item_html = []
                for r in data:
                    item_html.append(
                        f"""<div class='change-item'>
                        <span class='change-function'>{r['function_name']}</span>
                        <div class='change-values'>
                            <span class='change-value {cls}'>{{:+.1f}}% ({{}} {{}})</span>
                            <span class='change-time-diff'>{{}} → {{}}</span>
                        </div>
                    </div>""".format(
                            r["diff"],
                            _human_time(r["delta_ns"]),
                            "saved" if cls == "perf-good" else "lost",
                            _human_time(r["base"]),
                            _human_time(r["cmp"]),
                        )
                    )
                items = "".join(item_html)
            section_class = "improvements" if cls == "perf-good" else "regressions"
            return f"<div class='change-section {section_class}'>" f"<h3>{icon} {title}</h3>" f"{items}</div>"

        return (
            "<div class='changes-grid'>"
            + _block("Top 10 Improvements (by AVG time saved)", "🚀", improvs, "perf-good")
            + _block("Top 10 Regressions (by AVG time lost)", "⚠️", regs, "perf-bad")
            + "</div>"
        )

    def _render(self, df: pd.DataFrame, paths: Sequence[Path], summary: dict, top_changes: dict) -> str:
        ctx = {
            "total_functions": summary["total_functions"],
            "significant_changes": summary["significant_changes"],
            "avg_performance": f"{_human_time(summary['avg_performance']['human_diff'])} ({summary['avg_performance']['pct_diff']:+.1f}%)",
            "avg_perf_class": (
                "perf-good"
                if summary["avg_performance"]["pct_diff"] < -2
                else "perf-bad" if summary["avg_performance"]["pct_diff"] > 2 else "perf-neutral"
            ),
            "overall_class": (
                (
                    "perf-good"
                    if summary["avg_performance"]["pct_diff"] < -2
                    else "perf-bad" if summary["avg_performance"]["pct_diff"] > 2 else "perf-neutral"
                )
                if summary["significant_changes"]
                else "perf-neutral"
            ),
            "files_info": self._files_info(paths),
            "comparison_table": self._table(df, paths[0].stem),
            "significant_changes_content": self._significant_changes(top_changes),
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
    /* Separator after baseline column */
    th:nth-child(5), td:nth-child(5) {{ border-right: 2px solid var(--border); }}

    /* ── Performance Labels ────────────────────────────────────────────── */
    .perf-good, .perf-bad, .perf-neutral, .perf-warning, .perf-missing {{
      padding: 0.25rem 0.5rem;
      border-radius: 999px;
      display: inline-block;
      font-weight: 500;
      font-size: 0.85rem;
    }}
    .perf-good {{ background: var(--success-bg); color: var(--success); }}
    .perf-bad {{ background: var(--error-bg); color: var(--error); }}
    .perf-neutral {{ color: var(--muted); background: #f8f9fa; }}
    .perf-warning {{ color: #856404; background: #fff3cd; }}
    .perf-missing {{ color: var(--missing-text); font-style: italic; background: #f8f9fa; }}
    .delta-time {{ font-size: 0.85em; color: var(--muted); margin-left: 0.3em; white-space: nowrap; }}
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
      const ths = table.querySelectorAll('thead th');
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
            // Prefer data-delta-ns attribute for delta columns
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
