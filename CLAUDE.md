# CLAUDE.md — Stripe Support Agent

This file is auto-loaded into every Claude Code session in this repo. It defines
how we work here. Read it fully at the start of every session.

---

## Project

An LLM-powered customer support agent answering questions from Stripe's public
documentation, built as an end-to-end learning project covering the full LLMOps
stack: RAG, agents with tool use, observability, evaluation, semantic caching,
cost tracking, guardrails, and deployment.

**Owner:** Pratham (solo). Final-year AI/ML undergrad. Learning by shipping.

**Corpus:** Stripe docs via `https://docs.stripe.com/llms-full.txt`.

**Interface:** CLI in Phase 1, FastAPI from Phase 2 onward.

---

## Tech stack

| Layer            | Choice                             |
|------------------|------------------------------------|
| Language         | Python 3.11+                       |
| Package manager  | uv                                 |
| Lint/format      | ruff                               |
| Tests            | pytest                             |
| LLM              | Gemini 2.5 Flash (google-genai)    |
| Embeddings       | Voyage AI, `voyage-3-lite`, 512-d  |
| Vector DB        | Qdrant (Docker, self-hosted)       |
| Agent framework  | Pydantic AI                        |
| API              | FastAPI (Phase 2+)                 |
| Observability    | Langfuse self-hosted (Phase 4+)    |
| Eval             | Ragas + custom LLM-as-judge        |
| Cache            | Redis (Phase 6+)                   |
| Relational store | Postgres (Phase 3+ for tickets)    |
| Deployment       | Docker Compose, Fly.io, GitHub Actions |

**Do not add dependencies not on this list without asking. No LangChain,
LlamaIndex, or OpenAI SDK. No Pinecone or Weaviate.**

---

## Repo layout (target)
src/
config.py               # pydantic-settings
ingest.py               # Phase 1 CLI: load → chunk → embed → upsert
ask.py                  # Phase 1 CLI: question → retrieve → generate
rag/
loader.py             # fetch + parse llms-full.txt
chunker.py            # recursive char split, token-aware
embedder.py           # Voyage client
vectorstore.py        # Qdrant wrapper + retrieve()
generator.py          # Gemini prompt + generation
Later phases add: api/, agent/, tools/, eval/, cache/, guardrails/
tests/
data/                     # gitignored: JSONL corpora
.claude/
specs/                  # feature specs (author: human)
plans/                  # feature plans (author: Claude Code)
phases/                 # phase-level docs
current.md            # pointer to active phase
phase-1.md ... phase-8.md
docker-compose.yml
pyproject.toml
.env.example
LEARNINGS.md

---

## The workflow: spec → plan → implement → verify → PR

**One feature = one branch = one session = one PR.** No exceptions.

### Roles (do not blur them)

1. **Human (Pratham)** — writes specs, reviews plans, reviews diffs, decides
   architecture, runs commands, opens/merges PRs, updates `LEARNINGS.md`.
2. **Claude Code (you)** — reads specs, produces plans, implements, writes tests,
   explains concepts on request. Never merges PRs. Never edits `LEARNINGS.md`.
3. **Chat (Claude on claude.ai)** — used sparingly, only for concept explanations
   the human requests directly and for phase-transition gates.

### Per-feature loop

git checkout main && git pull
git checkout -b feature/<slug>
Human writes .claude/specs/NN-<slug>.md
Human commits the spec on the feature branch
Claude Code reads the spec + current code, writes .claude/plans/NN-<slug>.md.
Do not implement yet.
Human reviews plan. Iterates until sound.
Claude Code implements per the plan. Shows full diff. Does not commit.
Human reviews diff. Runs acceptance criteria.
Iterate if needed.
Human commits with the message template below and pushes.
Human opens PR on GitHub, reviews diff again in the PR UI, squash-merges.
Human deletes local + remote branch, updates LEARNINGS.md on main.


### Commit message template
feat: <feature name> (Phase <N>, feature <NN>)

<bullet 1>
<bullet 2>
<bullet 3>

Spec: .claude/specs/NN-<slug>.md
Plan: .claude/plans/NN-<slug>.md
<Any relevant metric, e.g. "Chunks produced: 4319">

---

## Spec template (human writes this)

Every spec follows this shape. Copy and fill.

```markdown
# Spec NN — <Feature Name>

## Feature
<One paragraph: what this builds.>

## Why
<One paragraph: why it exists, what unblocks after it.>

## Input contract
<Files consumed, their JSON shape if applicable.>

## Output contract
<Files produced, their JSON shape if applicable. Include field-by-field rules.>

## Scope (in)
- <Bullet: specific files, functions, CLI entries, tests.>

## Scope (out)
- <Bullet: what will NOT be built here. Reserve for later features.>

## Dependencies
- New: <list, or "none">
- Existing: <list>

## Acceptance criteria
1. <Runnable command + expected outcome.>
2. <Runnable command + expected outcome.>
...

## Failure modes to handle
- <Case>: <behavior>
- <Case>: <behavior>

## Notes
- <Anything non-obvious about the design or trade-offs.>
```

Specs must be **runnable** in the acceptance criteria — every criterion is a
command you can execute and eyeball. "Works well" is not a criterion.

---

## Plan requirements (Claude Code writes this)

When asked to plan a feature, produce `.claude/plans/NN-<slug>.md` with:

1. **Files to create or modify** — every one, with purpose.
2. **Algorithm walkthrough** for any non-trivial logic. Not just naming an
   approach — the actual steps.
3. **Test design** — every test, with the mock setup for external clients.
4. **Ambiguities in the spec** — call them out with your proposed resolution.
5. **Verification commands** (PowerShell) — one per acceptance criterion.

**Do not implement while producing the plan. Show the plan and stop.**

---

## Implementation constraints (apply always)

- Type hints on all function signatures.
- One-line docstrings on every public function.
- No side effects at import time (no auto-connecting clients, no file I/O).
- All external clients (Voyage, Gemini, Qdrant) are initialised inside functions
  or classes, not at module top-level.
- Configuration is read from `src/config.py`'s `Settings` class. Never
  `os.environ` directly.
- All I/O paths accept `pathlib.Path`, not `str`.
- Prefer generators over lists for anything that streams from disk.
- No new dependencies without human approval. If you feel one is essential,
  stop and ask.
- No async unless the spec explicitly requires it.
- No progress-bar or CLI-styling libraries (tqdm, rich, click). Use argparse
  and `print`.

---

## Test rules

- **Every feature ships tests.** No "we'll add tests later."
- Tests never make network calls. All external clients are mocked.
- Tests use inline fixtures (sample strings/dicts in the test file) not files
  in `tests/fixtures/` unless the fixture is >20 lines.
- Test names describe behaviour: `test_chunker_respects_code_block_boundaries`,
  not `test_chunker_1`.
- One assertion per concept. Multiple asserts in one test is fine if they
  verify the same behaviour.
- Do not test third-party libraries. Test our logic.

---

## Diff review checklist (human uses this before committing)

Every diff must pass these before commit. Claude Code, remind the human of this
checklist after presenting a diff.

- [ ] Only files in scope of the spec are modified.
- [ ] No unexpected dependencies added to `pyproject.toml`.
- [ ] No hardcoded secrets or paths.
- [ ] No `print` statements left from debugging (except deliberate CLI output).
- [ ] Type hints present on new functions.
- [ ] Tests exist and mock external services.
- [ ] `uv run ruff check <changed files>` passes.
- [ ] `uv run pytest <new test file>` passes.
- [ ] Acceptance criteria from spec all pass when run manually.

---

## Cost discipline

Any feature that calls a paid API must:

1. Print an estimated cost before spending anything.
2. Prompt for confirmation (`Proceed? [y/N]`, default No).
3. Accept a `--yes` flag to bypass the prompt for automation.
4. Print actual cost at the end.

**Target: total project spend under $5/month.** Voyage free tier covers
embeddings. Gemini free tier covers most generation. Real spend should be near
zero for Phases 1–5.

---

## Pushback duty

Push back on the human if they:

- Try to skip writing a spec.
- Skip diff review before commit.
- Try to merge without acceptance criteria passing.
- Ask for a feature outside the current phase.
- Ask for a dependency not on the approved list.
- Ask to "just make it work" without understanding what changed.

Push back is not obstruction. State the concern briefly and ask them to confirm.
If they confirm after hearing the concern, proceed.

---

## Learning mode

The human is learning this stack. When implementing, err toward the
straightforward approach even if slightly less "clever." When a design choice
has trade-offs, put a one-line comment in the code explaining why we chose one
side. When a concept is new (first appearance of RAG, embeddings, agents,
tracing, evals, etc.), offer to explain it in ≤5 lines before implementing.
Never lecture unprompted. Never explain more than one concept per exchange.

---

## Where to find things

- **Current phase:** `.claude/phases/current.md`
- **All phase plans:** `.claude/phases/phase-1.md` through `phase-8.md`
- **Feature specs (human-authored):** `.claude/specs/`
- **Feature plans (you author):** `.claude/plans/`
- **Running notes:** `LEARNINGS.md` (human-owned)
- **Project README:** `README.md`

---

## Do not

- Do not create `main`-branch commits directly outside `LEARNINGS.md` updates.
- Do not modify `.claude/phases/*.md` unless explicitly asked. These are the
  human's planning artifacts.
- Do not modify `README.md` unless explicitly asked.
- Do not modify `LEARNINGS.md` — that's the human's log.
- Do not preemptively build ahead. If the phase file lists 6 features, build
  feature N and stop. N+1 comes in the next session.