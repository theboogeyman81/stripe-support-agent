"""Pydantic AI tools available to the Stripe support agent."""

import ast

from pydantic_ai import RunContext

from src.config import Settings
from src.db.tickets import insert_ticket
from src.rag.vectorstore import retrieve

_ALLOWED_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.UAdd, ast.USub)


def _eval_node(node: ast.expr) -> float:
    """Recursively evaluate a whitelisted AST node to a float."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("disallowed expression")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval_node(node.operand)
        return +operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_OPS):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ValueError("division by zero")
            return left / right
        if isinstance(node.op, ast.Pow):
            return left**right
    raise ValueError("disallowed expression")


def calculate(ctx: RunContext[Settings], expression: str) -> str:
    """Evaluate a safe arithmetic expression and return the result as a string."""
    if not expression.strip():
        raise ValueError("expression must not be empty")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid expression: {exc}") from exc
    result = round(_eval_node(tree.body), 10)
    if isinstance(result, float) and result.is_integer():
        return str(int(result))
    return str(result)


def create_ticket(ctx: RunContext[Settings], category: str, summary: str) -> str:
    """Create a support ticket in Postgres and return a confirmation string."""
    if not ctx.deps.postgres_url:
        raise ValueError("postgres_url is not configured")
    ticket_id = insert_ticket(ctx.deps.postgres_url, category, summary)
    return f"Ticket #{ticket_id} created (category: {category})."


def search_docs(ctx: RunContext[Settings], query: str) -> str:
    """Search Stripe docs for chunks relevant to query; return formatted text."""
    if not query.strip():
        raise ValueError("query must not be empty")
    chunks = retrieve(query, top_k=5)
    if not chunks:
        return "No relevant documentation found."
    sections = []
    for i, chunk in enumerate(chunks, 1):
        sections.append(
            f"[{i}] {chunk['doc_title']}\n"
            f"URL: {chunk['doc_url']}\n"
            f"{chunk['text']}"
        )
    return "\n\n".join(sections)
