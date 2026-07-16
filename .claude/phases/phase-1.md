# Phase 1 — CLI RAG over Stripe docs

## Goal
A working CLI that answers Stripe questions using RAG over Stripe's docs,
with cited sources and per-query cost printed.

## Features
1. `project-scaffold` — uv, ruff, pytest, Qdrant via docker-compose, src/ layout
2. `docs-loader` — fetch and parse `llms-full.txt` → `data/stripe_docs.jsonl`
3. `chunker` — recursive character split, token-aware → `data/stripe_chunks.jsonl`
4. `embedder` — Voyage AI, resume-safe → `data/stripe_embeddings.jsonl`
5. `vectorstore` — Qdrant ingest + `retrieve(query, top_k)`
6. `generator-and-cli` — Gemini generation + `ask.py "..."` entry point

## What you'll learn
- Chunking strategies and their failure modes
- Embedding spaces, cosine similarity, and query vs document input types
- Qdrant collection design, HNSW basics, payload storage
- RAG prompt construction and citation prompting
- Token accounting and per-request cost estimation

## Exit checklist
- [ ] `docker compose up -d` brings up Qdrant
- [ ] `uv run python -m src.ingest` runs full pipeline
- [ ] `uv run python -m src.ask "How do I create a refund?"` returns a coherent
      answer citing at least one Stripe URL
- [ ] Per-query cost printed (input tokens, output tokens, $ estimate)
- [ ] At least 5 test queries tried; results logged in `LEARNINGS.md`
- [ ] `uv run pytest` all green
- [ ] `uv run ruff check src/` clean
- [ ] Monthly cost projection recorded in `LEARNINGS.md`