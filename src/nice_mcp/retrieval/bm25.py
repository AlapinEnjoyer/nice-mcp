"""BM25 lexical indexing and retrieval."""

import re
from pathlib import Path

import bm25s

from nice_mcp.corpus.models import DocChunk
from nice_mcp.retrieval.base import RankedChunk, searchable_text

TOKEN_PATTERN = r"(?u)\b[A-Za-z_][A-Za-z0-9_.]*\b|\b\d+\b"
QUERY_TERM = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*|\d+")


class BM25Retriever:
    """Deterministic lexical retriever backed by bm25s."""

    def __init__(self, index: bm25s.BM25, corpus: list[str]) -> None:
        """Initialize from a backend index and ordered chunk-ID corpus."""
        self._index = index
        self._corpus = corpus

    @classmethod
    def build(cls, chunks: list[DocChunk]) -> "BM25Retriever":
        """Build an in-memory lexical index."""
        ordered = sorted(chunks, key=lambda item: item.chunk_id)
        tokens = bm25s.tokenize(
            [_lexical_text(chunk) for chunk in ordered],
            lower=True,
            token_pattern=TOKEN_PATTERN,
            stopwords="english",
            show_progress=False,
        )
        index = bm25s.BM25(method="lucene")
        index.index(tokens, show_progress=False)
        return cls(index, [chunk.chunk_id for chunk in ordered])

    def save(self, directory: Path) -> None:
        """Persist the index and stable chunk-ID corpus."""
        directory.mkdir(parents=True, exist_ok=True)
        self._index.save(directory, corpus=self._corpus, show_progress=False)

    @classmethod
    def load(cls, directory: Path) -> "BM25Retriever":
        """Load a persisted lexical index."""
        index = bm25s.BM25.load(directory, load_corpus=True, show_progress=False)
        corpus = [item["text"] if isinstance(item, dict) else str(item) for item in index.corpus]
        return cls(index, corpus)

    def search(self, query: str, limit: int) -> list[RankedChunk]:
        """Retrieve lexical matches and hide backend-specific scores."""
        if not QUERY_TERM.findall(query):
            return []
        tokens = bm25s.tokenize(
            [query], lower=True, token_pattern=TOKEN_PATTERN, stopwords="english", show_progress=False, allow_empty=True
        )
        documents, scores = self._index.retrieve(
            tokens, corpus=self._corpus, k=min(limit, len(self._corpus)), show_progress=False
        )
        results = [
            RankedChunk(str(chunk_id), float(score))
            for chunk_id, score in zip(documents[0], scores[0], strict=True)
            if float(score) > 0
        ]
        return sorted(results, key=lambda item: (-item.score, item.chunk_id))[:limit]


def _lexical_text(chunk: DocChunk) -> str:
    """Boost structural and API fields through deterministic term repetition."""
    heading = f"{chunk.title} {' '.join(chunk.heading_path)}"
    return f"{heading}\n{heading}\n{heading}\n{searchable_text(chunk)}"
