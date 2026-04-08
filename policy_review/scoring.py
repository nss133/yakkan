from __future__ import annotations

from collections import defaultdict

from .models import RuleHit, QuantityDelta
from .numbers import deltas_penalty


def compute_risk(
    rule_hits: list[RuleHit],
    deltas: list[QuantityDelta],
    peer_coverage: int,
    score_clamp: tuple[int, int] = (0, 100),
) -> tuple[list[str], int, str]:
    tags = sorted({h.tag for h in rule_hits})
    score = sum(h.weight for h in rule_hits)
    score += deltas_penalty(deltas)

    # 희소성 보정: 동종 5개 중 0~1개만 유사 + 지급 제한/요건 강화가 있으면 +10
    payment_critical = {"PAYMENT_LIMITATION_EXPANSION", "PAYMENT_CONDITION_TIGHTENING", "EXCLUSION_EXPANSION", "PAYMENT_RESTRICTION"}
    if peer_coverage <= 1 and any(t in payment_critical for t in tags):
        score += 10

    lo, hi = score_clamp
    score = max(lo, min(hi, score))

    if score >= 60:
        sev = "CRITICAL"
    elif score >= 40:
        sev = "HIGH"
    elif score >= 20:
        sev = "MEDIUM"
    else:
        sev = "LOW"
    return tags, score, sev


def pick_recommendation(rule_hits: list[RuleHit]) -> tuple[str | None, str | None]:
    if not rule_hits:
        return None, None
    # tie-break: weight desc, axis PAYMENT 우선
    ranked = sorted(
        rule_hits,
        key=lambda h: (h.weight, 1 if h.axis == "PAYMENT" else 0),
        reverse=True,
    )
    top = ranked[0]
    return top.recommendation_type, top.recommendation_hint


def build_risk_finding(tags: list[str], evidence_new: str, peer_coverage: int | None = None, evidence_peer: str | None = None) -> str:
    tagset = set(tags)
    if "PAYMENT_CONDITION_TIGHTENING" in tagset:
        base = "신 약관은 보험금 지급을 위한 요건을 추가/강화하는 문구가 포함되어, 실제 지급 가능 범위를 축소하거나 분쟁 소지를 높일 수 있습니다."
    elif "PAYMENT_LIMITATION_EXPANSION" in tagset:
        base = "보험금 지급 한도/횟수/기간 관련 제한이 강화되어 소비자 체감 보장 범위가 축소될 우려가 있습니다."
    elif "PAYMENT_RESTRICTION" in tagset or "EXCLUSION_EXPANSION" in tagset:
        base = "보험금 지급 제외(면책/부지급) 범위가 확대될 소지가 있어, 적용 요건과 예외를 중심으로 재검토가 필요합니다."
    elif "DISCRETION" in tagset:
        base = "지급 판단에서 회사 재량으로 해석될 수 있는 표현이 포함되어, 분쟁 시 불리하게 작용할 소지가 있습니다."
    elif "AMBIGUITY" in tagset:
        base = "지급 판단과 관련된 표현이 추상적이어서 해석상 다툼이 발생할 가능성이 있습니다."
    else:
        base = "변경 조항에 대해 지급 판단/절차 관점의 추가 검토가 필요합니다."

    tail = f" 근거: “{evidence_new}”"
    if peer_coverage is not None and evidence_peer:
        tail += f" / 타사 비교(동종 {peer_coverage}/5): {evidence_peer}"
    return base + tail

