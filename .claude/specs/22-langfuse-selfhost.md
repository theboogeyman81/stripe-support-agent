# Spec 22 — Langfuse Setup (Cloud)

## Feature
Provision a Langfuse Cloud account, wire the three Langfuse credentials
(`public_key`, `secret_key`, `host`) into `Settings`, and document them in
`.env.example`. This is the infrastructure-only feature for Phase 4 — no SDK
code yet, no traces yet. The goal is to have Langfuse reachable and credentials
loadable from config so feature 23 (`langfuse-sdk-integration`) can build on
top without touching config again.

## Why
The original phase plan says "add to docker-compose, initialise Postgres schema"
but this machine has no Docker support (Windows 11 Home). Langfuse Cloud free
tier is the equivalent: Langfuse manages the backend, we get the same API
surface and UI, and setup takes two minutes. Same trade-off made for Qdrant
Cloud (feature 05) and Neon Postgres (feature 17).

Features 23–28 all assume a reachable Langfuse instance with credentials in
`Settings`. This feature provides that foundation.

## Input contract
- `src/config.py` — `Settings` class gains three new optional fields
- A Langfuse Cloud account (user action — see setup steps below)
- No new Python dependencies yet — that's feature 23

## Output contract

### `src/config.py` (modify)
Add three fields to `Settings`:

```python
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_host: str = "https://cloud.langfuse.com"
```

All three default to safe values so existing tests that construct `Settings(...)`
without Langfuse keys do not break. `langfuse_host` defaults to the Langfuse
Cloud URL — no change needed for cloud users.

### `.env.example` (modify)
Add a Langfuse section:

```
# Langfuse observability (https://cloud.langfuse.com)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### `.env` (user action)
User adds their real keys from the Langfuse Cloud dashboard. Not committed.

## Scope (in)
- `src/config.py` — add three Langfuse fields to `Settings`
- `.env.example` — document the new env vars

## Scope (out)
- No `langfuse` SDK dependency — added in feature 23
- No client initialisation — feature 23
- No tracing of any calls — features 24–26
- No docker-compose changes — not applicable to this machine
- No changes to any routes, tools, or agent code

## Dependencies
- New: none — credentials are just strings in Settings
- Existing: `pydantic-settings`

## Acceptance criteria
1. `uv run python -c "from src.config import Settings; s = Settings(); print(s.langfuse_host)"` prints `https://cloud.langfuse.com`.
2. `uv run python -c "from src.config import Settings; s = Settings(); print(s.langfuse_public_key)"` prints the key loaded from `.env` (non-empty after user adds it).
3. `uv run pytest -v` — all existing tests pass (no regressions from config changes).
4. `uv run ruff check src/config.py` exits 0.

## Setup steps (user action before implementing)

1. Go to `cloud.langfuse.com` and sign up (GitHub login works).
2. Create a new project — name it `stripe-support`.
3. Go to **Settings → API Keys** → click **Create new API key**.
4. Copy both keys:
   - `Public Key` → `LANGFUSE_PUBLIC_KEY=pk-lf-...`
   - `Secret Key` → `LANGFUSE_SECRET_KEY=sk-lf-...`
5. Add both to your `.env` file. `LANGFUSE_HOST` can be left out (defaults to
   `https://cloud.langfuse.com` in `Settings`).

## Failure modes to handle
- Missing keys at runtime: `langfuse_public_key = ""` default means the app
  starts without Langfuse. Feature 23 will check for empty keys before
  initialising the client and log a warning rather than crashing.
- Wrong host (e.g. self-hosted URL): `langfuse_host` is a plain string — any
  URL is accepted. Validation happens at connection time in feature 23.

## Notes
- Pydantic Settings reads `LANGFUSE_PUBLIC_KEY` from `.env` and maps it to
  `langfuse_public_key` automatically (underscore/uppercase conversion is
  built-in).
- The `langfuse_host` default points to Langfuse Cloud EU region
  (`cloud.langfuse.com`). US region is `us.cloud.langfuse.com` — user can
  override in `.env` if needed.
