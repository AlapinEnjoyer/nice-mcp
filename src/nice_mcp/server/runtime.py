"""Stateless runtime corpus service."""

import re
from dataclasses import dataclass
from pathlib import Path

from nice_mcp.config import RetrieverMode
from nice_mcp.contracts import (
    DocChunkOutput,
    GetDocChunksOutput,
    SearchDocsOutput,
    SearchResult,
)
from nice_mcp.corpus.models import DocChunk
from nice_mcp.corpus.snapshot import SnapshotManifest, load_snapshot
from nice_mcp.retrieval import Retriever, create_retriever

TERM = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*|\d+")


@dataclass(frozen=True)
class CorpusService:
    """Request-independent service over one immutable snapshot revision."""

    manifest: SnapshotManifest
    chunks: dict[str, DocChunk]
    retriever: Retriever

    @classmethod
    def load(
        cls,
        snapshot: Path,
        mode: RetrieverMode = RetrieverMode.BM25,
        *,
        dense_device: str = "cpu",
    ) -> "CorpusService":
        """Load and validate all immutable process-level resources."""
        resolved = snapshot.resolve(strict=True)
        manifest, chunks = load_snapshot(resolved, verify_components=False)
        retriever = create_retriever(mode, resolved, manifest, dense_device=dense_device)
        return cls(manifest, {chunk.chunk_id: chunk for chunk in chunks}, retriever)

    def search(self, query: str, limit: int = 5) -> SearchDocsOutput:
        """Search without retaining any client or request state."""
        results = []
        for ranked in self.retriever.search(query, limit):
            chunk = self.chunks.get(ranked.chunk_id)
            if chunk is None:
                raise RuntimeError(f"retriever returned unknown chunk ID: {ranked.chunk_id}")
            results.append(
                SearchResult(
                    chunk_id=chunk.chunk_id,
                    page_id=chunk.page_id,
                    title=chunk.title,
                    heading_path=list(chunk.heading_path),
                    canonical_url=chunk.canonical_url,
                    excerpt=make_excerpt(chunk.content_markdown, query),
                    previous_chunk_id=chunk.previous_chunk_id,
                    next_chunk_id=chunk.next_chunk_id,
                )
            )
        return SearchDocsOutput(query=query, corpus_revision=self.manifest.corpus_revision, results=results)

    def get_chunks(self, chunk_ids: list[str]) -> GetDocChunksOutput:
        """Fetch valid IDs in request order and report stale IDs separately."""
        chunks: list[DocChunkOutput] = []
        missing: list[str] = []
        for chunk_id in chunk_ids:
            chunk = self.chunks.get(chunk_id)
            if chunk is None:
                missing.append(chunk_id)
                continue
            chunks.append(
                DocChunkOutput(
                    chunk_id=chunk.chunk_id,
                    page_id=chunk.page_id,
                    title=chunk.title,
                    heading_path=list(chunk.heading_path),
                    canonical_url=chunk.canonical_url,
                    content_markdown=chunk.content_markdown,
                )
            )
        return GetDocChunksOutput(
            corpus_revision=self.manifest.corpus_revision, chunks=chunks, missing_chunk_ids=missing
        )


def make_excerpt(text: str, query: str, maximum: int = 500) -> str:
    """Create a compact query-aware excerpt without truncating chunk Markdown."""
    compact = " ".join(text.split())
    if len(compact) <= maximum:
        return compact
    lowered = compact.casefold()
    positions = [lowered.find(term.casefold()) for term in TERM.findall(query)]
    match = min((position for position in positions if position >= 0), default=0)
    start = max(0, min(match - maximum // 3, len(compact) - maximum))
    end = start + maximum
    excerpt = compact[start:end].strip()
    return ("…" if start else "") + excerpt + ("…" if end < len(compact) else "")
