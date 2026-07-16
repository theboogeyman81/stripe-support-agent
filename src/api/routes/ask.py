"""POST /ask route — retrieves chunks and generates a Gemini answer."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.rag.generator import generate
from src.rag.vectorstore import retrieve

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1)


class SourceItem(BaseModel):
    title: str
    url: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    input_tokens: int
    output_tokens: int
    cost_usd: float


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """Retrieve relevant chunks and generate a grounded answer."""
    try:
        chunks = retrieve(request.question, request.top_k)
        result = generate(request.question, chunks)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")

    seen_urls: set[str] = set()
    sources: list[SourceItem] = []
    for chunk in chunks:
        if chunk["doc_url"] not in seen_urls:
            seen_urls.add(chunk["doc_url"])
            sources.append(SourceItem(title=chunk["doc_title"], url=chunk["doc_url"]))

    return AskResponse(
        answer=result["answer"],
        sources=sources,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=result["cost_usd"],
    )
