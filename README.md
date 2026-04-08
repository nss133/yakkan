# 보험 약관 검토 엑셀 생성기 (MVP)

외부 LLM 없이, 개정 약관(신)·직전 약관(구)·동종 타사 5개 비교를 바탕으로
`DIFF_TABLE`, `PEER_BENCHMARK`, `RISK_COMMENTS` 시트를 갖는 엑셀을 생성합니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행(샘플)

```bash
python -m policy_review.cli \
  --rules rules/payment_rules.yaml \
  --input examples/input.json \
  --out out/PolicyReview.xlsx
```

## 입력 포맷 (examples/input.json)

- `new_clause`: 신 조항
- `old_clause`: 구 조항(없으면 생략 가능)
- `peer_matches`: 타사 유사 조항 Top-k(없으면 빈 배열)

