from __future__ import annotations

import re


_WS_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def normalize(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = _MULTI_NL_RE.sub("\n\n", t)
    t = "\n".join(_WS_RE.sub(" ", line).strip() for line in t.split("\n"))
    return t.strip()


_SENT_ENDINGS = [
    "다.",
    "함.",
    "한다.",
    "아니한다.",
    "됩니다.",
    "있다.",
    "없다.",
    "할 수 있다.",
    "할수있다.",
]


def split_sentences(text: str) -> list[str]:
    """
    한국어 약관 MVP용 문장 분리.
    - 줄바꿈을 먼저 정리한 뒤
    - 종결 표현(…다./…한다./…아니한다./…됩니다.) 기준으로 1차 분리
    """
    t = normalize(text)
    if not t:
        return []

    # 줄 기반 1차 분리 후 종결 표현 기반으로 2차 분리
    lines: list[str] = [ln.strip() for ln in t.split("\n") if ln.strip()]
    out: list[str] = []
    for ln in lines:
        s = ln
        # 가장 긴 종결 표현부터 매칭(예: "할 수 있다."가 "다."로 잘리는 것 방지)
        endings = sorted(_SENT_ENDINGS, key=len, reverse=True)
        buf = ""
        while s:
            cut_at = None
            cut_end = None
            for e in endings:
                idx = s.find(e)
                if idx == -1:
                    continue
                end_idx = idx + len(e)
                if cut_at is None or end_idx < cut_at:
                    cut_at = end_idx
                    cut_end = e
            if cut_at is None:
                buf = (buf + " " + s).strip() if buf else s.strip()
                break
            head = s[:cut_at].strip()
            if head:
                out.append(head)
            s = s[cut_at:].strip()
        if buf:
            out.append(buf)

    # 너무 짧은 조각/중복 제거
    cleaned: list[str] = []
    seen = set()
    for s in (x.strip() for x in out):
        if len(s) < 4:
            continue
        if s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
    return cleaned

