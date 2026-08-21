"""Run Ragas evaluation metrics over the golden dataset."""

import argparse
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
from ragas.metrics import answer_relevancy, context_precision, faithfulness

from src.config import Settings
from src.eval.ragas_llm import build_ragas_embeddings, build_ragas_llm
from src.rag.generator import generate
from src.rag.vectorstore import retrieve

logging.basicConfig(level=logging.WARNING)
warnings.filterwarnings("ignore")

DATASET_PATH = Path("data/golden_dataset.jsonl")
RESULTS_PATH = Path("data/ragas_results.json")

# Rough cost estimate: 1 generate() call + ~7 Ragas LLM calls per item,
# each averaging ~1 000 input + 150 output tokens.
_CALLS_PER_ITEM = 8
_INPUT_TOKENS_PER_CALL = 1_000
_OUTPUT_TOKENS_PER_CALL = 150
_INPUT_PRICE_PER_M = 0.30
_OUTPUT_PRICE_PER_M = 2.50
_COST_PER_ITEM = (
    (_CALLS_PER_ITEM * _INPUT_TOKENS_PER_CALL / 1_000_000) * _INPUT_PRICE_PER_M
    + (_CALLS_PER_ITEM * _OUTPUT_TOKENS_PER_CALL / 1_000_000) * _OUTPUT_PRICE_PER_M
)


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


def _confirm_cost(n_items: int, yes: bool) -> None:
    """Print estimated cost and prompt for confirmation unless --yes."""
    estimated = _COST_PER_ITEM * n_items
    print(f"Estimated cost: ${estimated:.2f} USD  "
          f"({n_items} items × ~{_CALLS_PER_ITEM} LLM calls each, upper bound)")
    if yes:
        return
    answer = input("Proceed? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)


def run_eval(dataset_path: Path, top_k: int, yes: bool) -> None:
    """Run the full evaluation pipeline and write results to disk."""
    records = _load_dataset(dataset_path)
    _confirm_cost(len(records), yes)

    settings = Settings()
    llm = build_ragas_llm(settings)
    embeddings = build_ragas_embeddings(settings)

    samples: list[SingleTurnSample] = []
    skipped = 0
    generate_cost = 0.0

    print(f"\nRunning pipeline for {len(records)} items...")
    for i, rec in enumerate(records, 1):
        question = rec["question"]
        reference = rec["reference_answer"]
        print(f"  [{i}/{len(records)}] {question[:60]}...")

        chunks = retrieve(question, top_k=top_k)
        if not chunks:
            print("    WARNING: no chunks retrieved — skipping")
            skipped += 1
            continue

        try:
            gen = generate(question, chunks)
        except Exception as exc:
            print(f"    WARNING: generate() failed ({exc}) — skipping")
            skipped += 1
            continue

        generate_cost += gen["cost_usd"]
        contexts = [c["text"] for c in chunks]
        samples.append(
            SingleTurnSample(
                user_input=question,
                retrieved_contexts=contexts,
                response=gen["answer"],
                reference=reference,
            )
        )

    if not samples:
        print("Error: no samples could be evaluated.")
        sys.exit(1)

    print(f"\nRunning Ragas metrics on {len(samples)} samples "
          f"({skipped} skipped)...")
    dataset = EvaluationDataset(samples=samples)
    result = evaluate(
        dataset,
        metrics=[faithfulness, context_precision, answer_relevancy],
        llm=llm,
        embeddings=embeddings,
    )

    scores = result.to_pandas()
    faith = float(scores["faithfulness"].mean())
    cp = float(scores["context_precision"].mean())
    ar = float(scores["answer_relevancy"].mean())

    print("\n--- Results ---")
    print(f"  faithfulness        {faith:.4f}")
    print(f"  context_precision   {cp:.4f}")
    print(f"  answer_relevancy    {ar:.4f}")
    print(f"  items_evaluated     {len(samples)}")
    print(f"  items_skipped       {skipped}")
    print(f"  generate_cost_usd   {generate_cost:.4f}")

    output = {
        "faithfulness": faith,
        "context_precision": cp,
        "answer_relevancy": ar,
        "items_evaluated": len(samples),
        "items_skipped": skipped,
        "generate_cost_usd": generate_cost,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    RESULTS_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nResults written to {RESULTS_PATH}")


def main() -> None:
    """Entry point for the Ragas evaluation script."""
    parser = argparse.ArgumentParser(description="Run Ragas eval over golden dataset")
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
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the cost confirmation prompt",
    )
    args = parser.parse_args()
    run_eval(args.path, args.top_k, args.yes)


if __name__ == "__main__":
    main()
