# stripe-support-agent

A production-grade LLM customer support agent answering questions from Stripe's documentation, built with the full LLMOps stack — RAG, agents, observability, evaluation, caching, and guardrails.

> Status: 🚧 Phase 1 in progress — basic CLI RAG pipeline.

## Why this exists

A learning project to go end-to-end on what it takes to ship an LLM system in production — not just call an API, but trace it, evaluate it, cache it, guard it, and deploy it. Stripe docs are the corpus because they're large, well-structured, and a believable real-world support use case.

## Architecture (target)
User question
│
▼
[Guardrails: input validation] ──► reject if unsafe
│
▼
[Semantic cache] ──► return cached answer if similar question seen
│
▼
[Retriever] ──► Voyage embeddings ──► Qdrant top-k search
│
▼
[Agent] ──► Gemini 2.5 Flash + tools (search, calculator, create_ticket)
│
▼
[Guardrails: output validation] ──► block hallucinations / off-topic
│
▼
Answer + cited sources
(Every step traced in Langfuse, evaluated nightly with Ragas, cost-tracked per request)

## Tech stack

| Layer            | Tool                                |
|------------------|-------------------------------------|
| Language         | Python 3.11+                        |
| LLM              | Gemini 2.5 Flash                    |
| Embeddings       | Voyage AI (`voyage-3-lite`)         |
| Vector DB        | Qdrant (self-hosted, Docker)        |
| Agent framework  | Pydantic AI                         |
| API              | FastAPI (later phases)              |
| Observability    | Langfuse (self-hosted)              |
| Evaluation       | Ragas + custom LLM-as-judge         |
| Caching          | Redis (semantic cache)              |
| Storage          | Postgres                            |
| Deployment       | Docker, Fly.io, GitHub Actions      |
| Tooling          | uv, ruff, pytest                    |

## Phase roadmap

- [ ] **Phase 1** — CLI RAG over Stripe docs (in progress)
- [ ] Phase 2 — FastAPI wrapper + structured logging
- [ ] Phase 3 — Agent with tool use
- [ ] Phase 4 — Observability with Langfuse
- [ ] Phase 5 — Evaluation pipeline (Ragas + custom evals)
- [ ] Phase 6 — Semantic caching + cost tracking
- [ ] Phase 7 — Guardrails + fallback chains
- [ ] Phase 8 — Deployment + CI/CD

Each phase has its own `PHASE_N.md` with goal, components, and exit checklist.

## Getting started (Phase 1)

### Prerequisites

- Python 3.11+
- Docker + Docker Compose
- `uv` (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- API keys: [Gemini](https://aistudio.google.com/apikey), [Voyage AI](https://www.voyageai.com/)

### Setup

```bash
# Clone
git clone https://github.com/<you>/stripe-support-agent.git
cd stripe-support-agent

# Install deps
uv sync

# Environment
cp .env.example .env
# Fill in GEMINI_API_KEY, VOYAGE_API_KEY

# Start Qdrant
docker compose up -d

# Ingest Stripe docs (Phase 1 — not yet implemented)
uv run python -m src.ingest

# Ask a question (Phase 1 — not yet implemented)
uv run python -m src.ask "How do I refund a payment?"
```

## Project layout
src/
rag/
loader.py       # fetch + parse Stripe llms-full.txt
chunker.py      # split docs into retrieval units
embedder.py     # Voyage AI client
vectorstore.py  # Qdrant wrapper
generator.py    # Gemini prompt + generation
config.py         # settings via pydantic-settings
ingest.py         # CLI: load → chunk → embed → upsert
ask.py            # CLI: question → retrieve → generate
tests/
data/               # ingested docs (gitignored)
docker-compose.yml
pyproject.toml
PLAN.md             # project-level plan
PHASE_1.md          # current phase plan
LEARNINGS.md        # surprises, bugs, decisions

## Working notes

- `PLAN.md` — high-level project plan (written before code)
- `PHASE_N.md` — per-phase scope and components
- `LEARNINGS.md` — running log of what surprised me, what broke, what I'd do differently
- Claude Code is the implementation tool. Architecture and reviews are human-driven.

## Cost target

< $5/month. Free tiers cover almost everything; only Gemini token usage is variable.

## License

MIT