"""Parse NiceGUI's generated Markdown into retrieval-friendly sections."""

import re
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
DECORATIVE_BLOCK = re.compile(r"^(?:\[Button(?::[^]]+)?\]|main\.py|example)$", re.IGNORECASE)
FOOTER_MARKER = "\n**Nice**GUI\n\nThe Python UI framework that shows up in your browser."


@dataclass(frozen=True)
class MarkdownSection:
    """Markdown content belonging to one semantic heading path."""

    heading_path: tuple[str, ...]
    heading_line: str
    body: str


def parse_sections(markdown: str, *, fallback_title: str) -> tuple[str, list[MarkdownSection]]:
    """Split Markdown into heading-scoped sections without inspecting fenced code."""
    lines = strip_page_shell(markdown).splitlines(keepends=True)
    path: list[str] = []
    title = fallback_title
    sections: list[MarkdownSection] = []
    current_heading = f"# {fallback_title}\n"
    body: list[str] = []
    fence_marker: str | None = None
    reference_context: str | None = None

    def flush() -> None:
        content = "".join(body).strip()
        if content:
            sections.append(MarkdownSection(tuple(path or [title]), current_heading, content + "\n"))
        body.clear()

    for line in lines:
        fence_match = FENCE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence_marker is None:
                fence_marker = marker
            elif marker == fence_marker:
                fence_marker = None
            body.append(line)
            continue
        heading_match = HEADING.match(line.rstrip("\n")) if fence_marker is None else None
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip().replace("*", "")
            if level == 1 and title == fallback_title:
                title = text
            if level == 1:
                reference_context = None
                path[:] = [text]
            # NiceGUI emits API reference markers as empty H2 headings, then
            # emits their detail sections as sibling H2 headings. Preserve the
            # logical component context until the next reference marker.
            elif level == 2 and text.casefold().startswith("reference for "):
                reference_context = text
                path[:] = [title, text]
            elif level == 2 and reference_context is not None:
                path[:] = [title, reference_context, text]
            else:
                path[:] = path[: level - 1]
                while len(path) < level - 1:
                    path.append(title)
                path.append(text)
            current_heading = line if line.endswith("\n") else line + "\n"
        else:
            body.append(line)
    flush()
    return title, sections


def strip_page_shell(markdown: str) -> str:
    """Remove NiceGUI's repeated navigation shell before the actual page heading."""
    normalized = markdown.replace("\r\n", "\n")
    lines = normalized.splitlines(keepends=True)
    top_level: list[tuple[int, str]] = []
    fence_marker: str | None = None
    for index, line in enumerate(lines):
        fence_match = FENCE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            fence_marker = marker if fence_marker is None else None if marker == fence_marker else fence_marker
            continue
        if fence_marker is None and (match := HEADING.match(line.rstrip("\n"))) and len(match.group(1)) == 1:
            top_level.append((index, match.group(2).strip()))
    if len(top_level) >= 2:
        first_index, first_title = top_level[0]
        second_index, _ = top_level[1]
        shell = "".join(lines[first_index:second_index])
        is_nicegui_shell = first_title.casefold() == "nicegui" or first_title.casefold().endswith("| nicegui")
        if is_nicegui_shell and "[Button: icon:menu]" in shell and "[Documentation]" in shell:
            normalized = "".join(lines[second_index:])
    footer = normalized.find(FOOTER_MARKER)
    return normalized[:footer].rstrip() + "\n" if footer >= 0 else normalized


def semantic_blocks(markdown: str) -> list[str]:
    """Split a section body into paragraphs and indivisible fenced blocks."""
    blocks: list[str] = []
    current: list[str] = []
    fence_marker: str | None = None
    for line in markdown.splitlines(keepends=True):
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence_marker is None:
                if current and "".join(current).strip():
                    _append_prose_block(blocks, current)
                current = [line]
                fence_marker = marker
                continue
            current.append(line)
            if marker == fence_marker:
                blocks.append("".join(current).rstrip() + "\n")
                current = []
                fence_marker = None
            continue
        if fence_marker is not None:
            current.append(line)
        elif not line.strip():
            if current and "".join(current).strip():
                _append_prose_block(blocks, current)
            current = []
        else:
            current.append(line)
    if current and "".join(current).strip():
        _append_prose_block(blocks, current)
    return blocks


def _append_prose_block(blocks: list[str], lines: list[str]) -> None:
    content = "".join(lines).strip()
    if content and not DECORATIVE_BLOCK.fullmatch(content):
        blocks.append(content + "\n")
