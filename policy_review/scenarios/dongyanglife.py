from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_LIST_URL = "https://pbano.myangel.co.kr/paging/WE_AC_WEPAAP020100L"


@dataclass(frozen=True)
class DongyangScenarioConfig:
    list_url: str
    product_contains: str
    product_pick: str  # substring to pick a row
    insurer: str
    insurer_code: str
    product_group: str
    out_dir: Path
    headless: bool = True
    user_agent: str = "yakkan-scenario/0.1 (+internal legal review)"


def _manifest_path(cfg: DongyangScenarioConfig) -> Path:
    p = cfg.out_dir / cfg.insurer_code / cfg.product_group / "manifest_scenario.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log(manifest: Path, obj: dict) -> None:
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run(cfg: DongyangScenarioConfig) -> dict[str, str]:
    """
    동양생명 판매상품 공시에서:
    - 상품명 검색
    - 결과 표에서 특정 상품 행 선택
    - 행 내 링크(요약서/사업방법서/보험약관) 중 사업방법서/보험약관(PDF) 다운로드

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
        page.set_default_timeout(180_000)

        _log(manifest, {"type": "goto", "url": cfg.list_url})
        page.goto(cfg.list_url, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)

        _log(manifest, {"type": "search", "keyword": cfg.product_contains})
        page.fill("#productSearchLbl", cfg.product_contains)
        page.locator("#productSearchLbl").press("Enter")
        page.wait_for_timeout(4000)

        rows = page.locator("table tbody tr")
        if rows.count() == 0:
            raise RuntimeError("검색 결과 표를 찾지 못했습니다.")

        _log(manifest, {"type": "pick_row", "text": cfg.product_pick})
        picked = None
        for i in range(min(rows.count(), 80)):
            t = rows.nth(i).inner_text() or ""
            if cfg.product_pick in t:
                picked = rows.nth(i)
                break
        if picked is None:
            sample = (rows.first.inner_text() or "")[:300]
            _log(manifest, {"type": "pick_row_failed", "sample_row0": sample})
            raise RuntimeError(f"상품 행을 찾지 못했습니다: {cfg.product_pick!r}")

        # 헤더 기준으로 링크 순서가 (요약서, 사업방법서, 보험약관)인 것을 확인했음
        links = picked.locator("a")
        if links.count() < 3:
            raise RuntimeError("다운로드 링크를 찾지 못했습니다(요약서/사업방법서/약관).")

        def download_link(link_index: int, kind: str, out_path: Path) -> None:
            _log(manifest, {"type": "click_download", "kind": kind, "link_index": link_index})
            with page.expect_download(timeout=120_000) as dl:
                links.nth(link_index).click()
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

        download_link(1, "METHODS", out_methods)
        download_link(2, "TERMS", out_terms)

        context.close()
        browser.close()

    return results


def build_product_pick_from_contains(product_contains: str) -> str:
    return product_contains.strip()

