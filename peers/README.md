# 타사 약관 데이터 운영 방식(MVP)

상품군이 케이스별로 달라지므로, 타사 약관은 아래 구조로 보관하는 것을 전제로 합니다.

## 1) 원문 PDF 보관

`peer_data/raw/<insurer_code>/` 아래에 PDF를 저장합니다.

## 2) 인덱스(조항 텍스트) 생성

원문 PDF → 텍스트 추출 → (간단) 조항 분리(제n조 단위) 후,
`peer_data/index/<insurer_code>/<product_group>/documents.jsonl`로 저장합니다.

`product_group` 예시:
- `whole_life` (종신)
- `cancer` (암)
- `dementia` (치매/간병)

실손은 이번 범위에서 제외.

