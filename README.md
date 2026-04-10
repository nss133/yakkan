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

## 타사 약관 PDF 수집(동적 페이지 대응: Playwright)

JS로 렌더링되거나 다운로드 버튼 클릭이 필요한 사이트는 Playwright 수집기를 사용합니다.

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium

python -m policy_review.peer_playwright_cli \
  --targets peers/targets.yaml \
  --only samsunglife \
  --headful \
  --i-accept-site-tos
```

### 중요(자동 수집의 현실적 한계)

- 생명보험협회 공시실(`http://pub.insure.or.kr`)은 `robots.txt`가 전체 경로를 차단(`Disallow: /`)하는 형태로 보이므로, **자동 크롤링으로 전체를 훑는 방식은 권장되지 않습니다.**
- 각 보험사 공시실은 화면/검색/세션 구조가 달라 **범용 크롤러 1개로 “누락 없이”를 보장하기 어렵습니다.**
  - 실전에서는 보통 **보험사별 시나리오(Playwright 스크립트)** 또는 **상품 상세 페이지 seed URL**을 주는 방식이 가장 안정적입니다.

## 보험사별 시나리오(예: 한화생명)

상품목록에서 검색 → 상품 선택 → 최신 판매기간 행의 **약관/사업방법서 PDF**를 내려받습니다.

```bash
python -m playwright install chromium

python -m policy_review.scenario_cli hanwhalife \
  --insurer "한화생명" \
  --insurer-code hanwhalife \
  --product-group whole_life \
  --product-contains "검색어" \
  --i-accept-site-tos
```

아래 시나리오도 동일한 인터페이스로 동작합니다.

- `samsunglife`: 삼성생명 판매상품 목록 → 팝업(iframe) PDF 캡처
- `kyobo`: 교보생명 전체상품조회 → 기간별 다운로드(모달) PDF
- `dongyanglife`: 동양생명 판매상품 → `MasFiledownload` 기반 PDF 다운로드
- `heungkuklife`: 흥국생명 판매상품 → 자동완성 선택 후 PDF 다운로드
- `shinhanlife`: 신한라이프 판매중 상품공시 → `bizxpress` 경로 PDF(GET) 저장

다운로드 결과는 기본적으로 아래 구조로 저장됩니다.

- `peer_data/raw_auto/<insurer_code>/<product_group>/TERMS/terms.pdf`
- `peer_data/raw_auto/<insurer_code>/<product_group>/METHODS/methods.pdf`

## 타사 약관 PDF → 조항 인덱스 생성

다운로드한 PDF 폴더를 상품군별로 인덱싱해 `peer_data/index/.../documents.jsonl`을 생성합니다.

```bash
python -m policy_review.peer_index_cli \
  --insurer "삼성생명" \
  --insurer-code samsunglife \
  --product-group whole_life \
  --doc-type TERMS \
  --pdf-dir peer_data/raw/samsunglife
```

사업방법서도 동일하게 인덱싱합니다.

```bash
python -m policy_review.peer_index_cli \
  --insurer "삼성생명" \
  --insurer-code samsunglife \
  --product-group whole_life \
  --doc-type METHODS \
  --pdf-dir "/path/to/manual-downloads/methods"
```

## 입력 포맷 (examples/input.json)

- `new_clause`: 신 조항
- `old_clause`: 구 조항(없으면 생략 가능)
- `peer_matches`: 타사 유사 조항 Top-k(없으면 빈 배열)

