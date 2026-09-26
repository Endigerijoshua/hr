"""
Extract plain text from a resume file, regardless of domain (engineering,
sales, arts, finance, etc.) — domain-agnostic on purpose, since we're just
pulling raw text here. Domain-specific interpretation happens in score.py.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import docx


def extract_text(path: str) -> str:
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(p)
    elif suffix == ".docx":
        return _extract_docx(p)
    elif suffix in (".txt", ".md"):
        return p.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported resume file type: {suffix} ({path})")


def _extract_pdf(path: Path) -> str:
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n".join(text_parts)


def _extract_docx(path: Path) -> str:
    document = docx.Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)
