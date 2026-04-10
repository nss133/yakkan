from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_LIST_URL = "https://www.kyobo.com/dgt/web/product-official/all-product/search"


@dataclass(frozen=True)
class KyoboScenarioConfig:
    list_url: str
    product_contains: str
    product_pick: str  # substring to pick a row
    insurer: str
    insurer_code: str
    product_group: str
    out_dir: Path
    headless: bool = True
    user_agent: str = "yakkan-scenario/0.1 (+internal legal review)"


def _manifest_path(cfg: KyoboScenarioConfig) -> Path:
    p = cfg.out_dir / cfg.insurer_code / cfg.product_group / "manifest_scenario.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log(manifest: Path, obj: dict) -> None:
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run(cfg: KyoboScenarioConfig) -> dict[str, str]:
    """
    교보생명 전체상품조회에서:
    - 키워드/상품명 검색
    - 결과 표에서 특정 상품 행 선택(기간별 다운로드 '확인')
    - 모달 내 최신 판매기간(첫 행)의 약관/사업방법서 다운로드(PW download 이벤트)

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
        context = browser.new_context(user_agent=cfg.user_agent, accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(120_000)

        _log(manifest, {"type": "goto", "url": cfg.list_url})
        page.goto(cfg.list_url, wait_until="networkidle")
        page.wait_for_timeout(1500)

        _log(manifest, {"type": "search", "keyword": cfg.product_contains})
        page.fill("#input-01", cfg.product_contains)
        page.locator("#searchBtn").click()
        page.wait_for_timeout(2500)

        _log(manifest, {"type": "pick_row", "text": cfg.product_pick})
        row = page.locator("table tbody tr").filter(has_text=cfg.product_pick).first
        if row.count() == 0:
            raise RuntimeError(f"상품 행을 찾지 못했습니다: {cfg.product_pick!r}")

        # 기간별 다운로드 모달 열기
        row.locator("button", has_text="확인").first.click()
        page.wait_for_timeout(1500)

        # 모달 내부의 판매기간 테이블(판매기간/약관/사업방법서)에서 첫 행 선택
        tbl = page.locator("table:has(th:has-text('판매기간')):has(th:has-text('약관'))").first
        if tbl.count() == 0:
            raise RuntimeError("기간별 다운로드 테이블을 찾지 못했습니다.")
        period_row = tbl.locator("tbody tr").first

        def download_td(td_index: int, kind: str, out_path: Path) -> None:
            _log(manifest, {"type": "click_download", "kind": kind})
            with page.expect_download(timeout=120_000) as dl:
                period_row.locator("td").nth(td_index).locator("a").first.click()
            d = dl.value
            d.save_as(out_path)
            _log(
                manifest,
                {
                    "type": "download_saved",
                    "kind": kind,
                    "path": str(out_path),
                    "suggested_filename": d.suggested_filename,
                    "bytes": out_path.stat().st_size if out_path.exists() else None,
                },
            )
            results[kind] = str(out_path)

        # 컬럼: 0판매기간 1약관 2사업방법서
        download_td(1, "TERMS", out_terms)
        download_td(2, "METHODS", out_methods)

        context.close()
        browser.close()

    return results


def build_product_pick_from_contains(product_contains: str) -> str:
    return product_contains.strip()

