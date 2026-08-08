"""Custom Ragas LLM and embeddings wrappers backed by google-genai and Voyage AI."""

import typing as t

import voyageai
from google import genai
from langchain_core.outputs import Generation, LLMResult
from ragas.embeddings.base import BaseRagasEmbeddings
from ragas.llms.base import BaseRagasLLM
from ragas.run_config import RunConfig

from src.config import Settings


class GeminiRagasLLM(BaseRagasLLM):
    """Ragas LLM wrapper backed by google-genai (no LangChain required)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
    ) -> None:
        super().__init__()
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def _call(self, text: str) -> str:
        """Call Gemini and return the response text."""
        response = self._client.models.generate_content(
            model=self._model, contents=text
        )
        return response.text.strip()

    def generate_text(
        self,
        prompt: t.Any,
        n: int = 1,
        temperature: float = 1e-8,
        stop: t.Optional[t.List[str]] = None,
        callbacks: t.Any = None,
    ) -> LLMResult:
        """Generate text synchronously from a Ragas PromptValue."""
        text = self._call(prompt.to_string())
        return LLMResult(generations=[[Generation(text=text)]])

    async def agenerate_text(
        self,
        prompt: t.Any,
        n: int = 1,
        temperature: t.Optional[float] = None,
        stop: t.Optional[t.List[str]] = None,
        callbacks: t.Any = None,
    ) -> LLMResult:
        """Generate text asynchronously (wraps synchronous Gemini call)."""
        return self.generate_text(prompt, n=n)


class VoyageRagasEmbeddings(BaseRagasEmbeddings):
    """Ragas embeddings wrapper backed by Voyage AI (no LangChain required)."""

    def __init__(self, api_key: str, model: str = "voyage-3-lite") -> None:
        super().__init__()
        self._client = voyageai.Client(api_key=api_key)
        self._model = model
        self.set_run_config(RunConfig())

    def embed_query(self, text: str) -> t.List[float]:
        """Embed a single query string."""
        return self._client.embed([text], model=self._model).embeddings[0]

    def embed_documents(self, texts: t.List[str]) -> t.List[t.List[float]]:
        """Embed a list of document strings."""
        return self._client.embed(texts, model=self._model).embeddings

    async def aembed_query(self, text: str) -> t.List[float]:
        """Async embed a single query string (wraps synchronous Voyage call)."""
        return self.embed_query(text)

    async def aembed_documents(self, texts: t.List[str]) -> t.List[t.List[float]]:
        """Async embed a list of document strings (wraps synchronous Voyage call)."""
        return self.embed_documents(texts)


def build_ragas_llm(settings: Settings) -> GeminiRagasLLM:
    """Return a GeminiRagasLLM configured from Settings."""
    return GeminiRagasLLM(api_key=settings.gemini_api_key)


def build_ragas_embeddings(settings: Settings) -> VoyageRagasEmbeddings:
    """Return a VoyageRagasEmbeddings configured from Settings."""
    return VoyageRagasEmbeddings(api_key=settings.voyage_api_key)
