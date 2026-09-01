"""Reciprocal-rank fusion over lexical and dense candidates."""

from nice_mcp.retrieval.base import RankedChunk, Retriever

HYBRID_CANDIDATES = 40
HYBRID_RRF_K = 60
HYBRID_BM25_WEIGHT = 1.0
HYBRID_DENSE_WEIGHT = 7.0


class HybridRetriever:
    """Fuse BM25 and dense rankings WITHOUT mixing incomparable scores."""

    def __init__(
        self,
        bm25: Retriever,
        dense: Retriever,
        *,
        candidates: int = HYBRID_CANDIDATES,
        rrf_k: int = HYBRID_RRF_K,
        bm25_weight: float = HYBRID_BM25_WEIGHT,
        dense_weight: float = HYBRID_DENSE_WEIGHT,
    ) -> None:
        """Initialize the two first-stage retrievers and fusion defaults."""
        self._bm25 = bm25
        self._dense = dense
        self._candidates = candidates
        self._rrf_k = rrf_k
        self._bm25_weight = bm25_weight
        self._dense_weight = dense_weight

    def search(self, query: str, limit: int) -> list[RankedChunk]:
        """Fuse two independent rankings with RRF."""
        scores: dict[str, float] = {}
        for weight, ranking in (
            (self._bm25_weight, self._bm25.search(query, self._candidates)),
            (self._dense_weight, self._dense.search(query, self._candidates)),
        ):
            for rank, result in enumerate(ranking, start=1):
                scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + weight / (self._rrf_k + rank)
        return [
            RankedChunk(chunk_id, score)
            for chunk_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]
