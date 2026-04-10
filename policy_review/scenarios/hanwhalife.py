from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


DEFAULT_LIST_URL = (
    "https://www.hanwhalife.com/main/disclosure/goods/disclosurenotice/"
    "DF_GDDN000_P10000.do?MENU_ID1=DF_GDGL000&MENU_ID2=DF_GDGL000_P20000"
)


@dataclass(frozen=True)
class HanwhaScenarioConfig:
    list_url: str
    product_contains: str
    product_pick: str  # exact product text substring to click in the left-side list
    insurer: str
    insurer_code: str
    product_group: str
    out_dir: Path
    headless: bool = True
    user_agent: str = "yakkan-scenario/0.1 (+internal legal review)"


def _safe_filename(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", ".", " "):
            out.append(ch)
        else:
            out.append("_")
    s = "".join(out).strip().replace(" ", "_")
    return s[:180] if len(s) > 180 else s


def _manifest_path(cfg: HanwhaScenarioConfig) -> Path:
    p = cfg.out_dir / cfg.insurer_code / cfg.product_group / "manifest_scenario.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log(manifest: Path, obj: dict) -> None:
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run(cfg: HanwhaScenarioConfig) -> dict[str, str]:
    """
    한화생명 상품공시실(상품목록)에서:
    - 상품명 검색
    - 결과에서 특정 상품 선택
    - 최신 판매기간(첫 행)의 약관/사업방법서 PDF 다운로드

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
        page.wait_for_timeout(800)

        page.fill("#schText", cfg.product_contains)
        _log(manifest, {"type": "search", "keyword": cfg.product_contains})
        page.get_by_text("검색하기", exact=False).first.click()
        page.wait_for_timeout(1200)

        _log(manifest, {"type": "pick_product", "text": cfg.product_pick})
        page.locator("a", has_text=cfg.product_pick).first.click()
        page.wait_for_timeout(1200)

        # 최신 판매기간 행의 약관/사업방법서 버튼(ck-fileDownload, data-file에 키워드 포함)
        row = page.locator("#LIST_GRID3 tbody tr").first

        def download_col(kind: str, out_path: Path) -> None:
            sel = "button.ck-fileDownload"
            if kind == "TERMS":
                btn = row.locator(f"{sel}[data-file*='약관']").first
            elif kind == "METHODS":
                btn = row.locator(f"{sel}[data-file*='사업방법서']").first
            else:
                raise ValueError(kind)

            data_file = btn.get_attribute("data-file") or ""
            _log(manifest, {"type": "click_download", "kind": kind, "data_file": data_file})

            with page.expect_download() as dl_info:
                btn.click()
            download = dl_info.value
            download.save_as(out_path)
            _log(
                manifest,
                {
                    "type": "download_saved",
                    "kind": kind,
                    "path": str(out_path),
                    "suggested_filename": download.suggested_filename,
                    "bytes": out_path.stat().st_size if out_path.exists() else None,
                },
            )
            results[kind] = str(out_path)

        download_col("METHODS", out_methods)
        download_col("TERMS", out_terms)

        context.close()
        browser.close()

    return results


def build_product_pick_from_contains(product_contains: str) -> str:
    """
    사용자가 --product-contains만 넣는 경우를 돕기 위한 휴리스틱(기본: contains 그대로).
    필요하면 여기서 매핑 테이블을 추가.
    """
    return product_contains.strip()
