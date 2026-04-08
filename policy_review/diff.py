from __future__ import annotations

import re
from typing import Iterable

from .models import QuantityDelta, RuleHit
from .text import split_sentences


def classify_focus_axis(text: str) -> str:
    t = text
    payment = sum(t.count(k) for k in ["보험금", "지급", "지급사유", "지급요건", "지급기준", "보상", "면책", "감액", "한도"])
    definition = sum(t.count(k) for k in ["정의", "이라 함", "의미", "이란", "정의한다"])
    procedure = sum(t.count(k) for k in ["청구", "통지", "제출서류", "기한", "기간", "이내"])
    exclusion = sum(t.count(k) for k in ["지급하지", "보상하지", "면책"])
    scores = {
        "PAYMENT": payment,
        "DEFINITION": definition,
        "PROCEDURE": procedure,
        "EXCLUSION": exclusion,
    }
    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "OTHER"


def change_type(old_text: str | None, new_text: str) -> str:
    if old_text is None:
        return "ADDED"
    if old_text.strip() == new_text.strip():
        return "UNCHANGED"
    return "MODIFIED"


_EXCPT_RE = re.compile(r"(다만|단\s*,)")


def diff_scope(old_text: str | None, new_text: str, deltas: list[QuantityDelta], rule_hits: list[RuleHit]) -> str:
    """
    MVP 규칙:
    - 예외(다만/단) 삭제되면 BROADER 우선
    - 지급 제한/요건 강화 태그가 있으면 BROADER
    - 반대(요건 완화 등)는 본 MVP에선 약하게 처리
    """
    old_text = old_text or ""
    old_excpt = bool(_EXCPT_RE.search(old_text))
    new_excpt = bool(_EXCPT_RE.search(new_text))
    if old_excpt and not new_excpt:
        return "BROADER"

    tags = {h.tag for h in rule_hits}
    if tags.intersection({"PAYMENT_CONDITION_TIGHTENING", "PAYMENT_LIMITATION_EXPANSION", "EXCLUSION_EXPANSION", "PAYMENT_RESTRICTION"}):
        return "BROADER"

    # 수치 변화 중 불리 강화가 있으면 BROADER
    for d in deltas:
        if d.label in {"청구/통지기한", "지급한도", "지급횟수"} and d.direction == "DECREASE":
            return "BROADER"
        if d.label == "대기/면책기간" and d.direction == "INCREASE":
            return "BROADER"

    return "UNCLEAR"


def pick_key_snippets(
    old_text: str | None,
    new_text: str,
    rule_hits: list[RuleHit],
    deltas: list[QuantityDelta],
    max_sentences: int = 2,
) -> tuple[str, str]:
    old_sents = split_sentences(old_text or "")
    new_sents = split_sentences(new_text)
    if not new_sents:
        return ("", "")

    # 룰이 걸린 문장 가산점 맵
    hit_weight_by_sentence: dict[str, int] = {}
    for h in rule_hits:
        hit_weight_by_sentence[h.evidence_sentence] = max(hit_weight_by_sentence.get(h.evidence_sentence, 0), h.weight)

    def score_sentence(s: str) -> int:
        score = 0
        # 지급/정의 키워드
        score += 3 * sum(1 for k in ["보험금", "지급", "면책", "감액", "한도", "대기기간", "청구", "통지"] if k in s)
        score += 1 * sum(1 for k in ["정의", "이라 함", "의미"] if k in s)
        # 룰 히트 가산
        score += hit_weight_by_sentence.get(s, 0)
        # 수치 포함 가산
        if re.search(r"\d+\s*(일|개월|년|원|만원|억원|회|번|%|퍼센트)", s):
            score += 8
        return score

    ranked_new = sorted(new_sents, key=score_sentence, reverse=True)[:max_sentences]
    key_new = " ".join(ranked_new).strip()

    # 각 신문장에 가장 유사한 구문장(단순 토큰 Jaccard)
    def jaccard(a: str, b: str) -> float:
        ta = set(a.split())
        tb = set(b.split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    matched_old: list[str] = []
    for s_new in ranked_new:
        best = ("", 0.0)
        for s_old in old_sents:
            sim = jaccard(s_new, s_old)
            if sim > best[1]:
                best = (s_old, sim)
        if best[1] >= 0.35 and best[0]:
            matched_old.append(best[0])
    key_old = " ".join(matched_old).strip()
    return (key_old, key_new)

