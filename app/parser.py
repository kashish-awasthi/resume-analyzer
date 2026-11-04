"""Extract plain text from uploaded resume files (PDF, DOCX, TXT)."""

from __future__ import annotations

import io

from docx import Document
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


class ResumeParseError(ValueError):
    """Raised when a file can't be turned into text."""


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def extract_text(filename: str, data: bytes) -> str:
    """Return the text content of a resume file."""
    if not data:
        raise ResumeParseError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ResumeParseError("File is larger than 5 MB.")

    ext = _extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ResumeParseError(
            f"Unsupported file type '{ext or 'none'}'. Upload a PDF, DOCX or TXT file."
        )

    try:
        if ext == ".pdf":
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext == ".docx":
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(parts)
        else:
            text = data.decode("utf-8", errors="replace")
    except ResumeParseError:
        raise
    except Exception as exc:  # corrupt or encrypted files
        raise ResumeParseError(f"Could not read the file: {exc}") from exc

    text = text.strip()
    if len(text) < 50:
        raise ResumeParseError(
            "Very little text was found. If this is a scanned PDF, export it as a text-based PDF."
        )
    return text
