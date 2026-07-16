# Phase 6 — Semantic caching + cost tracking

> Draft.

## Goal
Cut cost and latency via caching. Track and expose every dollar spent.

## Features (planned)
36. `redis-setup` — add to docker-compose, health check
37. `exact-match-cache` — key = hash(model, prompt), value = response
38. `semantic-cache` — key = query embedding, similarity ≥ threshold hits
39. `cache-metrics` — hit/miss counters exposed on `/metrics`
40. `token-accounting` — middleware records tokens per request
41. `cost-logging` — Postgres table `request_costs`
42. `admin-cost-endpoint` — `GET /admin/costs?window=7d` returns aggregate

## What you'll learn
- Exact vs semantic caching, and their failure modes (stale, near-miss)
- Cache invalidation strategies for LLM responses
- Cost attribution (per user, per endpoint, per model)
- Similarity thresholds and how to tune them empirically

## Exit checklist
- [ ] Repeated identical query is served from cache with cost = $0
- [ ] Semantically similar query hits semantic cache, logged as such
- [ ] `/admin/costs` shows accurate 7-day spend
- [ ] Eval scores unchanged after caching enabled
- [ ] `LEARNINGS.md` updated with Phase 6 notes