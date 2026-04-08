from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .models import Rule, RuleHit


def load_rules(path: str | Path) -> list[Rule]:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    rules_raw = data.get("rules", [])
    rules: list[Rule] = []
    for r in rules_raw:
        rules.append(
            Rule(
                id=str(r["id"]),
                axis=str(r.get("axis", "OTHER")),
                tag=str(r["tag"]),
                weight=int(r.get("weight", 0)),
                regex=[str(x) for x in r.get("regex", [])],
                window_keywords=[str(x) for x in r.get("window_keywords", [])],
                recommendation_type=r.get("recommendation_type"),
                recommendation_hint=r.get("recommendation_hint"),
            )
        )
    return rules


def _window_ok(sentence: str, window_keywords: list[str]) -> bool:
    if not window_keywords:
        return True
    return any(k in sentence for k in window_keywords)


def apply_rules(sentences: list[str], rules: list[Rule]) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for s in sentences:
        for r in rules:
            if not _window_ok(s, r.window_keywords):
                continue
            for pat in r.regex:
                if re.search(pat, s):
                    hits.append(
                        RuleHit(
                            rule_id=r.id,
                            axis=r.axis,
                            tag=r.tag,
                            weight=r.weight,
                            evidence_sentence=s,
                            recommendation_type=r.recommendation_type,
                            recommendation_hint=r.recommendation_hint,
                        )
                    )
                    break
    return hits


def to_debug_dict(hits: list[RuleHit]) -> list[dict[str, Any]]:
    return [asdict(h) for h in hits]

