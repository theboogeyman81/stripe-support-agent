"""Write eval score summary as a markdown table to stdout."""

import argparse
import json
from pathlib import Path

# Maps result filename → list of (result_key, threshold_key) pairs.
METRICS = [
    ("retrieval_results.json", [
        ("recall_at_k", "recall_at_k"),
        ("mrr", "mrr"),
    ]),
    ("ragas_results.json", [
        ("faithfulness", "faithfulness"),
        ("context_precision", "context_precision"),
        ("answer_relevancy", "answer_relevancy"),
    ]),
    ("judge_results.json", [
        ("mean_tool_choice", "mean_tool_choice"),
        ("mean_tone", "mean_tone"),
    ]),
]


def _load_results(data_dir: Path) -> dict[str, dict | None]:
    """Load each result file; return None for files that are absent."""
    out: dict[str, dict | None] = {}
    for filename, _ in METRICS:
        path = data_dir / filename
        out[filename] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        )
    return out


def build_rows(
    results: dict[str, dict | None],
    thresholds: dict,
) -> list[dict]:
    """Build table rows from pre-loaded result dicts and thresholds."""
    rows: list[dict] = []
    for filename, metric_pairs in METRICS:
        data = results.get(filename)
        for result_key, threshold_key in metric_pairs:
            threshold = thresholds[threshold_key]
            if data is None or result_key not in data:
                rows.append({
                    "metric": result_key,
                    "score": None,
                    "threshold": threshold,
                    "status": "—",
                })
            else:
                score = float(data[result_key])
                rows.append({
                    "metric": result_key,
                    "score": score,
                    "threshold": threshold,
                    "status": "PASS" if score >= threshold else "FAIL",
                })
    return rows


def format_table(rows: list[dict]) -> str:
    """Return a markdown table string for the given rows."""
    lines = [
        "## Eval Results",
        "",
        "| Metric | Score | Threshold | Status |",
        "|--------|-------|-----------|--------|",
    ]
    for row in rows:
        score_str = f"{row['score']:.4f}" if row["score"] is not None else "N/A"
        thr = row["threshold"]
        lines.append(f"| {row['metric']} | {score_str} | {thr:.2f} | {row['status']} |")
    return "\n".join(lines)


def main() -> None:
    """Write eval score summary to stdout."""
    parser = argparse.ArgumentParser(
        description="Write eval score summary as markdown to stdout"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing result JSON files (default: data/)",
    )
    args = parser.parse_args()

    thresholds = json.loads(
        (args.data_dir / "eval_thresholds.json").read_text(encoding="utf-8")
    )
    results = _load_results(args.data_dir)
    rows = build_rows(results, thresholds)
    print(format_table(rows))


if __name__ == "__main__":
    main()
