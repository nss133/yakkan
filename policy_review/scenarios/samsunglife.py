from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

DEFAULT_LIST_URL = "https://www.samsunglife.com/individual/products/disclosure/sales/PDO-PRPRI010110M"


@dataclass(frozen=True)
class SamsungScenarioConfig:
    list_url: str
    product_contains: str
    product_pick: str  # substring to pick a row
    insurer: str
    insurer_code: str
    product_group: str
    out_dir: Path
    headless: bool = True
    user_agent: str = "yakkan-scenario/0.1 (+internal legal review)"


def _manifest_path(cfg: SamsungScenarioConfig) -> Path:
    p = cfg.out_dir / cfg.insurer_code / cfg.product_group / "manifest_scenario.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log(manifest: Path, obj: dict) -> None:
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _capture_first_pdf_bytes(page: Page, timeout_ms: int = 90_000) -> bytes | None:
    pdf: list[bytes] = []

    def on_response(resp):
        if pdf:
            return
        try:
            url = resp.url or ""
            ct = (resp.headers or {}).get("content-type", "")
            # 삼성은 iframe(XView.do)로 문서 뷰어를 열고, 약관(301)은 content-type이 pdf가 아닐 수 있음.
            # 그래서 URL 힌트(XView/docID) 기반으로만 본문을 읽고, magic bytes로 PDF를 판정한다.
            url_hint = ("XView.do" in url) or ("docID=" in url) or ("contenttype" in url.lower())
            if ("pdf" not in ct.lower()) and (not url_hint):
                return
            b = resp.body()
            if len(b) >= 4 and b[:4] == b"%PDF" and len(b) > 1024:
                pdf.append(b)
        except Exception:
            return

    page.on("response", on_response)
    t0 = time.time()
    while (time.time() - t0) * 1000 < timeout_ms:
        if pdf:
            return pdf[0]
        page.wait_for_timeout(200)
    return None


def run(cfg: SamsungScenarioConfig) -> dict[str, str]:
    """
    삼성생명 상품공시(판매상품 목록)에서:
    - 상품명 검색
    - 결과 표에서 특정 상품 행 선택
    - 사업방법서/약관 클릭 시 열리는 팝업(iframe)에서 PDF 응답을 캡처하여 저장

    반환: {"TERMS": path, "METHODS": path}
    """
    manifest = _manifest_path(cfg)
    if manifest.exists():
        manifest.unlink()

    out_terms = cfg.out_dir / cfg.insurer_code / cfg.product_group / "TERMS" / "terms.pdf"
    out_methods = cfg.out_dir / cfg.insurer_code / cfg.product_group / "METHODS" / "methods.pdf"
    out_terms.parent.mkdir(parents=True, exist_ok=True)
    out_methods.parent.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.headless)
        context = browser.new_context(user_agent=cfg.user_agent, accept_downloads=False)
        page = context.new_page()
        page.set_default_timeout(180_000)

        _log(manifest, {"type": "goto", "url": cfg.list_url})
        # SPA 특성상 networkidle이 장시간 끝나지 않는 경우가 있어 domcontentloaded로 진입한다.
        page.goto(cfg.list_url, wait_until="domcontentloaded")
        page.wait_for_selector("#keywordSearch")
        page.wait_for_selector("table tbody tr")
        page.wait_for_timeout(1500)

        _log(manifest, {"type": "search", "keyword": cfg.product_contains})
        page.fill("#keywordSearch", cfg.product_contains)
        page.locator("#keywordSearch").press("Enter")
        page.wait_for_timeout(800)
        # 엔터만으로 갱신이 안 되는 경우 버튼도 함께 시도
        if page.locator(".btn-search").count():
            page.locator(".btn-search").first.click()
        try:
            page.wait_for_function(
                """(kw) => document.body && document.body.innerText && document.body.innerText.includes(kw)""",
                cfg.product_contains,
                timeout=15_000,
            )
        except Exception:
            pass
        page.wait_for_timeout(3000)

        # 표에서 상품명으로 행 선택(행 텍스트 스캔; has_text 매칭이 불안정한 케이스 대응)
        _log(manifest, {"type": "pick_row", "text": cfg.product_pick})
        rows = page.locator("table tbody tr")
        if rows.count() == 0:
            raise RuntimeError("검색 결과 표를 찾지 못했습니다.")
        picked = None
        for i in range(min(rows.count(), 50)):
            t = rows.nth(i).inner_text() or ""
            if cfg.product_pick in t:
                picked = rows.nth(i)
                break
        if picked is None:
            sample = (rows.first.inner_text() or "")[:300]
            _log(manifest, {"type": "pick_row_failed", "sample_row0": sample})
            raise RuntimeError(f"상품 행을 찾지 못했습니다: {cfg.product_pick!r}")
        row = picked

        def download_from_popup(td_index: int, kind: str, out_path: Path) -> None:
            with context.expect_page() as np:
                row.locator("td").nth(td_index).locator("a").first.click()
            popup = np.value
            popup.wait_for_load_state("domcontentloaded")
            popup.wait_for_timeout(2000)

            b = _capture_first_pdf_bytes(popup, timeout_ms=120_000)
            if not b:
                _log(manifest, {"type": "pdf_capture_failed", "kind": kind, "popup_url": popup.url})
                popup.close()
                raise RuntimeError(f"{kind} PDF를 캡처하지 못했습니다.")

            out_path.write_bytes(b)
            _log(
                manifest,
                {
                    "type": "download_saved",
                    "kind": kind,
                    "path": str(out_path),
                    "bytes": out_path.stat().st_size if out_path.exists() else None,
                    "popup_url": popup.url,
                },
            )
            results[kind] = str(out_path)
            popup.close()

        # 삼성 표 컬럼: 0번호 1분류 2상품명 3판매기간 4요약서 5방법서 6약관
        download_from_popup(5, "METHODS", out_methods)
        download_from_popup(6, "TERMS", out_terms)

        context.close()
        browser.close()

    return results


def build_product_pick_from_contains(product_contains: str) -> str:
    return product_contains.strip()

