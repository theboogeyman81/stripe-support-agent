# Plan: 01 — Project Scaffold

## Context
The repo is empty (only `.claude/specs/` exists). Every later phase (loader,
chunker, embedder, retriever, generator) requires a working Python environment,
a local Qdrant instance, and a clean secrets strategy. This plan bootstraps all
of that — no business logic is introduced.

The spec lives at `.claude/specs/01-project-scafflod.md` (note: typo in
filename — "scafflod" — keep as-is, do not rename).

---

## Ambiguities & Resolutions

| Ambiguity | Resolution |
|---|---|
| `uv init` vs. hand-crafting `pyproject.toml` | Write `pyproject.toml` directly; `uv init` creates noise (README, hello.py). `uv sync` is the acceptance criterion, not `uv init`. |
| `src/` as a package vs. PEP 517 src-layout | Treat `src/` as a plain Python package (with `__init__.py`). The acceptance criterion imports `from src.config import Settings`, confirming flat package style. |
| `pytest` / `ruff` placement | Place in `[dependency-groups] dev` (PEP 735, natively supported by uv ≥ 0.4). |
| `src/__init__.py` content | One-line docstring only (consistent with stub convention). |
| `.gitignore` — file listed as missing | Create fresh; spec defines scope (Python + `.env` + `data/`). |
| Root files (README, PLAN, etc.) — listed as present but missing | Do not create them; they are out of scope for this spec. |

---

## Files Created

| Path | Purpose |
|---|---|
| `pyproject.toml` | uv project manifest + ruff config |
| `.gitignore` | Python / .env / data exclusions |
| `.env.example` | Documents required env vars (no values) |
| `docker-compose.yml` | Qdrant v1.12.4 with named volume |
| `LEARNINGS.md` | Phase 1 notes placeholder |
| `src/__init__.py` | Package marker |
| `src/config.py` | Pydantic-settings `Settings` class |
| `src/ingest.py` | Stub |
| `src/ask.py` | Stub |
| `src/rag/__init__.py` | Sub-package marker |
| `src/rag/loader.py` | Stub |
| `src/rag/chunker.py` | Stub |
| `src/rag/embedder.py` | Stub |
| `src/rag/vectorstore.py` | Stub |
| `src/rag/generator.py` | Stub |
| `tests/__init__.py` | Test package marker |

## Files Modified
None — all files are new.

---

## Verification

```bash
uv sync --all-groups
docker compose up -d
curl http://localhost:6333
echo "GEMINI_API_KEY=test\nVOYAGE_API_KEY=test" > .env
uv run python -c "from src.config import Settings; print(Settings())"
uv run pytest
uv run ruff check src/
```
