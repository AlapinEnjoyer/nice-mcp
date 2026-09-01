"""Offline corpus snapshot build orchestration."""

import asyncio
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from nice_mcp.config import BuildConfig
from nice_mcp.corpus.fetch import fetch_corpus
from nice_mcp.corpus.incremental import chunk_incrementally
from nice_mcp.corpus.models import DocChunk
from nice_mcp.corpus.snapshot import (
    ComponentManifest,
    SnapshotManifest,
    load_snapshot,
    set_distribution_permissions,
    tree_checksum,
    write_snapshot,
)
from nice_mcp.corpus.tokens import load_token_counter
from nice_mcp.corpus.validation import validate_chunks, validate_regression, validate_source_sizes
from nice_mcp.retrieval.bm25 import BM25Retriever

BUILD_COMPONENTS = {"bm25", "dense"}


@dataclass(frozen=True)
class BuiltSnapshot:
    """A completed immutable snapshot ready for activation or reporting."""

    manifest: SnapshotManifest
    path: Path


@dataclass
class SnapshotStage:
    """Temporary snapshot directory that can be promoted exactly once."""

    staging: Path
    snapshots: Path
    promoted: bool = False

    def promote(self, revision: str) -> Path:
        """Move the staged snapshot into its immutable revision directory."""
        if self.promoted:
            raise RuntimeError("snapshot stage already promoted")
        target = self.snapshots / revision.removeprefix("sha256:")
        if target.exists():
            shutil.rmtree(self.staging)
        else:
            self.staging.replace(target)
        self.promoted = True
        return target


def build_corpus_snapshot(
    output_root: Path,
    requested: set[str],
    *,
    regression_override: str | None = None,
    full_rebuild: bool = False,
    dense_device: str = "cpu",
) -> BuiltSnapshot:
    """Fetch, chunk, index, validate, and write an immutable corpus snapshot."""
    include_dense = validate_requested_components(requested)
    config = BuildConfig()
    current = output_root / "current"
    if current.exists():
        active_manifest, active_chunks = load_snapshot(current.resolve(strict=True), verify_components=False)
    else:
        active_manifest, active_chunks = None, []

    token_counter = load_token_counter(config.tokenizer)
    pages = asyncio.run(
        fetch_corpus(
            config.source_index_url,
        )
    )
    chunks, incremental_stats = chunk_incrementally(
        pages,
        build_config=config,
        previous_manifest=active_manifest,
        previous_chunks=active_chunks,
        force_full=full_rebuild,
        token_counter=token_counter,
    )
    report = validate_chunks(chunks)
    validate_regression(report.page_count, report.chunk_count, active_manifest, override_reason=regression_override)
    source_sizes = {page.page_id: len(page.content_markdown.strip()) for page in pages}
    validate_source_sizes(source_sizes, active_manifest, override_reason=regression_override)

    with staged_snapshot(output_root) as stage:
        build_stats = incremental_stats.model_dump()
        components = build_retrieval_components(
            chunks,
            stage.staging,
            include_dense=include_dense,
            dense_device=dense_device,
        )
        manifest = write_snapshot(
            stage.staging,
            chunks,
            source_hashes={page.page_id: page.source_hash for page in pages},
            source_sizes=source_sizes,
            build_config=config,
            components=components,
            regression_override_reason=regression_override,
            build_stats=build_stats,
        )
        load_snapshot(stage.staging)
        set_distribution_permissions(stage.staging)
        return BuiltSnapshot(manifest, stage.promote(manifest.corpus_revision))


def reindex_snapshot(
    snapshot: Path,
    output_root: Path,
    requested: set[str],
    *,
    dense_device: str = "cpu",
) -> BuiltSnapshot:
    """Create a new immutable revision with selected retrieval components."""
    include_dense = validate_requested_components(requested)
    source = snapshot.resolve(strict=True)
    prior, chunks = load_snapshot(source, verify_components=False)
    with staged_snapshot(output_root) as stage:
        components = build_retrieval_components(
            chunks,
            stage.staging,
            include_dense=include_dense,
            dense_device=dense_device,
        )
        manifest = write_snapshot(
            stage.staging,
            chunks,
            source_hashes=prior.source_hashes,
            source_sizes=prior.source_sizes,
            build_config=prior.build_config,
            components=components,
        )
        load_snapshot(stage.staging)
        set_distribution_permissions(stage.staging)
        return BuiltSnapshot(manifest, stage.promote(manifest.corpus_revision))


def build_retrieval_components(
    chunks: list[DocChunk],
    staging: Path,
    *,
    include_dense: bool,
    dense_device: str = "cpu",
) -> dict[str, ComponentManifest]:
    """Build mandatory BM25 and, optionally, a dense index in a staged snapshot."""
    components: dict[str, ComponentManifest] = {}
    bm25_path = Path("indexes/bm25")
    BM25Retriever.build(chunks).save(staging / bm25_path)
    components["bm25"] = component_manifest(bm25_path, staging, {"backend": "bm25s", "method": "lucene"})
    if include_dense:
        from nice_mcp.retrieval.dense import DENSE_MODEL_ID, DenseRetriever

        dense_path = Path("indexes/dense")
        DenseRetriever.build(
            chunks,
            staging / dense_path,
            device=dense_device,
        )
        components["dense"] = component_manifest(
            dense_path, staging, {"model_id": DENSE_MODEL_ID}
        )
    return components


def component_manifest(path: Path, root: Path, logical_config: dict[str, str]) -> ComponentManifest:
    """Create component metadata with separated logical config and physical checksum."""
    return ComponentManifest(
        relative_path=path.as_posix(),
        logical_config=logical_config,
        sha256=tree_checksum(root / path),
    )


def validate_requested_components(requested: set[str]) -> bool:
    """Validate requested indexes and return whether the optional dense index is wanted."""
    unknown = requested - BUILD_COMPONENTS
    if unknown:
        raise ValueError(f"unsupported retrieval components: {sorted(unknown)}")
    if "bm25" not in requested:
        raise ValueError("bm25 is required")
    return "dense" in requested


@contextmanager
def staged_snapshot(output_root: Path) -> Iterator[SnapshotStage]:
    """Yield a temporary snapshot stage and remove it unless it is promoted."""
    snapshots = output_root / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    stage = SnapshotStage(Path(tempfile.mkdtemp(prefix=".build-", dir=snapshots)), snapshots)
    try:
        yield stage
    finally:
        if not stage.promoted:
            shutil.rmtree(stage.staging, ignore_errors=True)
