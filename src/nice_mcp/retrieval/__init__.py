"""Selectable documentation retrieval implementations."""

from pathlib import Path

from nice_mcp.config import RetrieverMode
from nice_mcp.corpus.snapshot import SnapshotManifest, verify_component
from nice_mcp.retrieval.base import RankedChunk, Retriever
from nice_mcp.retrieval.bm25 import BM25Retriever
from nice_mcp.retrieval.hybrid import HybridRetriever


def create_retriever(
    mode: RetrieverMode,
    snapshot: Path,
    manifest: SnapshotManifest,
    *,
    dense_device: str = "auto",
) -> Retriever:
    """Load the selected retriever or fail rather than silently falling back."""

    def component_path(name: str) -> Path:
        component = manifest.components.get(name)
        if component is None:
            raise RuntimeError(f"snapshot does not contain required {name!r} component")
        try:
            return verify_component(snapshot, name, component)
        except ValueError as error:
            raise RuntimeError(str(error)) from error

    if mode == RetrieverMode.BM25:
        return BM25Retriever.load(component_path("bm25"))
    if mode == RetrieverMode.DENSE:
        from nice_mcp.retrieval.dense import DenseRetriever

        return DenseRetriever.load(component_path("dense"), device=dense_device)
    if mode == RetrieverMode.HYBRID:
        from nice_mcp.retrieval.dense import DenseRetriever

        return HybridRetriever(
            BM25Retriever.load(component_path("bm25")),
            DenseRetriever.load(component_path("dense"), device=dense_device),
        )


__all__ = ["RankedChunk", "Retriever", "create_retriever"]
