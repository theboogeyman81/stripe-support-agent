"""Tests for src/rag/loader.py — no network calls."""

import json

import pytest

from src.rag.loader import parse_llms_txt, save_jsonl

# Mimics the assembled format produced by fetch_all_docs.
# Three docs: two valid, one with content too short to keep.
SAMPLE_RAW = """\
<!-- stripe-doc-start: https://docs.stripe.com/testing.md -->
# Testing

Simulate payments to test your integration.

## How to use test cards

When you work with a test card, use test API keys in all API calls.
This is true whether you're serving a payment form to test interactively
or writing test code.

<!-- stripe-doc-start: https://docs.stripe.com/api.md -->
# API Reference

The Stripe API is organized around REST. Our API has predictable
resource-oriented URLs, accepts form-encoded request bodies, returns
JSON-encoded responses, and uses standard HTTP response codes,
authentication, and verbs.

<!-- stripe-doc-start: https://docs.stripe.com/stub.md -->
# Stub

"""


def test_yields_correct_count():
    docs = list(parse_llms_txt(SAMPLE_RAW))
    # stub.md body is only the title line (< 50 chars after strip) → dropped
    assert len(docs) == 2


def test_first_record_fields():
    docs = list(parse_llms_txt(SAMPLE_RAW))
    first = docs[0]
    assert first["url"] == "https://docs.stripe.com/testing.md"
    assert first["title"] == "Testing"
    assert "test API keys" in first["content"]


def test_content_includes_title_line():
    docs = list(parse_llms_txt(SAMPLE_RAW))
    assert docs[0]["content"].startswith("# Testing")


def test_drops_short_content():
    docs = list(parse_llms_txt(SAMPLE_RAW))
    urls = [d["url"] for d in docs]
    assert "https://docs.stripe.com/stub.md" not in urls


def test_save_jsonl_writes_and_returns_count(tmp_path):
    records = [
        {"url": "https://docs.stripe.com/a.md", "title": "A", "content": "body a"},
        {"url": "https://docs.stripe.com/b.md", "title": "B", "content": "body b"},
    ]
    out = tmp_path / "out.jsonl"
    n = save_jsonl(records, out)

    assert n == 2
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["url"] == "https://docs.stripe.com/a.md"
    assert first["title"] == "A"
