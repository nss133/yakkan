from __future__ import annotations

from collections import defaultdict

from .models import PeerMatch


def top_k(peer_matches: list[PeerMatch], k: int = 3) -> list[PeerMatch]:
    return sorted(peer_matches, key=lambda x: x.sim_score, reverse=True)[:k]


def compute_peer_coverage(peer_matches: list[PeerMatch], th_sim: float = 0.72) -> tuple[int, str]:
    """
    coverage: 유사 조항이 발견된 보험사 수(0~5)
    rarity_flag: COMMON/MIXED/RARE
    """
    insurers = {m.peer_insurer for m in peer_matches if m.sim_score >= th_sim}
    coverage = len(insurers)
    if coverage >= 4:
        flag = "COMMON"
    elif coverage >= 2:
        flag = "MIXED"
    else:
        flag = "RARE"
    return coverage, flag

