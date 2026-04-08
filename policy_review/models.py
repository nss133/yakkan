from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Clause:
    doc_id: str
    clause_id: str
    clause_path: str
    title: str
    text: str
    source_ref: str


@dataclass(frozen=True)
class Rule:
    id: str
    axis: str
    tag: str
    weight: int
    regex: list[str]
    window_keywords: list[str]
    recommendation_type: Optional[str] = None
    recommendation_hint: Optional[str] = None


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    axis: str
    tag: str
    weight: int
    evidence_sentence: str
    recommendation_type: Optional[str]
    recommendation_hint: Optional[str]


@dataclass(frozen=True)
class PeerMatch:
    peer_doc_id: str
    peer_insurer: str
    peer_clause_path: str
    peer_snippet: str
    sim_score: float


@dataclass(frozen=True)
class Quantity:
    raw: str
    value: float
    unit: str  # 일/개월/년/원/만원/억원/회/번/%/퍼센트


@dataclass(frozen=True)
class QuantityDelta:
    unit: str
    old_value: float
    new_value: float
    direction: str  # INCREASE/DECREASE/CHANGE
    label: str      # "청구기한", "대기기간", "지급한도" 등(룰 기반 힌트)

