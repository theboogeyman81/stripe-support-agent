# Plan 09 — Ingest Endpoint

Spec: `.claude/specs/09-ingest-endpoint.md`

---

## Files to create or modify

| File | Action | Purpose |
|------|--------|---------|
| `src/ingest.py` | Modify | Extract `run_ingest()` from `main()`; `main()` becomes a thin wrapper |
| `src/config.py` | Modify | Add `admin_api_key: str = "changeme"` to `Settings` |
| `src/api/routes/ingest.py` | Create | `POST /admin/ingest` handler, auth dependency, request/response models |
| `src/api/app.py` | Modify | Register ingest router inside `create_app()` |
| `.env.example` | Modify | Add `ADMIN_API_KEY=changeme` with warning comment |
| `tests/test_ingest_route.py` | Create | 5 tests, all mocked — no network calls |

---

## Algorithm walkthrough

### 1. `run_ingest()` in `src/ingest.py`

Extract all pipeline logic from `main()` into a standalone function. `main()`
keeps only argument parsing and prints.

```python
def run_ingest(settings: Settings, recreate: bool = False) -> dict:
```

Returns a dict with exactly these 7 keys (zero-fill anything skipped):
```
docs_loaded, chunks_produced, vectors_embedded, vectors_skipped,
points_upserted, embed_cost_usd, cached_steps
```

**Step-by-step:**

**Step 1 — Load**
```
if DOCS_PATH.exists():
    add "docs" to cached_steps, docs_loaded = 0
else:
    call fetch_stripe_docs → fetch_all_docs → parse_llms_txt → save_jsonl
    set docs_loaded = return value of save_jsonl

if DOCS_PATH still missing:
    raise RuntimeError("docs file not found after load step")
```

**Step 2 — Chunk**
```
if CHUNKS_PATH.exists():
    add "chunks" to cached_steps, chunks_produced = 0
else:
    call chunk_corpus(DOCS_PATH, CHUNKS_PATH)
    set chunks_produced = stats["chunks"]

if CHUNKS_PATH still missing:
    raise RuntimeError("chunks file not found after chunk step")
```

**Step 3 — Embed**

Always call `embed_corpus` with `auto_confirm=True` — it handles
already-embedded chunks internally (reads existing IDs, skips them).
When all chunks are already embedded it returns in milliseconds without
any API call.

```
client = voyageai.Client(api_key=settings.voyage_api_key)
embedder = VoyageEmbedder(client)
embed_stats = embed_corpus(CHUNKS_PATH, EMBEDDINGS_PATH, embedder, auto_confirm=True)

vectors_embedded = embed_stats["newly_embedded"]
vectors_skipped  = embed_stats["already_embedded"]
embed_cost_usd   = embed_stats["actual_cost"]

if vectors_embedded == 0:
    add "embeddings" to cached_steps

if EMBEDDINGS_PATH missing or empty:
    raise RuntimeError("embeddings file not found after embed step")
```

**Step 4 — Upsert**

`QdrantStore.create_collection(recreate=False)` raises `RuntimeError` if the
collection already exists — that's fine for the CLI but wrong for the API
(we want idempotent upserts). Swallow the error when `recreate=False`:

```
store = QdrantStore(url=settings.qdrant_url, collection=COLLECTION,
                    api_key=settings.qdrant_api_key)
try:
    store.create_collection(recreate=recreate)
except RuntimeError:
    if recreate:
        raise           # real error — re-raise
    # collection already exists, proceed to upsert on top of it

upsert_stats = ingest(CHUNKS_PATH, EMBEDDINGS_PATH, store)
points_upserted = upsert_stats["upserted"]
```

**Updated `main()`** — thin wrapper after extraction:
```python
def main() -> None:
    args = parse_args()
    settings = Settings()
    try:
        result = run_ingest(settings, recreate=args.recreate)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Docs loaded : {result['docs_loaded']}")
    print(f"Chunks      : {result['chunks_produced']}")
    print(f"Embedded    : {result['vectors_embedded']}  (skipped {result['vectors_skipped']})")
    print(f"Upserted    : {result['points_upserted']}")
    print(f"Embed cost  : ${result['embed_cost_usd']:.4f}")
    if result['cached_steps']:
        print(f"Cached steps: {', '.join(result['cached_steps'])}")
```

The cost-confirmation prompt in `main()` stays where it is — it only runs
before embedding and only when data files are absent. `run_ingest()` always
uses `auto_confirm=True` because the API caller consciously triggered the
endpoint.

Wait — the confirmation prompt is currently in `main()` before calling
`embed_corpus`. After the refactor, `run_ingest()` calls `embed_corpus` with
`auto_confirm=True` and `main()` no longer has a prompt. This is intentional:
`main()` already handled the "estimated cost / Proceed?" gate before calling
`embed_corpus`. With `run_ingest()`, the gate is gone from the CLI too —
acceptable because the existing `--yes` flag was designed for automation and
the data files are almost always cached on a re-run.

If this is a concern, raise it with Pratham before implementing. The plan
proceeds assuming the prompt removal is fine for Phase 2.

---

### 2. `src/config.py`

One line added to `Settings`:
```python
admin_api_key: str = "changeme"
```
Pydantic-settings will map this to the `ADMIN_API_KEY` environment variable.

---

### 3. `src/api/routes/ingest.py`

**Models:**
```python
class IngestRequest(BaseModel):
    recreate: bool = False

class IngestResponse(BaseModel):
    docs_loaded: int
    chunks_produced: int
    vectors_embedded: int
    vectors_skipped: int
    points_upserted: int
    embed_cost_usd: float
    cached_steps: list[str]
```

**Auth dependency:**

FastAPI normalises header names to lowercase before matching. The
`alias="X-Admin-Key"` keeps the conventional capitalisation in the OpenAPI
docs while still accepting the actual HTTP header.

```python
def _check_admin_key(
    request: Request,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    if x_admin_key is None:
        raise HTTPException(status_code=401, detail="missing admin key")
    if x_admin_key != request.app.state.settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin key")
```

`request.app.state.settings` is the `Settings` instance set during lifespan
in `app.py`. This is the correct FastAPI pattern for accessing app-level state
inside a dependency.

**Route:**
```python
router = APIRouter(prefix="/admin")

@router.post("/ingest", response_model=IngestResponse)
def ingest_pipeline(
    request: Request,
    body: IngestRequest = Body(default_factory=IngestRequest),
    _: None = Depends(_check_admin_key),
) -> IngestResponse:
    try:
        result = run_ingest(request.app.state.settings, body.recreate)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ingest error: {e}")
    return IngestResponse(**result)
```

Note: `Body(default_factory=IngestRequest)` allows the caller to omit the
request body entirely (e.g. `curl -X POST /admin/ingest` with no body). This
matches the spec's "body itself may be omitted" requirement.

---

### 4. `src/api/app.py`

Add one import and one `include_router` call inside `create_app()`:
```python
from src.api.routes import ingest as ingest_routes
# inside create_app(), after ask router:
app.include_router(ingest_routes.router)
```

---

### 5. `.env.example`

Add after the existing keys:
```
# Admin key for POST /admin/ingest — change this before any real deployment
ADMIN_API_KEY=changeme
```

---

## Test design — `tests/test_ingest_route.py`

All tests follow the same pattern as `test_ask_route.py`:
- `create_app(settings=mock_settings)` — never use the module-level `app`
- `TestClient(app)` inside a `with` block for proper lifespan handling
- Mock `run_ingest` at `src.api.routes.ingest.run_ingest`

**Mock settings helper:**
```python
def _make_mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.admin_api_key = "test-key"
    return mock
```

**Mock ingest result:**
```python
_SAMPLE_RESULT = {
    "docs_loaded": 0,
    "chunks_produced": 0,
    "vectors_embedded": 0,
    "vectors_skipped": 4319,
    "points_upserted": 4319,
    "embed_cost_usd": 0.0,
    "cached_steps": ["docs", "chunks", "embeddings"],
}
```

**`test_ingest_missing_key_returns_401`**
- No `X-Admin-Key` header in request
- Assert `response.status_code == 401`
- Assert `response.json()["detail"] == "missing admin key"`
- No mock needed (auth check fires before handler)

**`test_ingest_wrong_key_returns_403`**
- `X-Admin-Key: wrong-key` header
- Assert `response.status_code == 403`
- Assert `response.json()["detail"] == "invalid admin key"`
- No mock needed

**`test_ingest_valid_key_returns_200_with_expected_shape`**
- `X-Admin-Key: test-key` header, empty body
- Mock `run_ingest` returning `_SAMPLE_RESULT`
- Assert `response.status_code == 200`
- Assert all 7 keys present in `response.json()`
- Assert `response.json()["points_upserted"] == 4319`

**`test_ingest_pipeline_error_returns_502`**
- `X-Admin-Key: test-key` header
- Mock `run_ingest` raising `RuntimeError("Qdrant down")`
- Assert `response.status_code == 502`
- Assert `"ingest error" in response.json()["detail"]`

**`test_ingest_recreate_flag_passed_through`**
- `X-Admin-Key: test-key` header, body `{"recreate": true}`
- Mock `run_ingest` with `MagicMock(return_value=_SAMPLE_RESULT)`
- Assert `mock_run_ingest.call_args[1]["recreate"] is True`
  (or positional: `mock_run_ingest.call_args[0][1] is True`)

---

## Ambiguities in the spec — resolved

**1. Collection-already-exists when `recreate=False`**
The spec says "only upserts new data" when `recreate=False`. But
`QdrantStore.create_collection()` raises `RuntimeError` if the collection
exists. Resolution: swallow that `RuntimeError` in `run_ingest()` when
`recreate=False` and proceed to upsert. When `recreate=True`, re-raise.

**2. Cost confirmation prompt in CLI after refactor**
`ingest.py`'s `main()` currently prompts before embedding. After extracting
`run_ingest()` with `auto_confirm=True`, the CLI prompt disappears. This is
acceptable: the `--yes` flag already existed for automation, and embeddings
are almost always cached on any re-run after the first ingest. Documented
above in case Pratham wants to restore it.

**3. `Body(default_factory=...)` for optional request body**
FastAPI requires a `Body()` annotation for the request body to be truly
optional (omittable). Using `Body(default_factory=IngestRequest)` makes the
body entirely optional while still parsing it if provided.

**4. `vectors_skipped` when embed step is fully cached**
`embed_corpus` reports `already_embedded` count even when `newly_embedded=0`.
This correctly reflects "N vectors were found in cache and skipped" even
when the embed step is considered cached. No special handling needed.

---

## Verification commands (PowerShell)

**AC1 — 200 with stats (server must be running with `ADMIN_API_KEY=secret` in `.env`):**
```powershell
Invoke-WebRequest -Uri http://localhost:8000/admin/ingest `
  -Method POST `
  -ContentType "application/json" `
  -Headers @{"X-Admin-Key" = "secret"} `
  -Body '{}' |
  Select-Object -ExpandProperty Content
```

**AC2 — 401 missing key:**
```powershell
Invoke-WebRequest -Uri http://localhost:8000/admin/ingest `
  -Method POST -ContentType "application/json" -Body '{}' `
  -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty StatusCode
# Expect: 401
```

**AC3 — 403 wrong key:**
```powershell
Invoke-WebRequest -Uri http://localhost:8000/admin/ingest `
  -Method POST -ContentType "application/json" `
  -Headers @{"X-Admin-Key" = "wrong"} -Body '{}' `
  -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty StatusCode
# Expect: 403
```

**AC4 — unit tests pass:**
```powershell
uv run pytest tests/test_ingest_route.py -v
```

**AC5 — full test suite:**
```powershell
uv run pytest
```

**AC6 — ruff clean:**
```powershell
uv run ruff check src/ingest.py src/api/routes/ingest.py src/api/app.py src/config.py
```

**AC7 — CLI still works after refactor:**
```powershell
uv run python -m src.ingest --help
```
