"""Incremental reconstruction of immutable documentation corpora."""

from pydantic import BaseModel, ConfigDict

from nice_mcp.config import BuildConfig
from nice_mcp.corpus.chunking import TokenCounter, chunk_page
from nice_mcp.corpus.models import DocChunk, RawPage
from nice_mcp.corpus.snapshot import SnapshotManifest


class IncrementalBuildStats(BaseModel):
    """Non-canonical observability for one corpus reconstruction."""

    model_config = ConfigDict(frozen=True)

    added_pages: int
    changed_pages: int
    removed_pages: int
    reused_pages: int
    rebuilt_chunks: int
    reused_chunks: int


def chunk_incrementally(
    pages: list[RawPage],
    *,
    build_config: BuildConfig,
    previous_manifest: SnapshotManifest | None = None,
    previous_chunks: list[DocChunk] | None = None,
    force_full: bool = False,
    token_counter: TokenCounter,
) -> tuple[list[DocChunk], IncrementalBuildStats]:
    """Reuse unchanged page chunks when every chunk-producing input is compatible."""
    prior_chunks_by_page: dict[str, list[DocChunk]] = {}
    for chunk in previous_chunks or []:
        prior_chunks_by_page.setdefault(chunk.page_id, []).append(chunk)

    compatible = not force_full and previous_manifest is not None and previous_manifest.build_config == build_config
    prior_hashes = previous_manifest.source_hashes if compatible else {}
    current_ids = {page.page_id for page in pages}
    prior_ids = set(previous_manifest.source_hashes) if previous_manifest else set()

    chunks: list[DocChunk] = []
    added_pages = 0
    changed_pages = 0
    reused_pages = 0
    rebuilt_chunks = 0
    reused_chunks = 0
    for page in sorted(pages, key=lambda item: item.page_id):
        unchanged = prior_hashes.get(page.page_id) == page.source_hash
        has_prior_chunks = page.page_id in prior_chunks_by_page
        if unchanged and has_prior_chunks:
            reused = sorted(
                prior_chunks_by_page[page.page_id], key=lambda item: (item.heading_path, item.local_ordinal)
            )
            chunks.extend(reused)
            reused_pages += 1
            reused_chunks += len(reused)
            continue
        rebuilt = chunk_page(
            page,
            preferred_tokens=build_config.preferred_tokens,
            hard_tokens=build_config.hard_tokens,
            token_counter=token_counter,
        )
        chunks.extend(rebuilt)
        rebuilt_chunks += len(rebuilt)
        if page.page_id in prior_ids:
            changed_pages += 1
        else:
            added_pages += 1

    return chunks, IncrementalBuildStats(
        added_pages=added_pages,
        changed_pages=changed_pages,
        removed_pages=len(prior_ids - current_ids),
        reused_pages=reused_pages,
        rebuilt_chunks=rebuilt_chunks,
        reused_chunks=reused_chunks,
    )
