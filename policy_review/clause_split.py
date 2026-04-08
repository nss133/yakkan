from __future__ import annotations

import re

from .text import normalize


_JO_HEADER_RE = re.compile(r"^\s*제\s*(\d+)\s*조\s*(?:\((.*?)\))?\s*$")
_JO_INLINE_RE = re.compile(r"(제\s*\d+\s*조)\s*(?:\(([^)]+)\))?")


def split_by_jo(text: str) -> list[dict]:
    """
    매우 단순한 MVP 조항 분리:
    - '제n조' 헤더를 기준으로 덩어리화
    - 약관 레이아웃이 다양해 완벽하진 않지만 peer 비교용 후보 축소에는 유효
    """
    t = normalize(text)
    if not t:
        return []

    lines = t.split("\n")
    chunks: list[dict] = []
    cur = None

    def flush():
        nonlocal cur
        if not cur:
            return
        cur["text"] = "\n".join(cur["lines"]).strip()
        cur.pop("lines", None)
        if cur["text"]:
            chunks.append(cur)
        cur = None

    for ln in lines:
        m = _JO_HEADER_RE.match(ln)
        if m:
            flush()
            jo_no = int(m.group(1))
            title = (m.group(2) or "").strip()
            cur = {
                "clause_path": f"제{jo_no}조",
                "title": title,
                "lines": [],
            }
            continue
        if cur is None:
            # 시작 전, 본문 중에 inline 제n조가 먼저 나오는 케이스 방어
            m2 = _JO_INLINE_RE.search(ln)
            if m2:
                flush()
                jo = m2.group(1).replace(" ", "")
                title = (m2.group(2) or "").strip()
                cur = {"clause_path": jo, "title": title, "lines": [ln]}
            continue
        cur["lines"].append(ln)

    flush()
    return chunks

