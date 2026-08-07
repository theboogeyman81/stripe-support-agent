# Spec 16 — Tool: Calculator

## Feature
Add a `calculate` Pydantic AI tool to the agent that evaluates safe arithmetic
expressions and returns the numeric result as a string. When a user asks a
question involving numbers — e.g. "What is 3.5% of $12,000?" or "How much is
$500 after a 2.9% + $0.30 Stripe fee?" — the agent can call this tool instead
of doing mental arithmetic or hallucinating. No external APIs, no new
dependencies — just Python's `ast` module used as a safe evaluator.

## Why
LLMs are unreliable at multi-step arithmetic. A calculator tool gives the agent
a correct, deterministic answer for numeric sub-problems, which is especially
useful for Stripe fee calculations. It also exercises a second tool registration
so we can observe tool selection: the agent must choose between `search_docs`
and `calculate` based on the question.

## Input contract
- `src/agent/agent.py` — `create_agent()` from feature 15 (already has
  `tools=[search_docs]`, `deps_type=Settings`)
- No new environment variables or dependencies

## Output contract

### `src/agent/tools.py` (modify)
Add one new public function:

```python
def calculate(ctx: RunContext[Settings], expression: str) -> str:
    """Evaluate a safe arithmetic expression and return the result as a string."""
```

- Accepts a plain arithmetic expression string, e.g. `"12000 * 0.035"`.
- Evaluates using `ast.parse` + a whitelist-based node visitor — no `eval()`.
- Allowed nodes: numbers (`int`, `float`), unary `+`/`-`, binary `+`, `-`,
  `*`, `/`, `**`, and parentheses. No function calls, no names, no strings.
- Returns the result formatted as a plain string:
  - If the result is an integer value (e.g. `6.0`), return `"6"`.
  - Otherwise return Python's default `str()` of the float, e.g. `"420.0"`.
- Raises `ValueError` with a descriptive message for:
  - Empty or whitespace-only expression.
  - Any disallowed node type (names, calls, attributes, etc.).
  - Division by zero.
  - Expressions that do not parse as valid Python.

### Changes to `src/agent/agent.py`
- Add `calculate` to the `tools=[...]` list in `create_agent()`.
- No other changes.

## Scope (in)
- `src/agent/tools.py` — add `calculate` function and its AST visitor helper
- `src/agent/agent.py` — add `calculate` to `tools=[]`
- `tests/test_tools.py` — add tests for `calculate`

## Scope (out)
- No support for mathematical functions (`sqrt`, `log`, etc.) — plain operators only
- No unit conversion or currency formatting
- No changes to `search_docs`
- No new dependencies (`ast` is stdlib)
- No changes to any API routes

## Dependencies
- New: none (`ast` is stdlib)
- Existing: `pydantic_ai.RunContext`, `src/config.Settings`

## Acceptance criteria
1. `uv run python -c "from src.agent.tools import calculate; print('OK')"` exits 0.
2. `uv run pytest tests/test_tools.py -v` passes (all `calculate` tests plus
   existing `search_docs` tests).
3. `uv run ruff check src/agent/tools.py src/agent/agent.py` exits 0.
4. Manual check (no API cost):
   ```
   uv run python -c "
   from unittest.mock import MagicMock
   from pydantic_ai import RunContext
   from src.agent.tools import calculate
   ctx = MagicMock(spec=RunContext)
   print(calculate(ctx, '12000 * 0.035'))   # expect 420.0
   print(calculate(ctx, '(500 * 0.029) + 0.30'))  # expect 14.8
   "
   ```

## Failure modes to handle
- Empty expression: raise `ValueError("expression must not be empty")`.
- Disallowed node (e.g. `__import__('os')`): raise `ValueError("disallowed expression")`.
- Division by zero: raise `ValueError("division by zero")`.
- Unparseable expression (syntax error): raise `ValueError("invalid expression: <msg>")`.

## Notes
- `eval()` is forbidden — even with `globals={}` it is not safe enough for
  user-supplied input. The AST whitelist approach is the standard safe pattern.
- The AST visitor only needs to handle: `ast.Expression`, `ast.Constant`,
  `ast.UnaryOp`, `ast.BinOp`, and the operator node types for `+`, `-`, `*`,
  `/`, `**`. Any other node type raises `ValueError`.
- `ctx.deps` is not used in `calculate` (no Settings needed for pure math),
  but `RunContext[Settings]` is kept as the first parameter for consistency
  with `search_docs` and because `deps_type=Settings` is set on the agent.
