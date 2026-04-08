from __future__ import annotations

import math
import re
from collections import Counter


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w가-힣]+", re.UNICODE)


PAYMENT_KEYWORDS: dict[str, float] = {
    "보험금": 3.0,
    "지급": 2.5,
    "지급사유": 3.0,
    "지급요건": 3.0,
    "지급기준": 2.5,
    "보상": 2.0,
    "면책": 3.0,
    "감액": 2.5,
    "한도": 2.0,
    "대기기간": 2.0,
    "면책기간": 2.0,
    "청구": 1.8,
    "통지": 1.8,
    "제출서류": 1.5,
}


def normalize_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def tokenize(s: str) -> list[str]:
    s = normalize_text(s)
    if not s:
        return []
    # 형태소 분석 없이 MVP: 공백 토큰(2글자 이상)
    return [t for t in s.split(" ") if len(t) >= 2]


def jaccard_tokens(a: str, b: str) -> float:
    ta = set(tokenize(a))
    tb = set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _char_ngrams(s: str, n: int = 3) -> Counter[str]:
    s = normalize_text(s).replace(" ", "")
    if len(s) < n:
        return Counter()
    return Counter(s[i : i + n] for i in range(len(s) - n + 1))


def cosine_char_ngram(a: str, b: str, n: int = 3) -> float:
    ca = _char_ngrams(a, n=n)
    cb = _char_ngrams(b, n=n)
    if not ca or not cb:
        return 0.0
    inter = set(ca) & set(cb)
    dot = sum(ca[g] * cb[g] for g in inter)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(dot / (na * nb))


def keyword_weight_score(a: str, b: str, weights: dict[str, float] | None = None) -> float:
    """
    공통 키워드 가중치 합을 [0,1]로 정규화한 값.
    """
    weights = weights or PAYMENT_KEYWORDS
    common = 0.0
    total = sum(weights.values()) or 1.0
    for k, w in weights.items():
        if k in a and k in b:
            common += w
    return min(1.0, common / total)


_CLAUSE_NUM_RE = re.compile(r"(제\s*\d+\s*조)")
# 항/호는 '제2항' 형태 외에도 '2항', '②항' 같은 변형이 섞이는 경우가 있어 보강
_HANG_RE = re.compile(r"(제\s*\d+\s*항|\b\d+\s*항\b|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*항)")
_HO_RE = re.compile(r"(제\s*\d+\s*호|\b\d+\s*호\b|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*호)")

_CIRCLED_NUM_MAP = {
    "①": "1",
    "②": "2",
    "③": "3",
    "④": "4",
    "⑤": "5",
    "⑥": "6",
    "⑦": "7",
    "⑧": "8",
    "⑨": "9",
    "⑩": "10",
    "⑪": "11",
    "⑫": "12",
    "⑬": "13",
    "⑭": "14",
    "⑮": "15",
    "⑯": "16",
    "⑰": "17",
    "⑱": "18",
    "⑲": "19",
    "⑳": "20",
}


def extract_clause_number(clause_path: str, title: str = "", text: str = "") -> str | None:
    for s in (clause_path, title, text[:200]):
        m = _CLAUSE_NUM_RE.search(s)
        if m:
            return m.group(1).replace(" ", "")
    return None


def extract_clause_path_parts(clause_path: str, title: str = "", text: str = "") -> tuple[str | None, str | None, str | None]:
    """
    returns (조, 항, 호) like ("제10조","제2항","제1호")
    """
    s = f"{clause_path} {title} {text[:400]}"
    jo = None
    hang = None
    ho = None
    m = _CLAUSE_NUM_RE.search(s)
    if m:
        jo = m.group(1).replace(" ", "")
    m = _HANG_RE.search(s)
    if m:
        hang = m.group(1).replace(" ", "")
        for k, v in _CIRCLED_NUM_MAP.items():
            hang = hang.replace(k, v)
        # "2항" -> "제2항"로 정규화
        if hang and not hang.startswith("제") and hang.endswith("항"):
            hang = "제" + hang
    m = _HO_RE.search(s)
    if m:
        ho = m.group(1).replace(" ", "")
        for k, v in _CIRCLED_NUM_MAP.items():
            ho = ho.replace(k, v)
        if ho and not ho.startswith("제") and ho.endswith("호"):
            ho = "제" + ho
    return jo, hang, ho


def combined_similarity(
    *,
    clause_path_a: str,
    title_a: str,
    text_a: str,
    clause_path_b: str,
    title_b: str,
    text_b: str,
) -> float:
    """
    복합 유사도(0~1):
    - clause_path exact: 매우 강함
    - 조항번호(제n조) 일치: 강함
    - 제목 토큰 유사도 + 본문 문자 3-gram 코사인 + 지급 키워드 가중치
    """
    if clause_path_a and clause_path_a == clause_path_b:
        return 0.98

    num_a = extract_clause_number(clause_path_a, title_a, text_a)
    num_b = extract_clause_number(clause_path_b, title_b, text_b)
    clause_num_bonus = 0.18 if (num_a and num_b and num_a == num_b) else 0.0

    title_sim = jaccard_tokens(title_a, title_b)
    text_sim = cosine_char_ngram(text_a, text_b, n=3)
    kw_sim = keyword_weight_score(text_a, text_b)

    # 가중치: 본문 유사도 > 제목 유사도, 지급 키워드 보조
    base = (0.55 * text_sim) + (0.25 * title_sim) + (0.20 * kw_sim)
    score = min(1.0, base + clause_num_bonus)
    return float(score)

