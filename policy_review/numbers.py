from __future__ import annotations

import re
from collections import defaultdict

from .models import QuantityDelta


_Q_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(일|개월|년|원|만원|억원|회|번|%|퍼센트)")


def _to_float(s: str) -> float:
    try:
        return float(s)
    except Exception:
        return 0.0


def extract_quantities(text: str) -> list[tuple[float, str, str]]:
    """
    returns [(value, unit, raw_match)]
    """
    out: list[tuple[float, str, str]] = []
    for m in _Q_RE.finditer(text):
        val = _to_float(m.group(1))
        unit = m.group(2)
        raw = m.group(0)
        out.append((val, unit, raw))
    return out


def _context_label(text: str, start: int, end: int) -> str:
    # 주변 40자 문맥으로 단순 라벨링(지급 중심)
    left = max(0, start - 40)
    right = min(len(text), end + 40)
    ctx = text[left:right]
    if re.search(r"(청구|통지)\s*(기한|기간)|(\d+)\s*(일|개월|년)\s*(이내|내).*(청구|통지)", ctx):
        return "청구/통지기한"
    if re.search(r"(대기기간|면책기간)", ctx):
        return "대기/면책기간"
    if re.search(r"(한도|상한|최대)\s*(금액|액|)", ctx):
        return "지급한도"
    if re.search(r"(최대|총)\s*\d+\s*(회|번)|(횟수|회수)", ctx):
        return "지급횟수"
    if re.search(r"(감액|공제)|(%|퍼센트)\s*(감액|공제)", ctx):
        return "감액/공제"
    return "수치"


def compare_quantities(old_text: str | None, new_text: str) -> list[QuantityDelta]:
    """
    매우 단순한 MVP:
    - old/new에서 수치를 뽑고, (label, unit)별로 "첫번째 값"을 비교
    - 실제 운영에선 동일 항목을 더 정교하게 매칭해야 함
    """
    old_text = old_text or ""
    old_hits = [(m.start(), m.end(), _to_float(m.group(1)), m.group(2)) for m in _Q_RE.finditer(old_text)]
    new_hits = [(m.start(), m.end(), _to_float(m.group(1)), m.group(2)) for m in _Q_RE.finditer(new_text)]

    old_map: dict[tuple[str, str], float] = {}
    for st, en, v, u in old_hits:
        lbl = _context_label(old_text, st, en)
        old_map.setdefault((lbl, u), v)

    deltas: list[QuantityDelta] = []
    seen = set()
    for st, en, v_new, u in new_hits:
        lbl = _context_label(new_text, st, en)
        key = (lbl, u)
        if key in seen:
            continue
        seen.add(key)
        v_old = old_map.get(key)
        if v_old is None:
            continue
        if abs(v_new - v_old) < 1e-9:
            continue
        direction = "INCREASE" if v_new > v_old else "DECREASE"
        deltas.append(
            QuantityDelta(
                unit=u,
                old_value=v_old,
                new_value=v_new,
                direction=direction,
                label=lbl,
            )
        )

    return deltas


def deltas_to_summary(deltas: list[QuantityDelta]) -> str:
    parts: list[str] = []
    for d in deltas:
        arrow = "→"
        parts.append(f"{d.label}: {d.old_value:g}{d.unit}{arrow}{d.new_value:g}{d.unit}")
    return "; ".join(parts)


def deltas_penalty(deltas: list[QuantityDelta]) -> int:
    """
    지급 관점의 '불리 강화' 페널티(최대 +15):
    - 청구/통지기한 감소: 불리 (+5)
    - 대기/면책기간 증가: 불리 (+5)
    - 지급한도 감소: 불리 (+5)
    - 지급횟수 감소: 불리 (+5)
    - 감액/공제(%) 증가: 불리 (+5)
    """
    score = 0
    for d in deltas:
        if d.label == "청구/통지기한" and d.direction == "DECREASE":
            score += 5
        elif d.label == "대기/면책기간" and d.direction == "INCREASE":
            score += 5
        elif d.label == "지급한도" and d.direction == "DECREASE":
            score += 5
        elif d.label == "지급횟수" and d.direction == "DECREASE":
            score += 5
        elif d.label == "감액/공제" and d.direction == "INCREASE":
            score += 5
    return min(score, 15)

