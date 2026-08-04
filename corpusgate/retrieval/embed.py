"""Embeddings: always local, pinned in configs/models.yaml.

The real embedder wraps sentence-transformers with the pinned model
and never sends text anywhere; embedding is inside the self-hosting
boundary by rule 6. The fake embedder is deterministic and cheap so
the index and retrieval layers are testable in CI without torch, a
model download, or a network.
"""

import hashlib
import math
from pathlib import Path

import yaml

MODELS_CONFIG = "configs/models.yaml"


def pinned_embedding_model(config_path: str | Path = MODELS_CONFIG) -> str:
    return yaml.safe_load(Path(config_path).read_text())["models"]["embeddings"]


class SentenceTransformerEmbedder:
    """The pinned local embedder; loads lazily, runs on CPU."""

    def __init__(self, model_name: str | None = None):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or pinned_embedding_model()
        self._model = SentenceTransformer(self.model_name, device="cpu")
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.encode(texts, normalize_embeddings=True)]


class FakeEmbedder:
    """Deterministic hash-based unit vectors for tests; similar only to itself.

    Identical texts embed identically, different texts are nearly
    orthogonal, which is exactly enough to test index round trips and
    top-k plumbing without any model.
    """

    model_name = "fake"
    dim = 32

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            raw = [b - 127.5 for b in digest[: self.dim]]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            vectors.append([x / norm for x in raw])
        return vectors


def get_embedder(kind: str = "local"):
    if kind == "local":
        return SentenceTransformerEmbedder()
    if kind == "fake":
        return FakeEmbedder()
    raise ValueError(f"unknown embedder kind {kind!r}")
