"""Run LLM-as-judge evaluation over the golden dataset."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.agent.agent import run_agent
from src.config import Settings
from src.eval.judge import (
    build_judge_client,
    extract_tool_calls,
    score_tone,
    score_tool_choice,
)

DATASET_PATH = Path("data/golden_dataset.jsonl")
RESULTS_PATH = Path("data/judge_results.json")
JUDGE_MODEL = "gemini-2.5-flash"

# Cost estimate: 1 agent call (~8 LLM calls) + 2 judge calls per item.
_AGENT_INPUT_PER_ITEM = 8 * 1_000
_AGENT_OUTPUT_PER_ITEM = 8 * 150
_JUDGE_CALLS = 2
_JUDGE_INPUT_PER_CALL = 600
_JUDGE_OUTPUT_PER_CALL = 80
_INPUT_PRICE_PER_M = 0.30
_OUTPUT_PRICE_PER_M = 2.50

_AGENT_COST_PER_ITEM = (
    (_AGENT_INPUT_PER_ITEM / 1_000_000) * _INPUT_PRICE_PER_M
    + (_AGENT_OUTPUT_PER_ITEM / 1_000_000) * _OUTPUT_PRICE_PER_M
)
_JUDGE_COST_PER_ITEM = (
    (_JUDGE_CALLS * _JUDGE_INPUT_PER_CALL / 1_000_000) * _INPUT_PRICE_PER_M
    + (_JUDGE_CALLS * _JUDGE_OUTPUT_PER_CALL / 1_000_000) * _OUTPUT_PRICE_PER_M
)
_COST_PER_ITEM = _AGENT_COST_PER_ITEM + _JUDGE_COST_PER_ITEM


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
    print(
        f"Estimated cost: ${estimated:.2f} USD  "
        f"({n_items} items × 1 agent + {_JUDGE_CALLS} judge calls each, upper bound)"
    )
    if yes:
        return
    answer = input("Proceed? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)


def run_eval(dataset_path: Path, yes: bool) -> None:
    """Run the full judge evaluation pipeline and write results to disk."""
    records = _load_dataset(dataset_path)
    _confirm_cost(len(records), yes)

    settings = Settings()
    judge_client = build_judge_client(settings)

    items: list[dict] = []
    skipped = 0
    generate_cost = 0.0
    judge_cost = 0.0

    print(f"\nRunning pipeline for {len(records)} items...")
    for i, rec in enumerate(records, 1):
        question = rec["question"]
        rec_id = rec["id"]
        print(f"  [{i}/{len(records)}] {question[:60]}...")

        try:
            result = run_agent(question, settings)
        except Exception as exc:
            print(f"    WARNING: run_agent() failed ({exc}) — skipping")
            skipped += 1
            continue

        generate_cost += result["cost_usd"]
        tools_called = extract_tool_calls(result["message_history"])
        answer = result["answer"]

        tc = score_tool_choice(
            question, tools_called, answer, judge_client, JUDGE_MODEL
        )
        tone = score_tone(question, answer, judge_client, JUDGE_MODEL)
        judge_cost += _JUDGE_COST_PER_ITEM

        items.append(
            {
                "id": rec_id,
                "question": question,
                "tools_called": tools_called,
                "answer": answer,
                "tool_choice_score": tc["score"],
                "tone_score": tone["score"],
                "tool_choice_rationale": tc["rationale"],
                "tone_rationale": tone["rationale"],
            }
        )

    if not items:
        print("Error: no items could be evaluated.")
        sys.exit(1)

    mean_tc = sum(it["tool_choice_score"] for it in items) / len(items)
    mean_tone_val = sum(it["tone_score"] for it in items) / len(items)

    print("\n--- Results ---")
    print(f"  tool_choice         {mean_tc:.4f}")
    print(f"  tone                {mean_tone_val:.4f}")
    print(f"  items_evaluated     {len(items)}")
    print(f"  items_skipped       {skipped}")
    print(f"  generate_cost_usd   {generate_cost:.4f}")
    print(f"  judge_cost_usd      {judge_cost:.4f}")

    output = {
        "items": items,
        "mean_tool_choice": mean_tc,
        "mean_tone": mean_tone_val,
        "items_evaluated": len(items),
        "items_skipped": skipped,
        "generate_cost_usd": generate_cost,
        "judge_cost_usd": judge_cost,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    RESULTS_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nResults written to {RESULTS_PATH}")


def main() -> None:
    """Entry point for the LLM-as-judge evaluation script."""
    parser = argparse.ArgumentParser(
        description="Run LLM-as-judge eval over golden dataset"
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
        help="Accepted for CLI parity; agent retrieval is configured internally",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the cost confirmation prompt",
    )
    args = parser.parse_args()
    run_eval(args.path, args.yes)


if __name__ == "__main__":
    main()
