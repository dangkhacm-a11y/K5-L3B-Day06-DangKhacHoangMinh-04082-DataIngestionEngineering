"""Read and normalize PDF pages while preserving source/page traceability."""
import re
import unicodedata
from pathlib import Path
from .models import DocumentPage
from pypdf import PdfReader


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical page; keep its 1-based physical page number.

    Detect and record pages with no text. OCR, when needed, is a separate step.
    """
    reader = PdfReader(str(path))
    pages: list[DocumentPage] = []
    section = "front_matter"
    for number, pdf_page in enumerate(reader.pages, start=1):
        raw = pdf_page.extract_text() or ""
        text = normalize_text(raw)
        chapter_match = re.search(r"(?:Chapter Outline\s+|\b)([1-9])\.\d", text)
        chapter = int(chapter_match.group(1)) if chapter_match else None
        # Preserve the most recent numbered section heading as useful filter metadata.
        for line in text.splitlines():
            match = re.match(r"^\s*(\d+(?:\.\d+)*)\s+(.{3,100})$", line)
            if match:
                section = f"{match.group(1)} {match.group(2).strip()}"
                break
        pages.append(DocumentPage(
            document_id=document_id,
            source=source,
            page=number,
            text=text,
            metadata={"section": section, "chapter": chapter,
                      "extraction_status": "ok" if text else "empty"},
        ))
    return pages


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace without flattening paragraph boundaries."""
    text = unicodedata.normalize("NFC", text).replace("\u00ad", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[\t\f\v ]+", " ", line).strip() for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()
