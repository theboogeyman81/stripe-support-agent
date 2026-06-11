# Spec 01 — Project Scaffold

## Feature
Set up the foundational project structure, dependencies, configuration, and
local infrastructure for the Stripe Support Agent. No business logic yet.

## Why
Every later feature (loader, chunker, embedder, retriever, generator) needs
a working Python environment, Qdrant running locally, and a clean way to
read secrets from .env. This feature unblocks all of them.

## Scope (in)
- Python project initialised with `uv` (Python 3.11+)
- `pyproject.toml` with Phase 1 dependencies only
- Linter/formatter config (`ruff`)
- Test framework (`pytest`) wired up
- `docker-compose.yml` running Qdrant locally with persistent volume
- `src/` layout with empty module stubs (docstring-only files)
- `src/config.py` with a pydantic-settings `Settings` class
- `.env.example` listing required keys (no values)
- `.gitignore` for Python + `.env` + `data/`
- A `LEARNINGS.md` placeholder with `## Phase 1` header

## Scope (out)
- Docs loading / chunking / embedding / retrieval / generation logic
- FastAPI server (later phase)
- Postgres, Redis, Langfuse (later phases)
- Tests for business logic (none exists yet)
- CI/CD (later phase)

## Dependencies (Phase 1 only)
- `google-genai` — Gemini SDK
- `voyageai` — Voyage AI embeddings
- `qdrant-client` — Qdrant Python client
- `httpx` — HTTP client (for docs loader, added now to avoid second install)
- `pydantic` + `pydantic-settings` — config
- `python-dotenv` — `.env` loading
- `pytest` — tests
- `ruff` — lint + format

## Environment variables
- `GEMINI_API_KEY` — required
- `VOYAGE_API_KEY` — required
- `QDRANT_URL` — defaults to `http://localhost:6333`

## Directory layout
src/
init.py
config.py
ingest.py            # stub
ask.py               # stub
rag/
init.py
loader.py          # stub
chunker.py         # stub
embedder.py        # stub
vectorstore.py     # stub
generator.py       # stub
tests/
init.py
data/                  # gitignored
.claude/
specs/
plans/
docker-compose.yml
pyproject.toml
.env.example
.gitignore
LEARNINGS.md

Each stub module is empty except for a one-line docstring describing
its eventual purpose.

## Qdrant configuration
- Image: `qdrant/qdrant:v1.12.4` (pinned, not `latest`)
- Ports: `6333:6333` (REST), `6334:6334` (gRPC)
- Volume: named volume `qdrant_storage` mounted at `/qdrant/storage`
- Restart policy: `unless-stopped`

## Acceptance criteria
- `uv sync` completes with no errors
- `docker compose up -d` starts Qdrant
- `curl http://localhost:6333` returns Qdrant version JSON
- `uv run python -c "from src.config import Settings; print(Settings())"`
  works once `.env` is populated
- `uv run pytest` runs (exits 0 with "no tests collected" — that's fine)
- `uv run ruff check src/` passes
- No business logic in any module — only docstrings

## Out-of-scope failure modes (do not handle yet)
- Qdrant unreachable at runtime — config loads regardless
- Missing API keys — config will raise at runtime; that's acceptable for Phase 1

## Notes
- Pin Qdrant version. `latest` will break this project in 6 months.
- `httpx` is added now even though it's only used by the loader, to keep
  this feature's dependency list aligned with what Phase 1 actually needs.