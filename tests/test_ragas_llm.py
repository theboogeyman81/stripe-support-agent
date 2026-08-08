"""Tests for src/eval/ragas_llm.py — all external clients mocked."""

import asyncio
from unittest.mock import MagicMock

from langchain_core.outputs import Generation, LLMResult

from src.eval.ragas_llm import GeminiRagasLLM, VoyageRagasEmbeddings


def _mock_genai(text: str = "mocked response") -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value.text = text
    return client


def _mock_voyage(vectors: list | None = None) -> MagicMock:
    client = MagicMock()
    client.embed.return_value.embeddings = vectors or [[0.1, 0.2, 0.3]]
    return client


def _make_prompt(text: str = "What is a PaymentIntent?") -> MagicMock:
    prompt = MagicMock()
    prompt.to_string.return_value = text
    return prompt


# ── GeminiRagasLLM ──────────────────────────────────────────────────────────


def test_gemini_llm_generate_text_returns_llm_result() -> None:
    """generate_text() must return an LLMResult with one Generation."""
    llm = GeminiRagasLLM(api_key="test-key")
    llm._client = _mock_genai("Stripe processes payments.")
    result = llm.generate_text(_make_prompt())
    assert isinstance(result, LLMResult)
    assert len(result.generations) == 1
    assert isinstance(result.generations[0][0], Generation)
    assert result.generations[0][0].text == "Stripe processes payments."


def test_gemini_llm_generate_text_passes_prompt_to_client() -> None:
    """The prompt text must be forwarded verbatim to generate_content()."""
    llm = GeminiRagasLLM(api_key="test-key")
    mock_client = _mock_genai()
    llm._client = mock_client
    llm.generate_text(_make_prompt("Explain PaymentIntents"))
    mock_client.models.generate_content.assert_called_once()
    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs.get("contents") == "Explain PaymentIntents"


def test_gemini_llm_agenerate_text_returns_llm_result() -> None:
    """agenerate_text() must return the same shape as generate_text()."""
    llm = GeminiRagasLLM(api_key="test-key")
    llm._client = _mock_genai("async answer")
    result = asyncio.run(llm.agenerate_text(_make_prompt()))
    assert isinstance(result, LLMResult)
    assert result.generations[0][0].text == "async answer"


# ── VoyageRagasEmbeddings ───────────────────────────────────────────────────


def test_voyage_embeddings_embed_query_returns_list_of_float() -> None:
    """embed_query() must return a list of floats."""
    emb = VoyageRagasEmbeddings(api_key="test-key")
    emb._client = _mock_voyage([[0.1, 0.2, 0.3]])
    result = emb.embed_query("What is a PaymentIntent?")
    assert isinstance(result, list)
    assert all(isinstance(x, float) for x in result)


def test_voyage_embeddings_embed_documents_returns_list_of_lists() -> None:
    """embed_documents() must return a list of embeddings, one per text."""
    emb = VoyageRagasEmbeddings(api_key="test-key")
    emb._client = _mock_voyage([[0.1, 0.2], [0.3, 0.4]])
    result = emb.embed_documents(["text one", "text two"])
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(row, list) for row in result)


def test_voyage_embeddings_aembed_query_returns_list_of_float() -> None:
    """aembed_query() must return the same result as embed_query()."""
    emb = VoyageRagasEmbeddings(api_key="test-key")
    emb._client = _mock_voyage([[0.5, 0.6, 0.7]])
    result = asyncio.run(emb.aembed_query("test"))
    assert isinstance(result, list)
    assert result == [0.5, 0.6, 0.7]


def test_voyage_embeddings_aembed_documents_returns_list_of_lists() -> None:
    """aembed_documents() must return the same result as embed_documents()."""
    emb = VoyageRagasEmbeddings(api_key="test-key")
    emb._client = _mock_voyage([[0.1, 0.2], [0.3, 0.4]])
    result = asyncio.run(emb.aembed_documents(["a", "b"]))
    assert isinstance(result, list)
    assert len(result) == 2
