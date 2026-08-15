"""Compare current eval results against a committed baseline; exit 1 on regression."""

import argparse
import json
import sys
from pathlib import Path

from scripts.write_eval_summary import METRICS

BASELINE_FILE = "eval_baseline.json"
_COL = 22  # metric column width


def load_current(data_dir: Path) -> dict[str, float | None]:
    """Load all 7 metric values from result files; None for absent files/keys."""
    current: dict[str, float | None] = {}
    for filename, metric_pairs in METRICS:
        path = data_dir / filename
        if not path.exists():
            for result_key, _ in metric_pairs:
                current[result_key] = None
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            for result_key, _ in metric_pairs:
                val = data.get(result_key)
                current[result_key] = float(val) if val is not None else None
    return current


def check_regressions(
    current: dict[str, float | None],
    baseline: dict[str, float],
    delta: float,
) -> list[dict]:
    """Return one row per metric with status OK, REGRESSION, or SKIP."""
    rows: list[dict] = []
    for metric, base in baseline.items():
        cur = current.get(metric)
        if cur is None:
            rows.append({
                "metric": metric,
                "baseline": base,
                "current": None,
                "delta": None,
                "status": "SKIP",
            })
        else:
            diff = cur - base
            rows.append({
                "metric": metric,
                "baseline": base,
                "current": cur,
                "delta": diff,
                "status": "REGRESSION" if cur < base - delta else "OK",
            })
    return rows


def format_report(rows: list[dict]) -> str:
    """Return a fixed-width comparison table as a string."""
    header = (
        f"{'Metric':<{_COL}} {'Baseline':>8} {'Current':>8} {'Delta':>9}  Status"
    )
    sep = "-" * len(header)
    lines = [header, sep]
    for row in rows:
        cur_str = f"{row['current']:.4f}" if row["current"] is not None else "N/A"
        delta_str = f"{row['delta']:+.4f}" if row["delta"] is not None else "—"
        lines.append(
            f"{row['metric']:<{_COL}} {row['baseline']:>8.4f}"
            f" {cur_str:>8} {delta_str:>9}  {row['status']}"
        )
    return "\n".join(lines)


def main() -> None:
    """Run regression detection and exit 1 if any metric has regressed."""
    parser = argparse.ArgumentParser(
        description="Compare eval results against baseline; exit 1 on regression"
    )
    parser.add_argument(
        "--delta",
        type=float,
        default=0.05,
        help="Max score drop below baseline before flagging regression (default: 0.05)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing result and baseline JSON files (default: data/)",
    )
    args = parser.parse_args()

    baseline_path = args.data_dir / BASELINE_FILE
    if not baseline_path.exists():
        print(f"WARNING: {baseline_path} not found — skipping regression check")
        sys.exit(0)

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = load_current(args.data_dir)
    rows = check_regressions(current, baseline, args.delta)

    print(format_report(rows))

    regressions = [r for r in rows if r["status"] == "REGRESSION"]
    if regressions:
        print(f"\n{len(regressions)} regression(s) detected (delta: {args.delta})")
        sys.exit(1)

    skipped = [r for r in rows if r["status"] == "SKIP"]
    if skipped and len(skipped) == len(rows):
        print("\nWARNING: all metrics skipped — no result files found")
    else:
        print("\nNo regressions detected.")


if __name__ == "__main__":
    main()
