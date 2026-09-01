"""Publication gates for corpus snapshots."""

from dataclasses import dataclass

from nice_mcp.corpus.models import DocChunk
from nice_mcp.corpus.snapshot import SnapshotManifest


class ValidationError(RuntimeError):
    """Raised when a staged corpus must not be published."""


@dataclass(frozen=True)
class ValidationReport:
    """Summary of corpus validation checks."""

    page_count: int
    chunk_count: int


def validate_chunks(chunks: list[DocChunk]) -> ValidationReport:
    """Validate structural invariants before index publication."""
    if not chunks:
        raise ValidationError("corpus contains no chunks")
    ids = [chunk.chunk_id for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValidationError("duplicate chunk identities detected")
    for chunk in chunks:
        if not chunk.canonical_url.startswith("https://nicegui.io/documentation"):
            raise ValidationError(f"invalid canonical URL for {chunk.chunk_id}")
    return ValidationReport(
        page_count=len({chunk.page_id for chunk in chunks}),
        chunk_count=len(chunks),
    )


def validate_regression(
    page_count: int,
    chunk_count: int,
    active: SnapshotManifest | None,
    *,
    override_reason: str | None = None,
) -> None:
    """Prevent publication of unexpectedly partial crawls."""
    if active is None or override_reason:
        return
    if page_count < active.page_count * 0.9:
        raise ValidationError("page count decreased by more than 10%")
    if chunk_count < active.chunk_count * 0.9:
        raise ValidationError("chunk count decreased by more than 10%")


def validate_source_sizes(
    current: dict[str, int], active: SnapshotManifest | None, *, override_reason: str | None = None
) -> None:
    """Reject widespread suddenly tiny source bodies relative to the active snapshot."""
    if active is None or override_reason or not active.source_sizes:
        return
    expected = set(active.source_sizes) & set(current)
    unusually_small = {
        page_id
        for page_id in expected
        if current[page_id] < 500 or current[page_id] < active.source_sizes[page_id] * 0.2
    }
    if expected and len(unusually_small) / len(expected) > 0.1:
        raise ValidationError("more than 10% of expected pages produced unusually small bodies")
