Phase 1 — CLI RAG (in progress)

Feature 6: generator + ask.py CLI

Phase 2 — FastAPI wrapper + structured logging

Feature 7: FastAPI app skeleton
Feature 8: POST /ask endpoint
Feature 9: POST /ingest admin endpoint
Feature 10: GET /health + GET /ready
Feature 11: Structured JSON logging with request IDs
Feature 12: Request/response Pydantic schemas
Feature 13: Error handling middleware

Phase 3 — Agent with tool use

Feature 14: Pydantic AI agent scaffold
Feature 15: Tool — search_docs (wrap retrieve)
Feature 16: Tool — calculator
Feature 17: Tool — create_ticket (Postgres-backed)
Feature 18: Tool — lookup_user (mock user DB)
Feature 19: Agent system prompt + tool selection logic
Feature 20: Multi-turn conversation state
Feature 21: Agent endpoint POST /chat

Phase 4 — Observability with Langfuse

Feature 22: Langfuse self-hosted via docker-compose
Feature 23: Langfuse SDK integration + tracing decorators
Feature 24: Trace every LLM call
Feature 25: Trace every tool call
Feature 26: Trace retrieval (query, top-k, scores)
Feature 27: Session grouping (multi-turn conversations)
Feature 28: User feedback capture (thumbs up/down)

Phase 5 — Evaluation pipeline

Feature 29: Golden dataset (30–50 curated Q&A pairs)
Feature 30: Ragas integration (faithfulness, context precision, answer relevancy)
Feature 31: Custom LLM-as-judge for agent behavior
Feature 32: Retrieval eval script (recall@k, MRR)
Feature 33: pytest integration for evals
Feature 34: Nightly eval job (GitHub Actions cron)
Feature 35: Regression detection + reporting

Phase 6 — Semantic caching + cost tracking

Feature 36: Redis setup via docker-compose
Feature 37: Exact-match response cache
Feature 38: Semantic cache (query embedding similarity threshold)
Feature 39: Cache hit/miss metrics
Feature 40: Per-request token accounting
Feature 41: Per-request dollar cost logging (Postgres)
Feature 42: Cost dashboard endpoint GET /admin/costs

Phase 7 — Guardrails + fallback chains


Feature 43: Input guardrail — PII redaction (email, card, phone)
Feature 44: Input guardrail — prompt injection detection
Feature 45: Input guardrail — off-topic rejection
Feature 46: Output guardrail — hallucination check against retrieved context
Feature 47: Output guardrail — safety/toxicity filter
Feature 48: Output guardrail — citation enforcement
Feature 49: Model fallback chain (Gemini 2.5 Flash → Gemini 2.5 Flash-Lite → cached response)
Feature 50: Circuit breaker on repeated failures
Feature 51: Graceful degradation UX

Phase 8 — Deployment + CI/CD

Feature 52: Production Dockerfile (multi-stage)
Feature 53: Production docker-compose (app + Qdrant + Postgres + Redis + Langfuse)
Feature 54: .env management + secrets strategy
Feature 55: GitHub Actions — lint + test on PR
Feature 56: GitHub Actions — eval on PR (block merge on regression)
Feature 57: GitHub Actions — deploy on merge to main
Feature 58: Fly.io deployment config
Feature 59: HTTPS + custom domain (optional)
Feature 60: Public README with live demo URL + architecture diagram