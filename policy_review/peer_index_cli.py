from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from .peer_index import PeerDocMeta, index_pdf_to_document, write_documents_jsonl


def main():
    ap = argparse.ArgumentParser(description="타사 약관/사업방법서 PDF → 조항 인덱싱(JSONL)")
    ap.add_argument("--insurer", required=True, help="보험사명(표시용)")
    ap.add_argument("--insurer-code", required=True, help="보험사 코드(폴더명)")
    ap.add_argument("--product-group", required=True, help="상품군(whole_life/cancer/dementia 등)")
    ap.add_argument("--doc-type", default="TERMS", help="문서 타입(TERMS=약관, METHODS=사업방법서)")
    ap.add_argument("--pdf-dir", required=True, help="원문 PDF가 있는 폴더(수동 다운로드 폴더 가능)")
    ap.add_argument("--out", default="", help="출력 JSONL 경로(기본: peer_data/index/...)")
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir)
    pdfs = sorted([p for p in pdf_dir.glob("*.pdf") if p.is_file()])
    if not pdfs:
        raise SystemExit(f"PDF 없음: {pdf_dir}")

    docs = []
    for p in pdfs:
        doc_id = f"{args.insurer_code}::{args.product_group}::{uuid.uuid4().hex[:10]}"
        meta = PeerDocMeta(
            insurer=args.insurer,
            insurer_code=args.insurer_code,
            product_group=args.product_group,
            doc_type=str(args.doc_type).upper(),
            doc_id=doc_id,
            source_path=str(p),
        )
        docs.append(index_pdf_to_document(meta))

    out = args.out
    if not out:
        out = f"peer_data/index/{args.insurer_code}/{args.product_group}/{str(args.doc_type).upper()}/documents.jsonl"
    out_path = write_documents_jsonl(docs, out)
    print(f"[ok] wrote {len(docs)} documents to {out_path}")


if __name__ == "__main__":
    main()

