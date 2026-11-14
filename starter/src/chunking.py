"""Fixed-size and paragraph-aware chunking strategies."""
import hashlib
import re
from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, text: str, ordinal: int, strategy: str) -> Chunk:
    payload = f"{strategy}|{page.document_id}|{page.page}|{ordinal}|{text}"
    return Chunk(
        chunk_id=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        document_id=page.document_id, source=page.source, page=page.page,
        text=text, metadata={**page.metadata, "chunk_strategy": strategy, "chunk_ordinal": ordinal},
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split text into character windows and retain page metadata."""
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("Require size > 0 and 0 <= overlap < size")
    text = page.text.strip()
    if not text:
        return []
    step = size - overlap
    chunks = []
    for ordinal, start in enumerate(range(0, len(text), step)):
        part = text[start:start + size].strip()
        if part:
            chunks.append(_chunk(page, part, ordinal, "fixed"))
        if start + size >= len(text):
            break
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Pack complete paragraphs up to max_size; split only oversized paragraphs."""
    if max_size < 1:
        raise ValueError("max_size must be positive")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
    parts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            if current:
                parts.append(current)
                current = ""
            parts.extend(paragraph[i:i + max_size] for i in range(0, len(paragraph), max_size))
        elif not current:
            current = paragraph
        elif len(current) + 2 + len(paragraph) <= max_size:
            current += "\n\n" + paragraph
        else:
            parts.append(current)
            current = paragraph
    if current:
        parts.append(current)
    return [_chunk(page, text, i, "paragraph") for i, text in enumerate(parts)]
