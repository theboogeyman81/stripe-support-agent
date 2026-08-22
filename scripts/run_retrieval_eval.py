"""Run Recall@k and MRR evaluation against the golden dataset."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import Settings
from src.eval.retrieval_metrics import recall_at_k, reciprocal_rank
from src.rag.vectorstore import retrieve

DATASET_PATH = Path("data/golden_dataset.jsonl")
RESULTS_PATH = Path("data/retrieval_results.json")


def _load_dataset(path: Path) -> list[dict]:
    """Load and return records from a JSONL file."""
    if not path.exists():
        print(f"Error: dataset not found: {path}")
        sys.exit(1)
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def run_eval(dataset_path: Path, top_k: int) -> None:
    """Run retrieval evaluation and write results to disk."""
    records = _load_dataset(dataset_path)
    Settings()  # validate config early

    recalls: list[float] = []
    rrs: list[float] = []
    skipped = 0

    print(f"Evaluating retrieval for {len(records)} items (top_k={top_k})...")
    for i, rec in enumerate(records, 1):
        question = rec["question"]
        ideal_urls = rec["ideal_urls"]
        print(f"  [{i}/{len(records)}] {question[:60]}...")

        try:
            chunks = retrieve(question, top_k=top_k)
        except Exception as exc:
            print(f"    WARNING: retrieve() failed ({exc}) — skipping")
            skipped += 1
            continue

        doc_urls = [c["doc_url"] for c in chunks]
        recalls.append(recall_at_k(doc_urls, ideal_urls))
        rrs.append(reciprocal_rank(doc_urls, ideal_urls))

    if not recalls:
        print("Error: no items could be evaluated.")
        sys.exit(1)

    mean_recall = sum(recalls) / len(recalls)
    mean_mrr = sum(rrs) / len(rrs)

    print("\n--- Results ---")
    print(f"  recall_at_{top_k}      {mean_recall:.4f}")
    print(f"  mrr              {mean_mrr:.4f}")
    print(f"  items_evaluated  {len(recalls)}")
    print(f"  items_skipped    {skipped}")

    output = {
        "recall_at_k": mean_recall,
        "mrr": mean_mrr,
        "k": top_k,
        "items_evaluated": len(recalls),
        "items_skipped": skipped,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    RESULTS_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nResults written to {RESULTS_PATH}")


def main() -> None:
    """Entry point for the retrieval evaluation script."""
    parser = argparse.ArgumentParser(
        description="Run Recall@k and MRR eval over golden dataset"
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DATASET_PATH,
        help="Path to golden_dataset.jsonl",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve per question (default: 5)",
    )
    args = parser.parse_args()
    run_eval(args.path, args.top_k)


if __name__ == "__main__":
    main()
