"""Deterministic structural Markdown chunking."""

import hashlib
import re
import unicodedata
from collections.abc import Callable
from urllib.parse import urldefrag

from nice_mcp.corpus.models import DocChunk, RawPage
from nice_mcp.corpus.parsing import parse_sections, semantic_blocks

LIST_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+")
NON_SLUG = re.compile(r"[^a-z0-9]+")
TokenCounter = Callable[[str], int]


def normalize_heading_path(path: tuple[str, ...]) -> str:
    """Normalize a heading path for stable identity derivation."""
    return "/".join(" ".join(unicodedata.normalize("NFKC", item).casefold().split()) for item in path)


def chunk_id_for(base_url: str, heading_path: tuple[str, ...], local_ordinal: int) -> str:
    """Generate a deterministic chunk ID."""
    clean_url, _ = urldefrag(base_url.rstrip("/"))
    identity = f"{clean_url}\n{normalize_heading_path(heading_path)}\n{local_ordinal}"
    return "ngc_" + hashlib.sha256(identity.encode()).hexdigest()[:12]


def heading_fragment(heading: str) -> str:
    """Convert a documentation heading to a stable URL fragment."""
    return NON_SLUG.sub("-", unicodedata.normalize("NFKC", heading).casefold()).strip("-")


def _group_blocks(blocks: list[str], preferred: int, hard: int, count_tokens: TokenCounter) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for original_block in blocks:
        for block in _split_large_block(original_block, hard, count_tokens):
            current, current_tokens = _append_grouped_block(
                groups, current, current_tokens, block, preferred=preferred, hard=hard, count_tokens=count_tokens
            )
    if current:
        groups.append(current)
    return groups


def _append_grouped_block(
    groups: list[list[str]],
    current: list[str],
    current_tokens: int,
    block: str,
    *,
    preferred: int,
    hard: int,
    count_tokens: TokenCounter,
) -> tuple[list[str], int]:
    """Append one semantic block while honoring preferred and hard chunk targets."""
    tokens = count_tokens(block)
    if current and (current_tokens >= preferred or current_tokens + tokens > hard):
        groups.append(current)
        current, current_tokens = [], 0
    if tokens > hard:
        groups.append([block])
        return [], 0
    current.append(block)
    return current, current_tokens + tokens


def _split_large_block(block: str, hard: int, count_tokens: TokenCounter) -> list[str]:
    """Split oversized prose/list blocks without touching fenced code blocks."""
    if count_tokens(block) <= hard or block.lstrip().startswith(("```", "~~~")):
        return [block]
    pieces = _split_markdown_list_block(block)
    if len(pieces) == 1:
        return _split_by_lines(block, hard, count_tokens)
    return [piece for piece in pieces for piece in _split_large_block(piece, hard, count_tokens)]


def _split_markdown_list_block(block: str) -> list[str]:
    """Split a large Markdown list at the shallowest useful list-item boundary."""
    lines = block.splitlines(keepends=True)
    matches = [
        (index, len(match.group(1))) for index, line in enumerate(lines) if (match := LIST_ITEM.match(line)) is not None
    ]
    for indent in sorted({indent for _, indent in matches}):
        split_at = {index for index, item_indent in matches if item_indent == indent}
        if len(split_at) < 2:
            continue
        groups: list[str] = []
        current: list[str] = []
        for index, line in enumerate(lines):
            if index in split_at and current:
                groups.append("".join(current).rstrip() + "\n")
                current = []
            current.append(line)
        if current:
            groups.append("".join(current).rstrip() + "\n")
        return groups
    return [block]


def _split_by_lines(block: str, hard: int, count_tokens: TokenCounter) -> list[str]:
    """Fallback split for oversized prose with no useful list boundaries."""
    groups: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for line in block.splitlines(keepends=True):
        tokens = count_tokens(line)
        if current and current_tokens + tokens > hard:
            groups.append("".join(current).rstrip() + "\n")
            current, current_tokens = [], 0
        current.append(line)
        current_tokens += tokens
    if current:
        groups.append("".join(current).rstrip() + "\n")
    return groups


def chunk_page(
    page: RawPage,
    *,
    preferred_tokens: int = 450,
    hard_tokens: int = 500,
    token_counter: TokenCounter,
) -> list[DocChunk]:
    """Chunk one Markdown page and populate deterministic adjacency links."""
    title, sections = parse_sections(page.content_markdown, fallback_title=page.page_id.replace("-", " ").title())
    chunks: list[DocChunk] = []
    next_ordinal: dict[str, int] = {}
    for section in sections:
        path_key = normalize_heading_path(section.heading_path)
        for blocks in _group_blocks(semantic_blocks(section.body), preferred_tokens, hard_tokens, token_counter):
            ordinal = next_ordinal.get(path_key, 0)
            next_ordinal[path_key] = ordinal + 1
            content = section.heading_line.rstrip() + "\n\n" + "\n".join(block.rstrip() for block in blocks) + "\n"
            chunk_id = chunk_id_for(page.canonical_url, section.heading_path, ordinal)
            chunks.append(
                DocChunk(
                    chunk_id=chunk_id,
                    page_id=page.page_id,
                    title=title,
                    heading_path=section.heading_path,
                    content_markdown=content,
                    canonical_url=f"{page.canonical_url}#{heading_fragment(section.heading_path[-1])}",
                    local_ordinal=ordinal,
                    previous_chunk_id=None,
                    next_chunk_id=None,
                )
            )
    return [
        chunk.model_copy(
            update={
                "previous_chunk_id": chunks[index - 1].chunk_id if index else None,
                "next_chunk_id": chunks[index + 1].chunk_id if index + 1 < len(chunks) else None,
            }
        )
        for index, chunk in enumerate(chunks)
    ]
