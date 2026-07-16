# Phase 2 — FastAPI wrapper + structured logging

> Draft. Feature list is a target, not a contract. Revise at phase entry
> based on Phase 1 learnings.

## Goal
Expose the RAG pipeline as an HTTP API with typed schemas, structured JSON
logs, and request tracing IDs. No new AI logic.

## Features (planned)
7.  `fastapi-skeleton` — app factory, settings wiring, uvicorn entry
8.  `ask-endpoint` — `POST /ask` calling the Phase 1 generator
9.  `ingest-endpoint` — `POST /admin/ingest` (auth-gated) triggering pipeline
10. `health-endpoints` — `GET /health` (liveness), `GET /ready` (deps up)
11. `structured-logging` — JSON logs, request IDs, timing
12. `request-response-schemas` — Pydantic models per endpoint
13. `error-middleware` — uniform error shape, no leaked tracebacks

## What you'll learn
- FastAPI app factory pattern and dependency injection
- Pydantic response models vs domain models
- Structured logging patterns for LLM services
- Correlation IDs and how they enable later observability

## Exit checklist
- [ ] `uvicorn src.api.app:app` serves and responds
- [ ] `POST /ask` returns typed JSON with answer + citations + cost
- [ ] Every request logs a JSON line with `request_id`, `latency_ms`, `cost_usd`
- [ ] Invalid input returns 4xx with a schema error, not 500
- [ ] Health endpoints reflect Qdrant reachability
- [ ] `LEARNINGS.md` updated with Phase 2 notes