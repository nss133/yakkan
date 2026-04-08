from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .diff import change_type, classify_focus_axis, diff_scope, pick_key_snippets
from .excel import write_workbook
from .models import Clause, PeerMatch
from .numbers import compare_quantities, deltas_to_summary
from .peer import compute_peer_coverage, top_k
from .rules import apply_rules, load_rules
from .scoring import build_risk_finding, compute_risk, pick_recommendation
from .similarity import combined_similarity, extract_clause_number, extract_clause_path_parts
from .text import split_sentences


def _clause_from_dict(d: dict[str, Any]) -> Clause:
    return Clause(
        doc_id=d["doc_id"],
        clause_id=d["clause_id"],
        clause_path=d["clause_path"],
        title=d.get("title", ""),
        text=d.get("text", ""),
        source_ref=d.get("source_ref", ""),
    )


def _peer_from_dict(d: dict[str, Any]) -> PeerMatch:
    return PeerMatch(
        peer_doc_id=d["peer_doc_id"],
        peer_insurer=d["peer_insurer"],
        peer_clause_path=d.get("peer_clause_path", ""),
        peer_snippet=d.get("peer_snippet", ""),
        sim_score=float(d.get("sim_score", 0.0)),
    )


def _snippet(text: str, max_len: int = 140) -> str:
    t = " ".join(text.split())
    return t[:max_len]


def _find_best_clause_by_path_or_similarity(
    new_clause: Clause,
    old_clauses: list[Clause],
) -> tuple[Clause | None, float]:
    """
    Improved alignment:
    1) clause_path exact match
    2) combined similarity (조항번호/제목/본문/키워드/3-gram)
    returns (old_clause, confidence 0~1)
    """
    for c in old_clauses:
        if c.clause_path == new_clause.clause_path:
            return c, 0.98

    # 후보 축소 1: 조/항/호 단위로 최대한 좁히기
    jo_new, hang_new, ho_new = extract_clause_path_parts(new_clause.clause_path, new_clause.title, new_clause.text)
    num_new = jo_new
    candidates = old_clauses
    if jo_new and hang_new:
        same_jo_hang = []
        for c in old_clauses:
            jo_c, hang_c, _ = extract_clause_path_parts(c.clause_path, c.title, c.text)
            if jo_c == jo_new and hang_c == hang_new:
                same_jo_hang.append(c)
        if same_jo_hang:
            candidates = same_jo_hang
    elif jo_new:
        same_jo = []
        for c in old_clauses:
            jo_c, _, _ = extract_clause_path_parts(c.clause_path, c.title, c.text)
            if jo_c == jo_new:
                same_jo.append(c)
        if same_jo:
            candidates = same_jo

    # 후보 축소 2: focus axis가 같으면 우선(후보가 너무 많을 때만)
    if len(candidates) > 30:
        axis_new = classify_focus_axis(new_clause.text)
        axis_same = [c for c in candidates if classify_focus_axis(c.text) == axis_new]
        if axis_same:
            candidates = axis_same

    # 최종: 후보군 내에서 복합 유사도 최고 선택
    best: tuple[Clause | None, float] = (None, 0.0)
    for c in candidates:
        sim = combined_similarity(
            clause_path_a=new_clause.clause_path,
            title_a=new_clause.title,
            text_a=new_clause.text,
            clause_path_b=c.clause_path,
            title_b=c.title,
            text_b=c.text,
        )
        if sim > best[1]:
            best = (c, sim)
    if best[1] >= 0.55:
        return best[0], float(best[1])
    return None, 0.6


def _peer_match_topk_for_clause(
    new_clause: Clause,
    peer_documents: list[dict[str, Any]],
    k: int = 3,
) -> list[PeerMatch]:
    """
    peer_documents: [{doc_id, insurer, clauses:[{...}]}]
    Improved matching: combined similarity (조항번호/제목/본문/키워드/3-gram)
    """
    matches: list[PeerMatch] = []
    jo_new, hang_new, _ = extract_clause_path_parts(new_clause.clause_path, new_clause.title, new_clause.text)
    num_new = jo_new
    axis_new = classify_focus_axis(new_clause.text)
    for pd in peer_documents:
        peer_doc_id = pd["doc_id"]
        insurer = pd.get("insurer", "")
        peer_clause_dicts = list(pd.get("clauses", []))

        # 후보 축소(보험사별): 조/항 단위 우선
        if jo_new and hang_new:
            same_jo_hang = []
            for cd in peer_clause_dicts:
                jo_c, hang_c, _ = extract_clause_path_parts(cd.get("clause_path", ""), cd.get("title", ""), cd.get("text", ""))
                if jo_c == jo_new and hang_c == hang_new:
                    same_jo_hang.append(cd)
            if same_jo_hang:
                peer_clause_dicts = same_jo_hang
        elif num_new:
            same_jo = []
            for cd in peer_clause_dicts:
                jo_c, _, _ = extract_clause_path_parts(cd.get("clause_path", ""), cd.get("title", ""), cd.get("text", ""))
                if jo_c == num_new:
                    same_jo.append(cd)
            if same_jo:
                peer_clause_dicts = same_jo

        # 2) 그래도 많으면 focus axis가 같은 후보 우선
        if len(peer_clause_dicts) > 50:
            axis_same = [
                cd
                for cd in peer_clause_dicts
                if classify_focus_axis(cd.get("text", "")) == axis_new
            ]
            if axis_same:
                peer_clause_dicts = axis_same

        for cd in peer_clause_dicts:
            peer_clause = _clause_from_dict({**cd, "doc_id": peer_doc_id})
            sim = combined_similarity(
                clause_path_a=new_clause.clause_path,
                title_a=new_clause.title,
                text_a=new_clause.text,
                clause_path_b=peer_clause.clause_path,
                title_b=peer_clause.title,
                text_b=peer_clause.text,
            )
            if sim <= 0:
                continue
            matches.append(
                PeerMatch(
                    peer_doc_id=peer_doc_id,
                    peer_insurer=insurer,
                    peer_clause_path=peer_clause.clause_path,
                    peer_snippet=_snippet(peer_clause.text),
                    sim_score=float(sim),
                )
            )
    return top_k(matches, k=k)


def run_document(
    rules_path: str | Path,
    input_path: str | Path,
    out_xlsx_path: str | Path,
    th_sim: float = 0.60,
):
    """
    문서 전체(조항 N개) 처리.
    입력 포맷:
      - new_document: {doc_id, clauses:[{clause_id, clause_path, title, source_ref, text}]}
      - old_document: {doc_id, clauses:[...]} (optional)
      - peer_documents: [{doc_id, insurer, clauses:[...]}] (optional)
      - peer_set_id: string (optional)
    """
    rules = load_rules(rules_path)
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))

    new_doc = data["new_document"]
    old_doc = data.get("old_document")
    peer_docs = data.get("peer_documents", [])

    new_clauses = [_clause_from_dict({**c, "doc_id": new_doc["doc_id"]}) for c in new_doc.get("clauses", [])]
    old_clauses = []
    if old_doc:
        old_clauses = [_clause_from_dict({**c, "doc_id": old_doc["doc_id"]}) for c in old_doc.get("clauses", [])]

    diff_rows: list[dict[str, Any]] = []
    peer_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []

    row_id = 1
    for nc in new_clauses:
        oc, align_conf = _find_best_clause_by_path_or_similarity(nc, old_clauses)
        peer_matches = _peer_match_topk_for_clause(nc, peer_docs, k=3) if peer_docs else []

        new_sentences = split_sentences(nc.text)
        rule_hits = apply_rules(new_sentences, rules)
        deltas = compare_quantities(oc.text if oc else None, nc.text)

        ct = change_type(oc.text if oc else None, nc.text)
        axis = classify_focus_axis(nc.text)
        scope = diff_scope(oc.text if oc else None, nc.text, deltas, rule_hits)
        key_old, key_new = pick_key_snippets(oc.text if oc else None, nc.text, rule_hits, deltas)

        delta_summary = deltas_to_summary(deltas)
        change_summary = f"{ct}"
        if delta_summary:
            change_summary += f" / 수치변화: {delta_summary}"
        if key_new:
            change_summary += f" / 핵심: {key_new[:200]}"

        top = peer_matches
        coverage, rarity = compute_peer_coverage(peer_matches, th_sim=th_sim) if peer_matches else (0, "RARE")
        if rarity == "RARE":
            uniq_reason = f"동종 5개 중 유사 규정 희소({coverage}/5)"
            bench_comment = f"동종 대비 희소({coverage}/5). 지급 제한/요건 강화 여부를 중심으로 재검토 권고."
        elif rarity == "MIXED":
            uniq_reason = f"동종 내 혼재({coverage}/5)"
            bench_comment = f"동종 내 혼재({coverage}/5). 표현 강도/예외 유무를 비교 권고."
        else:
            uniq_reason = f"동종에서 흔함({coverage}/5)"
            bench_comment = f"동종에서 흔함({coverage}/5). 표준 문구 범위 내인지 확인."

        tags, score, sev = compute_risk(rule_hits, deltas, peer_coverage=coverage)
        rec_type, rec_hint = pick_recommendation(rule_hits)

        if rule_hits:
            best = sorted(rule_hits, key=lambda h: h.weight, reverse=True)[0]
            evidence_new = best.evidence_sentence
        else:
            evidence_new = key_new or nc.text[:200]

        evidence_peer = ""
        if top:
            evidence_peer = "; ".join(
                [f"{m.peer_insurer}({m.sim_score:.2f}): {m.peer_snippet[:120]}" for m in top if m.peer_snippet]
            )

        finding = build_risk_finding(tags, evidence_new=evidence_new, peer_coverage=coverage, evidence_peer=evidence_peer or None)

        diff_rows.append(
            {
                "row_id": row_id,
                "doc_new_id": nc.doc_id,
                "doc_old_id": oc.doc_id if oc else "",
                "clause_path": nc.clause_path,
                "clause_number": "",
                "clause_title_new": nc.title,
                "clause_title_old": oc.title if oc else "",
                "change_type": ct,
                "change_summary": change_summary,
                "diff_scope": scope,
                "focus_axis": axis,
                "text_old": oc.text if oc else "",
                "text_new": nc.text,
                "key_snippet_old": key_old,
                "key_snippet_new": key_new,
                "source_old": oc.source_ref if oc else "",
                "source_new": nc.source_ref,
                "confidence_alignment": align_conf,
                "note_manual": "",
            }
        )

        peer_rows.append(
            {
                "row_id": row_id,
                "doc_new_id": nc.doc_id,
                "clause_path": nc.clause_path,
                "focus_axis": axis,
                "key_snippet_new": key_new,
                "peer_set_id": data.get("peer_set_id", "peer-set-1"),
                "top_peer_1_insurer": top[0].peer_insurer if len(top) >= 1 else "",
                "top_peer_1_doc_id": top[0].peer_doc_id if len(top) >= 1 else "",
                "top_peer_1_clause_path": top[0].peer_clause_path if len(top) >= 1 else "",
                "top_peer_1_snippet": top[0].peer_snippet if len(top) >= 1 else "",
                "sim_score_1": top[0].sim_score if len(top) >= 1 else "",
                "top_peer_2_insurer": top[1].peer_insurer if len(top) >= 2 else "",
                "top_peer_2_doc_id": top[1].peer_doc_id if len(top) >= 2 else "",
                "top_peer_2_clause_path": top[1].peer_clause_path if len(top) >= 2 else "",
                "top_peer_2_snippet": top[1].peer_snippet if len(top) >= 2 else "",
                "sim_score_2": top[1].sim_score if len(top) >= 2 else "",
                "top_peer_3_insurer": top[2].peer_insurer if len(top) >= 3 else "",
                "top_peer_3_doc_id": top[2].peer_doc_id if len(top) >= 3 else "",
                "top_peer_3_clause_path": top[2].peer_clause_path if len(top) >= 3 else "",
                "top_peer_3_snippet": top[2].peer_snippet if len(top) >= 3 else "",
                "sim_score_3": top[2].sim_score if len(top) >= 3 else "",
                "peer_coverage": coverage,
                "peer_rarity_flag": rarity,
                "uniqueness_reason": uniq_reason,
                "benchmark_comment": bench_comment,
            }
        )

        risk_rows.append(
            {
                "row_id": row_id,
                "doc_new_id": nc.doc_id,
                "clause_path": nc.clause_path,
                "risk_tags": ";".join(tags) if tags else "",
                "risk_score": score,
                "severity": sev,
                "risk_finding": finding,
                "evidence_new": evidence_new,
                "evidence_peer": evidence_peer,
                "recommendation_type": rec_type or "",
                "recommended_text": rec_hint or "",
                "fallback_option": "",
                "review_status": "AUTO_DRAFT",
                "owner": "",
                "memo": "",
            }
        )

        row_id += 1

    write_workbook(diff_rows=diff_rows, peer_rows=peer_rows, risk_rows=risk_rows, out_path=out_xlsx_path)


def run_single(
    rules_path: str | Path,
    input_path: str | Path,
    out_xlsx_path: str | Path,
    th_sim: float = 0.60,
    alignment_confidence: float = 0.85,
):
    # backward compatible: single clause schema
    rules = load_rules(rules_path)
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if "new_document" in data:
        return run_document(rules_path=rules_path, input_path=input_path, out_xlsx_path=out_xlsx_path, th_sim=th_sim)

    new_clause = _clause_from_dict(data["new_clause"])
    old_clause = _clause_from_dict(data["old_clause"]) if data.get("old_clause") else None
    peer_matches = [_peer_from_dict(x) for x in data.get("peer_matches", [])]

    new_sentences = split_sentences(new_clause.text)
    rule_hits = apply_rules(new_sentences, rules)
    deltas = compare_quantities(old_clause.text if old_clause else None, new_clause.text)

    ct = change_type(old_clause.text if old_clause else None, new_clause.text)
    axis = classify_focus_axis(new_clause.text)
    scope = diff_scope(old_clause.text if old_clause else None, new_clause.text, deltas, rule_hits)
    key_old, key_new = pick_key_snippets(old_clause.text if old_clause else None, new_clause.text, rule_hits, deltas)

    delta_summary = deltas_to_summary(deltas)
    change_summary = f"{ct}"
    if delta_summary:
        change_summary += f" / 수치변화: {delta_summary}"
    if key_new:
        change_summary += f" / 핵심: {key_new[:200]}"

    top = top_k(peer_matches, k=3)
    coverage, rarity = compute_peer_coverage(peer_matches, th_sim=th_sim)
    if rarity == "RARE":
        uniq_reason = f"동종 5개 중 유사 규정 희소({coverage}/5)"
        bench_comment = f"동종 대비 희소({coverage}/5). 지급 제한/요건 강화 여부를 중심으로 재검토 권고."
    elif rarity == "MIXED":
        uniq_reason = f"동종 내 혼재({coverage}/5)"
        bench_comment = f"동종 내 혼재({coverage}/5). 표현 강도/예외 유무를 비교 권고."
    else:
        uniq_reason = f"동종에서 흔함({coverage}/5)"
        bench_comment = f"동종에서 흔함({coverage}/5). 표준 문구 범위 내인지 확인."

    tags, score, sev = compute_risk(rule_hits, deltas, peer_coverage=coverage)
    rec_type, rec_hint = pick_recommendation(rule_hits)

    if rule_hits:
        best = sorted(rule_hits, key=lambda h: h.weight, reverse=True)[0]
        evidence_new = best.evidence_sentence
    else:
        evidence_new = key_new or new_clause.text[:200]

    evidence_peer = ""
    if top:
        evidence_peer = "; ".join(
            [f"{m.peer_insurer}({m.sim_score:.2f}): {m.peer_snippet[:120]}" for m in top if m.peer_snippet]
        )

    finding = build_risk_finding(tags, evidence_new=evidence_new, peer_coverage=coverage, evidence_peer=evidence_peer or None)

    diff_rows = [
        {
            "row_id": 1,
            "doc_new_id": new_clause.doc_id,
            "doc_old_id": old_clause.doc_id if old_clause else "",
            "clause_path": new_clause.clause_path,
            "clause_number": "",
            "clause_title_new": new_clause.title,
            "clause_title_old": old_clause.title if old_clause else "",
            "change_type": ct,
            "change_summary": change_summary,
            "diff_scope": scope,
            "focus_axis": axis,
            "text_old": old_clause.text if old_clause else "",
            "text_new": new_clause.text,
            "key_snippet_old": key_old,
            "key_snippet_new": key_new,
            "source_old": old_clause.source_ref if old_clause else "",
            "source_new": new_clause.source_ref,
            "confidence_alignment": alignment_confidence if old_clause else 0.6,
            "note_manual": "",
        }
    ]

    peer_rows = [
        {
            "row_id": 1,
            "doc_new_id": new_clause.doc_id,
            "clause_path": new_clause.clause_path,
            "focus_axis": axis,
            "key_snippet_new": key_new,
            "peer_set_id": data.get("peer_set_id", "peer-set-1"),
            "top_peer_1_insurer": top[0].peer_insurer if len(top) >= 1 else "",
            "top_peer_1_doc_id": top[0].peer_doc_id if len(top) >= 1 else "",
            "top_peer_1_clause_path": top[0].peer_clause_path if len(top) >= 1 else "",
            "top_peer_1_snippet": top[0].peer_snippet if len(top) >= 1 else "",
            "sim_score_1": top[0].sim_score if len(top) >= 1 else "",
            "top_peer_2_insurer": top[1].peer_insurer if len(top) >= 2 else "",
            "top_peer_2_doc_id": top[1].peer_doc_id if len(top) >= 2 else "",
            "top_peer_2_clause_path": top[1].peer_clause_path if len(top) >= 2 else "",
            "top_peer_2_snippet": top[1].peer_snippet if len(top) >= 2 else "",
            "sim_score_2": top[1].sim_score if len(top) >= 2 else "",
            "top_peer_3_insurer": top[2].peer_insurer if len(top) >= 3 else "",
            "top_peer_3_doc_id": top[2].peer_doc_id if len(top) >= 3 else "",
            "top_peer_3_clause_path": top[2].peer_clause_path if len(top) >= 3 else "",
            "top_peer_3_snippet": top[2].peer_snippet if len(top) >= 3 else "",
            "sim_score_3": top[2].sim_score if len(top) >= 3 else "",
            "peer_coverage": coverage,
            "peer_rarity_flag": rarity,
            "uniqueness_reason": uniq_reason,
            "benchmark_comment": bench_comment,
        }
    ]

    risk_rows = [
        {
            "row_id": 1,
            "doc_new_id": new_clause.doc_id,
            "clause_path": new_clause.clause_path,
            "risk_tags": ";".join(tags) if tags else "",
            "risk_score": score,
            "severity": sev,
            "risk_finding": finding,
            "evidence_new": evidence_new,
            "evidence_peer": evidence_peer,
            "recommendation_type": rec_type or "",
            "recommended_text": rec_hint or "",
            "fallback_option": "",
            "review_status": "AUTO_DRAFT",
            "owner": "",
            "memo": "",
        }
    ]

    write_workbook(diff_rows=diff_rows, peer_rows=peer_rows, risk_rows=risk_rows, out_path=out_xlsx_path)

