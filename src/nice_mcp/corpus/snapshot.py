"""Immutable corpus snapshot persistence and activation."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from nice_mcp.config import BuildConfig
from nice_mcp.corpus.models import DocChunk


class Digest(Protocol):
    """Minimal hashing interface needed by the file checksum helpers."""

    def update(self, data: bytes, /) -> None:
        """Add bytes to the digest."""


class ComponentManifest(BaseModel):
    """Metadata for one retrieval component."""

    model_config = ConfigDict(extra="forbid")
    kind: str
    relative_path: str
    logical_config: dict[str, str] = Field(default_factory=dict)
    sha256: str | None = None


class SnapshotManifest(BaseModel):
    """Validated immutable snapshot metadata."""

    model_config = ConfigDict(extra="forbid")
    corpus_revision: str
    built_at: str
    page_count: int
    chunk_count: int
    source_hashes: dict[str, str]
    documentation_revision: str | None = None
    source_sizes: dict[str, int] = Field(default_factory=dict)
    build_config: BuildConfig = Field(default_factory=BuildConfig)
    components: dict[str, ComponentManifest] = Field(default_factory=dict)
    duplicate_content_groups: int = 0
    regression_override_reason: str | None = None
    build_stats: dict[str, int] = Field(default_factory=dict)


def calculate_revision(
    chunks: list[DocChunk],
    *,
    source_hashes: dict[str, str],
    build_config: BuildConfig | None = None,
    components: dict[str, ComponentManifest] | None = None,
) -> str:
    """Calculate a content-addressed revision without timestamps."""
    canonical = {
        "chunks": [chunk.model_dump(mode="json") for chunk in sorted(chunks, key=lambda item: item.chunk_id)],
        "source_hashes": dict(sorted(source_hashes.items())),
        "build_config": (build_config or BuildConfig()).model_dump(mode="json"),
        "components": {
            name: {
                "kind": component.kind,
                "relative_path": component.relative_path,
                "config": dict(sorted(component.logical_config.items())),
            }
            for name, component in sorted((components or {}).items())
        },
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"sha256:{digest}"


def write_snapshot(
    directory: Path,
    chunks: list[DocChunk],
    *,
    source_hashes: dict[str, str],
    source_sizes: dict[str, int] | None = None,
    build_config: BuildConfig | None = None,
    components: dict[str, ComponentManifest] | None = None,
    regression_override_reason: str | None = None,
    build_stats: dict[str, int] | None = None,
) -> SnapshotManifest:
    """Write canonical records and a manifest into a staged directory."""
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "manifest.json").exists() or (directory / "chunks.jsonl").exists():
        raise FileExistsError(f"snapshot records already exist in {directory}")
    component_values = components or {}
    effective_build_config = build_config or BuildConfig()
    revision = calculate_revision(
        chunks,
        source_hashes=source_hashes,
        build_config=effective_build_config,
        components=component_values,
    )
    with (directory / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in sorted(chunks, key=lambda item: item.chunk_id):
            handle.write(json.dumps(chunk.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) + "\n")
    manifest = SnapshotManifest(
        corpus_revision=revision,
        built_at=datetime.now(UTC).isoformat(),
        page_count=len(source_hashes),
        chunk_count=len(chunks),
        source_hashes=dict(sorted(source_hashes.items())),
        documentation_revision=documentation_revision(source_hashes),
        source_sizes=dict(sorted((source_sizes or {}).items())),
        build_config=effective_build_config,
        components=component_values,
        duplicate_content_groups=_duplicate_content_groups(chunks),
        regression_override_reason=regression_override_reason,
        build_stats=build_stats or {},
    )
    (directory / "manifest.json").write_text(
        manifest.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
    )
    return manifest


def _duplicate_content_groups(chunks: list[DocChunk]) -> int:
    counts = Counter((chunk.title, chunk.heading_path, chunk.content_markdown.strip()) for chunk in chunks)
    return sum(count > 1 for count in counts.values())


def load_snapshot(directory: Path, *, verify_components: bool = True) -> tuple[SnapshotManifest, list[DocChunk]]:
    """Load and verify an immutable snapshot's canonical records."""
    directory = directory.resolve(strict=True)
    manifest = SnapshotManifest.model_validate_json((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.documentation_revision is not None and manifest.documentation_revision != documentation_revision(
        manifest.source_hashes
    ):
        raise ValueError("snapshot documentation revision does not match source hashes")
    try:
        chunks = [
            DocChunk.model_validate_json(line)
            for line in (directory / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("snapshot contains malformed chunk records") from error
    if len(chunks) != manifest.chunk_count:
        raise ValueError("snapshot chunk count does not match manifest")
    expected = calculate_revision(
        chunks,
        source_hashes=manifest.source_hashes,
        build_config=manifest.build_config,
        components=manifest.components,
    )
    if expected != manifest.corpus_revision:
        raise ValueError("snapshot revision does not match canonical content")
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise ValueError("snapshot contains duplicate chunk IDs")
    if verify_components:
        for name, component in manifest.components.items():
            verify_component(directory, name, component)
    return manifest, chunks


def verify_component(snapshot: Path, name: str, component: ComponentManifest) -> Path:
    """Resolve and verify one component path inside a snapshot."""
    snapshot = snapshot.resolve(strict=True)
    component_path = (snapshot / component.relative_path).resolve(strict=True)
    if snapshot not in component_path.parents:
        raise ValueError(f"component path escapes snapshot: {name}")
    if component.sha256 and component.sha256 != tree_checksum(component_path):
        raise ValueError(f"component checksum mismatch: {name}")
    return component_path


def documentation_revision(source_hashes: dict[str, str]) -> str:
    """Identify canonical documentation inputs independently of retrieval indexes."""
    canonical = json.dumps(dict(sorted(source_hashes.items())), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def tree_checksum(directory: Path) -> str:
    """Hash all regular files in a directory deterministically."""
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(b"\0")
        update_digest_from_file(digest, path)
        digest.update(b"\0")
    return digest.hexdigest()


def file_checksum(path: Path) -> str:
    """Hash one file without loading it fully into memory."""
    digest = hashlib.sha256()
    update_digest_from_file(digest, path)
    return digest.hexdigest()


def update_digest_from_file(digest: Digest, path: Path) -> None:
    """Feed file bytes into an existing digest in fixed-size chunks."""
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)


def activate_snapshot(snapshot: Path, current: Path) -> None:
    """Atomically update a symlink after a snapshot has been validated."""
    snapshot = snapshot.resolve(strict=True)
    current.parent.mkdir(parents=True, exist_ok=True)
    temporary = current.with_name(f".{current.name}.tmp")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(snapshot, target_is_directory=True)
    temporary.replace(current)


def set_distribution_permissions(snapshot: Path) -> None:
    """Make a validated snapshot readable by non-root runtime containers."""
    snapshot.chmod(0o755)
    for path in snapshot.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
