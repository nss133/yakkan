from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .clause_split import split_by_jo
from .pdf_text import extract_text_pymupdf


@dataclass(frozen=True)
class PeerDocMeta:
    insurer: str
    insurer_code: str
    product_group: str  # whole_life / cancer / dementia ...
    doc_type: str  # TERMS / METHODS
    doc_id: str
    source_path: str


def index_pdf_to_document(meta: PeerDocMeta) -> dict:
    text = extract_text_pymupdf(meta.source_path)
    clauses = split_by_jo(text)

    # clause_id는 파일 단위로 유일하면 충분(MVP)
    out_clauses = []
    for i, c in enumerate(clauses, start=1):
        out_clauses.append(
            {
                "clause_id": f"{meta.doc_id}::jo::{i}",
                "clause_path": c.get("clause_path", ""),
                "title": c.get("title", ""),
                "source_ref": meta.source_path,
                "text": c.get("text", ""),
            }
        )

    return {
        "doc_id": meta.doc_id,
        "insurer": meta.insurer,
        "insurer_code": meta.insurer_code,
        "product_group": meta.product_group,
        "doc_type": meta.doc_type,
        "source_path": meta.source_path,
        "clauses": out_clauses,
    }


def write_documents_jsonl(docs: list[dict], out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return out_path

