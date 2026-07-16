# Phase 4 — Observability with Langfuse

> Draft.

## Goal
Every LLM call, tool call, and retrieval is traced end-to-end in Langfuse,
grouped by session, with cost attached.

## Features (planned)
22. `langfuse-selfhost` — add to docker-compose, initialise Postgres schema
23. `langfuse-sdk-integration` — client init from settings
24. `trace-llm-calls` — decorate every Gemini call
25. `trace-tool-calls` — decorate every tool
26. `trace-retrieval` — log query, top-k results, scores
27. `session-grouping` — link multi-turn traces by session id
28. `user-feedback` — thumbs up/down endpoint writes to trace

## What you'll learn
- LLM tracing vs classical APM (spans, generations, sessions)
- Sampling strategies (100% now, less at scale)
- Prompt/response inspection for debugging
- Cost aggregation per user, per endpoint, per model

## Exit checklist
- [ ] Open a random production trace, replay the full agent turn
- [ ] Filter by session id — see all turns in one place
- [ ] Cost per trace shown, aggregates in Langfuse UI
- [ ] Thumbs-down surfaces the trace for review
- [ ] `LEARNINGS.md` updated with Phase 4 notes