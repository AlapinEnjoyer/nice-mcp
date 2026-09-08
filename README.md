# NiceGUI Documentation MCP Server

An unofficial, retrieval-only MCP server for NiceGUI documentation.
It builds immutable documentation snapshots offline and exposes exactly two tools:

- `search_docs(query, limit=5)` discovers ranked chunks.
- `get_doc_chunks(chunk_ids)` returns their full Markdown.

## Docker

Build a self-contained CPU image with the application, current NiceGUI
documentation, indexes, and model assets:

```bash
docker build -f deploy/Dockerfile -t nice-mcp .
```

The image can then run from any directory without the repository or a mounted
data directory:

```bash
docker run -d \
  --name nice-mcp \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  nice-mcp
```

The MCP endpoint is available at `http://127.0.0.1:8000/mcp`. Serving is fully
offline; rebuild the image to update the bundled documentation. If Docker reuses
the corpus layer, pass a changed value such as
`--build-arg CORPUS_REFRESH=2026-09-08`.

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

By default, `auto` uses Apple MPS when available and otherwise falls back to
CPU. Use `--dense-device cpu` or `--dense-device mps` to override selection.

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
`NICE_MCP_DENSE_DEVICE=cpu` or `mps` to override it.

Valid retrievers are `bm25`, `dense`, and `hybrid`.

Production MCP is Streamable HTTP at `/mcp`. `/health/live` and
`/health/ready` are ordinary HTTP health endpoints. Stdio is available locally:

```bash
uv run nice-mcp stdio
```
