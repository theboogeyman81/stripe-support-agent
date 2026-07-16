"""Ask entry point: takes a user question and returns a grounded answer."""

import argparse
import sys

from src.rag.generator import INPUT_PRICE_PER_M, OUTPUT_PRICE_PER_M, generate
from src.rag.vectorstore import retrieve

_EST_OUTPUT_TOKENS = 400
_EST_TOKENS_PER_CHUNK = 500
_PROMPT_OVERHEAD_TOKENS = 300


def main() -> None:
    """Retrieve relevant chunks, generate an answer, and print with sources and cost."""
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description="Ask a question about Stripe docs")
    parser.add_argument("question", help="Natural language question about Stripe")
    parser.add_argument(
        "--top-k", type=int, default=5, metavar="N",
        help="Number of chunks to retrieve (default: 5)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip cost confirmation prompt"
    )
    args = parser.parse_args()

    est_input_tokens = args.top_k * _EST_TOKENS_PER_CHUNK + _PROMPT_OVERHEAD_TOKENS
    est_cost = (
        (est_input_tokens / 1_000_000) * INPUT_PRICE_PER_M
        + (_EST_OUTPUT_TOKENS / 1_000_000) * OUTPUT_PRICE_PER_M
    )
    print(
        f"Estimated cost: ~${est_cost:.6f} "
        f"({est_input_tokens} in / {_EST_OUTPUT_TOKENS} out tokens, estimated)"
    )

    if not args.yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    hits = retrieve(args.question, top_k=args.top_k)
    result = generate(args.question, hits)

    print("\nAnswer:")
    print(result["answer"])

    seen_urls: set[str] = set()
    sources = []
    for hit in hits:
        if hit["doc_url"] not in seen_urls:
            seen_urls.add(hit["doc_url"])
            sources.append(hit)

    print("\nSources:")
    for i, src in enumerate(sources, 1):
        print(f"[{i}] {src['doc_title']} — {src['doc_url']}")

    print(f"\nTokens : {result['input_tokens']} in / {result['output_tokens']} out")
    print(f"Cost   : ${result['cost_usd']:.6f}")


if __name__ == "__main__":
    main()
