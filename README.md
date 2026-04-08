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

## 타사 약관 PDF 수집(초기 단계)

주의: 각 사이트의 이용약관/robots.txt를 준수해야 합니다.

```bash
python -m policy_review.peer_cli --targets peers/targets.yaml --i-accept-site-tos
```

## 타사 약관 PDF → 조항 인덱스 생성

다운로드한 PDF 폴더를 상품군별로 인덱싱해 `peer_data/index/.../documents.jsonl`을 생성합니다.

```bash
python -m policy_review.peer_index_cli \
  --insurer "삼성생명" \
  --insurer-code samsunglife \
  --product-group whole_life \
  --pdf-dir peer_data/raw/samsunglife
```

## 입력 포맷 (examples/input.json)

- `new_clause`: 신 조항
- `old_clause`: 구 조항(없으면 생략 가능)
- `peer_matches`: 타사 유사 조항 Top-k(없으면 빈 배열)

