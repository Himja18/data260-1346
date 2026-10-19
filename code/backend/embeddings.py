"""HW6 Part 2: text embeddings for episodic memory.

Backends (EMBED_BACKEND):
  st     - sentence-transformers BAAI/bge-small-en-v1.5 (default; same model as the HW4 RAG)
  ollama - an Ollama embedding model through src/model_client.py (e.g. nomic-embed-text)
  hash   - deterministic hashed bag-of-words, used only by the offline tests
All vectors are L2-normalised, so cosine similarity is a dot product.
"""
import hashlib
import re
import sys
from functools import lru_cache

import numpy as np

from hw06_config import EMBED_BACKEND, EMBED_MODEL_OLLAMA, EMBED_MODEL_ST, REPO_ROOT

HASH_DIM = 256


def _normalise(vectors: np.ndarray) -> np.ndarray:
    """L2-normalise each row (zero rows stay zero)."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class HashEmbedder:
    """Offline stand-in: words hashed into a fixed-size vector."""
    name = "hash-bow-256"

    def embed(self, texts: list) -> list:
        """Embed texts without any model download."""
        out = np.zeros((len(texts), HASH_DIM))
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9#]+", text.lower()):
                digest = hashlib.md5(word.encode()).digest()
                out[row, digest[0] % HASH_DIM] += 1.0 if digest[1] % 2 else -1.0
        return _normalise(out).tolist()


class SentenceTransformerEmbedder:
    """Local sentence-transformers model (loaded on first use)."""

    def __init__(self, model_name: str = EMBED_MODEL_ST) -> None:
        self.name = model_name
        self._model = None

    def embed(self, texts: list) -> list:
        """Embed texts with the local model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.name)
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=float).tolist()


class OllamaEmbedder:
    """Ollama embedding model, called through the HW1 model adapter."""

    def __init__(self, model_name: str = EMBED_MODEL_OLLAMA) -> None:
        self.name = f"ollama:{model_name}"
        self._model_name = model_name
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from model_client import ModelClient
        self._client = ModelClient()

    def embed(self, texts: list) -> list:
        """Embed texts through ModelClient.embed()."""
        vecs = np.asarray(self._client.embed(texts, model=self._model_name), dtype=float)
        return _normalise(vecs).tolist()


@lru_cache(maxsize=1)
def get_embedder():
    """The embedder selected by EMBED_BACKEND (one instance per process)."""
    if EMBED_BACKEND == "hash":
        return HashEmbedder()
    if EMBED_BACKEND == "ollama":
        return OllamaEmbedder()
    return SentenceTransformerEmbedder()


def cosine_scores(query: list, matrix: list) -> np.ndarray:
    """Cosine similarity of one normalised query vector against many normalised vectors."""
    if not matrix:
        return np.zeros(0)
    q = np.asarray(query, dtype=float)
    m = np.asarray(matrix, dtype=float)
    if m.shape[1] != q.shape[0]:               # stored with a different embedding model
        return np.full(len(matrix), -1.0)
    return m @ q
