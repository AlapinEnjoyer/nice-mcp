"""Exact dense-vector retrieval."""

import json
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer

from nice_mcp.corpus.models import DocChunk
from nice_mcp.retrieval.base import RankedChunk, searchable_text

DENSE_MODEL_ID = "BAAI/bge-small-en-v1.5"
DENSE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
SUPPORTED_DEVICES = {"auto", "cpu", "mps"}

type Embeddings = NDArray[np.float32]


def resolve_device(device: str) -> str:
    """Resolve ``auto`` to the best available PyTorch device."""
    if device not in SUPPORTED_DEVICES:
        raise ValueError(f"unsupported dense device: {device}")
    if device != "auto":
        return device
    import torch

    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


class DenseRetriever:
    """Cosine retrieval over normalized single-vector embeddings."""

    def __init__(self, model: SentenceTransformer, ids: list[str], embeddings: Embeddings) -> None:
        """Initialize from a local encoder and aligned normalized vectors."""
        self._model = model
        self._ids = ids
        self._embeddings = embeddings

    @classmethod
    def build(
        cls,
        chunks: list[DocChunk],
        directory: Path,
        *,
        batch_size: int = 32,
        device: str = "auto",
    ) -> "DenseRetriever":
        """Build and persist an exact dense index and its query encoder."""
        model = SentenceTransformer(DENSE_MODEL_ID, device=resolve_device(device))
        ordered_chunks = sorted(chunks, key=lambda chunk: chunk.chunk_id)
        embeddings: Embeddings = model.encode(
            [searchable_text(chunk) for chunk in ordered_chunks],
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "embeddings.npy", embeddings, allow_pickle=False)
        (directory / "ids.json").write_text(
            json.dumps([chunk.chunk_id for chunk in ordered_chunks]) + "\n", encoding="utf-8"
        )
        model.save_pretrained(str(directory / "model"))
        return cls(model, [chunk.chunk_id for chunk in ordered_chunks], embeddings)

    @classmethod
    def load(cls, directory: Path, *, device: str = "auto") -> "DenseRetriever":
        """Load local model assets and vectors without network access."""
        ids = json.loads((directory / "ids.json").read_text(encoding="utf-8"))
        embeddings = np.load(directory / "embeddings.npy", allow_pickle=False)
        if len(ids) != len(embeddings):
            raise ValueError("dense index IDs and embeddings differ in length")
        model = SentenceTransformer(str(directory / "model"), device=resolve_device(device), local_files_only=True)
        return cls(model, ids, embeddings)

    def search(self, query: str, limit: int) -> list[RankedChunk]:
        """Return exact cosine nearest neighbors."""
        vector = self._model.encode(
            [DENSE_QUERY_PREFIX + query], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )[0]
        scores = self._embeddings @ vector
        indices = np.argsort(-scores, kind="stable")[:limit]
        return [RankedChunk(self._ids[int(index)], float(scores[int(index)])) for index in indices]
