"""Minimal OpenAI embeddings adapter using the standard-library HTTP client."""
import json
import os
import urllib.error
import urllib.request
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """OpenAI embedding adapter; failures are surfaced without mock fallback."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name.strip()
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment")
        if not self.model_name:
            raise ValueError("Set EMBEDDING_MODEL, e.g. text-embedding-3-small")
        # OpenAI text-embedding-3-small defaults to 1536 dimensions.
        self.dimensions = int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        # Keep request sizes bounded; preserve response order using the index field.
        for offset in range(0, len(texts), 64):
            batch = texts[offset:offset + 64]
            payload = json.dumps({"model": self.model_name, "input": batch}).encode("utf-8")
            request = urllib.request.Request(
                "https://api.openai.com/v1/embeddings", data=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    result = json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError) as exc:
                raise RuntimeError(f"OpenAI embeddings request failed: {exc}") from exc
            data = sorted(result["data"], key=lambda row: row["index"])
            batch_vectors = [row["embedding"] for row in data]
            if any(len(vector) != self.dimensions for vector in batch_vectors):
                raise ValueError("Embedding dimension differs from EMBEDDING_DIMENSIONS")
            vectors.extend(batch_vectors)
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding provider returned an unexpected vector count")
        return vectors

    def embed_query(self, question: str) -> list[float]:
        vectors = self.embed_documents([question])
        return vectors[0]
