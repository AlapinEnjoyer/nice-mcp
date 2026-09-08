"""Command-line interface for corpus and server operations."""

import json
from pathlib import Path

import typer

from nice_mcp.config import Settings, get_settings
from nice_mcp.corpus.artifact import install_artifact, package_snapshot
from nice_mcp.corpus.build import BUILD_COMPONENTS, build_corpus_snapshot, reindex_snapshot
from nice_mcp.corpus.snapshot import (
    activate_snapshot,
    load_snapshot,
)
from nice_mcp.corpus.validation import validate_chunks
from nice_mcp.server.app import create_http_app, create_mcp_server
from nice_mcp.server.runtime import CorpusService

app = typer.Typer(no_args_is_help=True, help="Build and serve NiceGUI documentation snapshots.")


def _parse_component_set(value: str, *, allowed: set[str], require: str | None = None) -> set[str]:
    """Parse and validate a comma-separated component list."""
    items = {item.strip() for item in value.split(",") if item.strip()}
    if require:
        items.add(require)
    if invalid := items - allowed:
        raise typer.BadParameter(f"unknown components: {sorted(invalid)}")
    return items


@app.command("build-corpus")
def build_corpus(
    output_root: Path = typer.Option(Path("data"), help="Snapshot root containing snapshots/ and current."),
    retrievers: str = typer.Option("bm25", help="Comma-separated components: bm25,dense."),
    regression_override: str | None = typer.Option(None, help="Audited reason to bypass count regression gates."),
    full_rebuild: bool = typer.Option(False, "--full-rebuild", help="Ignore reusable page chunks."),
    dense_device: str = typer.Option("auto", help="Dense build device: auto, cpu, or mps."),
) -> None:
    """Fetch, chunk, index, validate, and atomically activate a corpus."""
    requested = _parse_component_set(retrievers, allowed=BUILD_COMPONENTS, require="bm25")
    current = output_root / "current"
    built = build_corpus_snapshot(
        output_root,
        requested,
        regression_override=regression_override,
        full_rebuild=full_rebuild,
        dense_device=dense_device,
    )
    activate_snapshot(built.path, current)
    typer.echo(built.manifest.model_dump_json(indent=2))


@app.command("build-index")
def build_index(
    snapshot: Path = typer.Argument(..., exists=True),
    output_root: Path = typer.Option(Path("data")),
    retrievers: str = typer.Option("bm25,dense"),
    dense_device: str = typer.Option("auto", help="Dense build device: auto, cpu, or mps."),
) -> None:
    """Create a new immutable revision with selected retrieval components."""
    requested = _parse_component_set(retrievers, allowed=BUILD_COMPONENTS, require="bm25")
    built = reindex_snapshot(snapshot, output_root, requested, dense_device=dense_device)
    typer.echo(str(built.path))


@app.command("validate-corpus")
def validate_corpus(snapshot: Path = typer.Argument(..., exists=True)) -> None:
    """Validate a built immutable corpus snapshot."""
    manifest, chunks = load_snapshot(snapshot)
    report = validate_chunks(chunks)
    typer.echo(json.dumps({**report.__dict__, "corpus_revision": manifest.corpus_revision}, indent=2))


@app.command("package-corpus")
def package_corpus(snapshot: Path, output: Path | None = None) -> None:
    """Package a validated snapshot as a separately deployable artifact."""
    manifest, _ = load_snapshot(snapshot)
    target = output or Path("artifacts") / f"nicegui-corpus-{manifest.corpus_revision.removeprefix('sha256:')}.tar.gz"
    typer.echo(str(package_snapshot(snapshot, target)))


@app.command("install-corpus")
def install_corpus(
    archive: Path = typer.Argument(..., exists=True), output_root: Path = typer.Option(Path("data"))
) -> None:
    """Install, validate, and atomically select a corpus artifact."""
    target = install_artifact(archive, output_root / "snapshots")
    activate_snapshot(target, output_root / "current")
    typer.echo(str(target))


def _load_service() -> tuple[Settings, CorpusService]:
    """Load runtime settings and corpus service."""
    settings = get_settings()
    return settings, CorpusService.load(
        settings.snapshot_path,
        settings.retriever,
        dense_device=settings.dense_device,
    )


@app.command("serve")
def serve() -> None:
    """Serve Streamable HTTP at /mcp."""
    import uvicorn

    settings, service = _load_service()
    uvicorn.run(
        create_http_app(service),
        host=settings.host,
        port=settings.port,
    )


@app.command("stdio")
def stdio() -> None:
    """Run a local stdio MCP transport for testing."""
    _, service = _load_service()
    create_mcp_server(service).run("stdio")


def main() -> None:
    """Run the Typer application."""
    app()
