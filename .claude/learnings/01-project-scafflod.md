# Learnings: 01 — Project Scaffold

---

## uv

**What:** Python package + project manager (replaces pip + venv + pip-tools).
**Why:** Faster installs, single lockfile (`uv.lock`) for reproducibility, one tool for everything.
**How:** `uv sync --all-groups` reads `pyproject.toml`, resolves deps, creates `.venv/`, writes `uv.lock`. Run anything inside the venv with `uv run <cmd>`.

---

## pyproject.toml

**What:** Single config file for a Python project — replaces `setup.py`, `requirements.txt`, `setup.cfg`.
**Why:** One place for project metadata, dependencies, and tool config (ruff, pytest).
**How:**
- `[project]` → name, version, Python version, runtime deps
- `[dependency-groups] dev` → dev-only deps (pytest, ruff), installed with `--all-groups`, not shipped
- `[tool.ruff]` → linter config lives here too

---

## pydantic-settings

**What:** Reads env vars (and `.env` files) into a typed Python class.
**Why:** One place to declare all config; raises a clear error if a required key is missing.
**How:**
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    gemini_api_key: str          # required — errors if missing
    qdrant_url: str = "http://localhost:6333"  # optional — has default
```
`Settings()` auto-loads `.env` + real env vars. Import it wherever config is needed.

---

## .env / .env.example

**What:** `.env` holds real secrets (gitignored). `.env.example` is a committed template with blank values.
**Why:** Secrets never go in git. The example tells teammates exactly what keys they need.
**How:** Copy `.env.example` → `.env`, fill in real values. `pydantic-settings` picks it up automatically.

---

## docker-compose.yml

**What:** Declares local infrastructure as code — here, just Qdrant.
**Why:** One command (`docker compose up -d`) gives everyone the same local service, no manual installs.
**How:** Pinned image (`qdrant/qdrant:v1.12.4`) so it never breaks on a surprise upgrade. Named volume (`qdrant_storage`) means data survives container restarts. Ports `6333` (REST) and `6334` (gRPC) forwarded to localhost.

---

## Qdrant

**What:** A vector database — stores embeddings and finds nearest ones by similarity.
**Why:** The RAG pipeline needs fast "find the most relevant chunks for this query" lookups. That's what Qdrant does.
**How:** REST API at `http://localhost:6333`. Later phases upsert vectors here (embedder → vectorstore) and query them (retriever). `curl http://localhost:6333` returns version JSON to confirm it's up.

---

## ruff

**What:** Fast Python linter + formatter (replaces flake8 + isort + black).
**Why:** One tool, near-instant feedback, catches real bugs like undefined names and unused imports.
**How:** `uv run ruff check src/` to lint. `uv run ruff format src/` to format. Config in `[tool.ruff]` in `pyproject.toml`.

---

## pytest

**What:** Python test framework.
**Why:** Standard, zero-config discovery — `uv run pytest` finds and runs all `test_*.py` files.
**How:** No tests yet; exits 0 with "no tests collected" — intentional for Phase 1. Tests go in `tests/`.

---

## src/ layout

**What:** `src/` is a plain Python package (has `__init__.py`), not a PEP 517 src-layout.
**Why:** Imports read `from src.config import Settings` — so `src` is the importable package name.
**How:** Every subdir also gets `__init__.py` (e.g. `src/rag/`). Stub files are one-line docstrings only — no logic until their phase.

---

## Named Docker volume

**What:** `qdrant_storage` is a Docker-managed volume, not a bind-mount to a host folder.
**Why:** Data persists across `docker compose down` / `up` without caring about host paths.
**How:** Declared under `volumes:` at the bottom of `docker-compose.yml`. Docker manages where it lives on disk.
