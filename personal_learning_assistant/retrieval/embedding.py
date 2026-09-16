"""Embedding provider abstraction for rebuildable Phase 5.8 indexes."""

from __future__ import annotations

from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str

    def embed(self, texts: Sequence[str]):
        ...


class FastEmbedProvider:
    """Lazy FastEmbed adapter.

    Construction does not import/download the model. The first embed() call does.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        *,
        model_version: str = "fastembed-0.8.0",
    ):
        self.model_name = str(model_name)
        self.model_version = str(model_version)
        self._model = None

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except ImportError as error:
            raise RuntimeError(
                "Semantic retrieval requires fastembed. Install project requirements."
            ) from error
        self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed(self, texts):
        try:
            import numpy as np
        except ImportError as error:
            raise RuntimeError(
                "Semantic retrieval requires NumPy. Install project requirements."
            ) from error
        model = self._get_model()
        return [
            np.asarray(vector, dtype=np.float32)
            for vector in model.embed(list(texts))
        ]
