"""Turn an uploaded file into plain text with page markers.

Downstream code (chunking, citations, the review grid) relies on the
``[[page N]]`` markers to attribute an answer back to a page number, so the
marker format is part of this module's contract.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

PAGE_MARKER = "[[page {n}]]"
PAGE_MARKER_RE = re.compile(r"\[\[page (\d+)\]\]")


@dataclass
class Extraction:
    text: str
    pages: int
    kind: str
    words: int = 0
    warnings: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("﻿", "")
    # Collapse runs of spaces/tabs but keep paragraph breaks meaningful.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _join_pages(pages: list[str]) -> str:
    parts = []
    for i, body in enumerate(pages, start=1):
        body = _clean(body)
        if not body:
            continue
        parts.append(f"{PAGE_MARKER.format(n=i)}\n{body}")
    return "\n\n".join(parts)


def _from_pdf(path: Path) -> Extraction:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    warnings: list[str] = []
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # a single bad page shouldn't kill the upload
            pages.append("")
            warnings.append(f"page {len(pages)}: {exc}")

    text = _join_pages(pages)
    if not text:
        warnings.append(
            "No selectable text found — this looks like a scanned PDF and needs OCR."
        )
    return Extraction(text=text, pages=len(reader.pages), kind="pdf", warnings=warnings)


def _from_docx(path: Path) -> Extraction:
    import docx

    document = docx.Document(str(path))
    blocks: list[str] = []
    for para in document.paragraphs:
        if para.text.strip():
            style = (para.style.name or "").lower() if para.style else ""
            if style.startswith("heading"):
                blocks.append(f"\n## {para.text.strip()}")
            else:
                blocks.append(para.text.strip())

    for table in document.tables:
        rows = []
        for row in table.rows:
            cells = [c.text.strip().replace("|", "\\|") for c in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            blocks.append("\n" + "\n".join(rows))

    body = "\n".join(blocks)
    # Word has no fixed pagination; approximate for citation purposes.
    return Extraction(text=_join_pages(_paginate(body)), pages=0, kind="docx")


def _from_text(path: Path, kind: str) -> Extraction:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return Extraction(text=_join_pages(_paginate(raw)), pages=0, kind=kind)


def _paginate(body: str, chars_per_page: int = 3000) -> list[str]:
    """Split flat text into pseudo-pages on paragraph boundaries."""
    body = _clean(body)
    if not body:
        return []
    pages, current = [], ""
    for para in body.split("\n\n"):
        if current and len(current) + len(para) > chars_per_page:
            pages.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        pages.append(current)
    return pages


def extract(path: Path, max_chars: int) -> Extraction:
    """Extract text from ``path``, truncating to ``max_chars``."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        result = _from_pdf(path)
    elif suffix == ".docx":
        result = _from_docx(path)
    elif suffix in {".md", ".markdown"}:
        result = _from_text(path, "markdown")
    else:
        result = _from_text(path, "text")

    if len(result.text) > max_chars:
        result.text = result.text[:max_chars]
        result.warnings.append(
            f"Document truncated to {max_chars:,} characters for analysis."
        )

    if result.pages == 0:
        result.pages = len(PAGE_MARKER_RE.findall(result.text))
    result.words = len(result.text.split())
    return result


def page_of(text: str, offset: int) -> int:
    """Page number that ``offset`` falls on within marker-annotated text."""
    page = 0
    for match in PAGE_MARKER_RE.finditer(text):
        if match.start() > offset:
            break
        page = int(match.group(1))
    return page


def strip_markers(text: str) -> str:
    return PAGE_MARKER_RE.sub("", text).strip()
