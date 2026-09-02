# NiceGUI Documentation MCP Server

An unofficial, retrieval-only MCP server for NiceGUI documentation.
It builds immutable documentation snapshots offline and exposes exactly two tools:

- `search_docs(query, limit=5)` discovers ranked chunks.
- `get_doc_chunks(chunk_ids)` returns their full Markdown.

## Development

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Type checking uses Astral's Ty. It can also be run without installing the
development group with `uvx ty check .`.


## Build a corpus

BM25-only:

```bash
uv run nice-mcp build-corpus --output-root data --retrievers bm25
```

All retrieval components:

```bash
uv run nice-mcp build-corpus --output-root data --retrievers bm25,dense
```

By default, `auto` uses CUDA when available, then Apple MPS, and otherwise
falls back to CPU. Use `--dense-device cpu`, `--dense-device mps`, or
`--dense-device cuda` to override device selection.

The builder discovers NiceGUI pages from its search index, requests each page as
Markdown using `Accept: text/markdown`, validates and chunks it, builds selected
indexes, validates the staged snapshot, then atomically updates `data/current`.
It never scrapes the rendered HTML and does not co-index `llms.txt`.

Builds track only the latest NiceGUI documentation. By default, unchanged pages
reuse their existing chunks; changed and added pages are rechunked, removed
pages disappear, and every retrieval index is rebuilt from the current chunk
set. Use `--full-rebuild` to deliberately bypass page-chunk reuse.

Dense model weights are downloaded during an offline build and copied
into the immutable snapshot, so serving requires no network access. Each manifest
records the corpus revision, source hashes, build configuration, and retrieval
component metadata.

Validate and package a snapshot independently of the application image:

```bash
uv run nice-mcp validate-corpus data/current
uv run nice-mcp package-corpus data/current
```

## Run

```bash
NICE_MCP_SNAPSHOT_PATH=data/current \
NICE_MCP_RETRIEVER=hybrid \
uv run nice-mcp serve
```

Dense and hybrid retrieval use automatic device selection by default. Set
`NICE_MCP_DENSE_DEVICE=cpu`, `mps`, or `cuda` to override it.

Valid retrievers are `bm25`, `dense`, and `hybrid`.

Production MCP is Streamable HTTP at `/mcp`. `/health/live` and
`/health/ready` are ordinary HTTP health endpoints. Stdio is available locally:

```bash
uv run nice-mcp stdio
```
