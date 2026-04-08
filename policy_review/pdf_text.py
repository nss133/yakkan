from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def extract_text_pymupdf(pdf_path: str | Path) -> str:
    """
    텍스트형 PDF 기준 MVP 추출기.
    스캔/OCR은 별도 단계(추후)로 분리.
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    try:
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text("text") or "")
        return "\n".join(parts).strip()
    finally:
        doc.close()

