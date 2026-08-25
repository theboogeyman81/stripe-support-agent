# Spec 38 — semantic-cache

## Feature
Add a semantic cache layer in front of the full `/ask` pipeline (retrieval +
generation). Before calling `retrieve()`, embed the incoming question with
Voyage AI and scan Redis for a stored entry whose embedding has cosine
similarity ≥ a configurable threshold. On a hit, return the cached
`AskResponse` fields immediately — zero retrieval, zero LLM spend. On a miss,
run the normal pipeline and store the result for future similar questions.

## Why
The exact-match cache (feature 37) only helps when questions are byte-for-byte
identical. Semantically equivalent phrasings ("how do I refund?" vs "what's
the process for issuing a refund?") always miss. The semantic cache broadens
coverage to near-duplicate questions, which dominate real support traffic.

## Input contract
- `src/cache/exact_match.py` — pattern to follow for error-swallowing helpers.
- `src/rag/embedder.py` — `VoyageEmbedder.embed_query(text) -> list[float]`.
- `src/api/app.py` — lifespan already stores `redis_client` on `app.state`.
- `src/config.py` — `Settings` extended with new `semantic_similarity_threshold`.

## Output contract
- `src/cache/semantic.py` — exports:
  - `cosine_similarity(a: list[float], b: list[float]) -> float`
  - `semantic_search(redis_client, embedder, question, threshold) -> dict | None`
    Embeds `question`, scans all `semantic:*` keys, returns best-matching
    entry (without the `embedding` field) if similarity ≥ threshold, else None.
    Silently returns None on any error.
  - `semantic_store(redis_client, embedder, question, value, ttl) -> None`
    Embeds `question`, writes `{**value, "embedding": [...]}` as JSON under
    a new `semantic:<uuid>` key with TTL. Silently swallows errors.
- `src/config.py` — new `semantic_similarity_threshold: float = 0.95` field.
- `.env.example` — new `SEMANTIC_SIMILARITY_THRESHOLD=0.95` line.
- `src/api/app.py` — lifespan initialises a `VoyageEmbedder` and stores it
  on `app.state.embedder`; on error stores `None`.
- `src/api/routes/ask.py` — semantic cache checked before `retrieve()`;
  result stored after the full pipeline completes.
- `tests/test_semantic_cache.py` — unit tests, all mocked.

## Scope (in)
- `src/cache/semantic.py` (new)
- `src/config.py` — add `semantic_similarity_threshold`
- `.env.example` — add `SEMANTIC_SIMILARITY_THRESHOLD`
- `src/api/app.py` — add `VoyageEmbedder` init in lifespan
- `src/api/routes/ask.py` — semantic cache lookup + store
- `tests/test_semantic_cache.py` (new)

## Scope (out)
- No Redis Stack / vector search commands — plain Redis SCAN + GET only
- No semantic cache for `/chat` (agent) endpoint
- No cache eviction beyond TTL expiry
- No cache metrics or hit-rate counters (feature 39)
- No per-key similarity logging

## Dependencies
- New: none — `voyageai` and `redis` already installed; `math`, `uuid`, `json` are stdlib
- Existing: `src/rag/embedder.py`, `src/cache/exact_match.py`, `src/config.py`

## Acceptance criteria
1. `uv run ruff check src/cache/semantic.py src/api/app.py src/api/routes/ask.py tests/test_semantic_cache.py` — no errors.
2. `uv run pytest tests/test_semantic_cache.py -v` — all tests pass.
3. `uv run pytest -q` — full suite still passes.
4. With a real `REDIS_URL` in `.env`, POST the same question twice:
   - First response: `"cache_hit": false`
   - Second response: `"cache_hit": true` (served from semantic cache before retrieval)
5. POST a paraphrase of the first question; response returns `"cache_hit": true`.
6. With `REDIS_URL=""`, endpoint still answers correctly (`cache_hit: false`).

## Failure modes to handle
- Voyage API error during embed: `semantic_search` and `semantic_store` catch
  all exceptions and return None / no-op — pipeline continues normally.
- Redis SCAN or GET error: same catch-all, treated as miss.
- Corrupt JSON in a stored entry: skip that entry, continue scanning.
- `embedder` is None (Voyage key missing at startup): skip cache entirely.
- `redis_client` is None: skip cache entirely.

## Notes
- Redis Cloud free tier (standard Redis) has no vector search. We scan all
  `semantic:*` keys in Python and compute cosine similarity locally. This is
  O(n) but acceptable for a dev/demo project where n < a few thousand.
- Voyage embeddings are L2-normalised, so cosine similarity equals dot product.
  We still compute cosine explicitly so the function is correct for any input.
- Threshold default 0.95 is intentionally conservative — better to miss and
  call Gemini than to return a subtly wrong cached answer.
- The `embedding` field is stored inside the Redis value (alongside answer,
  sources, tokens) so a single GET retrieves everything needed for both
  similarity comparison and response construction.
- `semantic_store` is called after `generate()`, so the stored result already
  reflects the exact-match cache hit status (`cache_hit: False` stripped before
  writing, same pattern as `set_cached` in feature 37).
