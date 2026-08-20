"""Validate data/golden_dataset.jsonl against the expected schema."""

import argparse
import json
import re
import sys
from pathlib import Path

_ID_RE = re.compile(r"^q\d{3}$")
_REQUIRED = {"id", "question", "reference_answer", "ideal_urls"}


def validate_records(lines: list[str]) -> tuple[int, list[str]]:
    """Parse and validate JSONL lines; return (total_items, errors)."""
    errors: list[str] = []
    seen_ids: dict[str, int] = {}
    total = 0
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        total += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {lineno}: invalid JSON — {exc}")
            continue
        missing = _REQUIRED - rec.keys()
        if missing:
            errors.append(f"line {lineno}: missing fields {sorted(missing)}")
            continue
        rid = rec.get("id", "")
        if not isinstance(rid, str) or not _ID_RE.match(rid):
            errors.append(f"line {lineno}: id {rid!r} must match q<NNN>")
        if rid in seen_ids:
            errors.append(
                f"line {lineno}: duplicate id {rid!r} "
                f"(first seen line {seen_ids[rid]})"
            )
        else:
            seen_ids[rid] = lineno
        for field in ("question", "reference_answer"):
            val = rec.get(field, "")
            if not isinstance(val, str) or not val.strip():
                errors.append(f"line {lineno}: {field!r} must be a non-empty string")
        urls = rec.get("ideal_urls", [])
        if not isinstance(urls, list) or not (1 <= len(urls) <= 3):
            errors.append(f"line {lineno}: 'ideal_urls' must be a list of 1–3 items")
    return total, errors


def main() -> None:
    """Entry point: validate the dataset file and exit 0/1."""
    parser = argparse.ArgumentParser(description="Validate golden_dataset.jsonl")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("data/golden_dataset.jsonl"),
        help="Path to the JSONL file (default: data/golden_dataset.jsonl)",
    )
    args = parser.parse_args()
    if not args.path.exists():
        print(f"Error: file not found: {args.path}")
        sys.exit(1)
    lines = args.path.read_text(encoding="utf-8").splitlines()
    total, errors = validate_records(lines)
    if errors:
        for err in errors:
            print(f"  ERROR: {err}")
        print(f"\n{total} items checked, {len(errors)} error(s) found.")
        sys.exit(1)
    print(f"OK: {total} items, all valid.")


if __name__ == "__main__":
    main()
