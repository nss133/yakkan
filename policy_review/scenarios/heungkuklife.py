from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_LIST_URL = "https://www.heungkuklife.co.kr/front/public/saleProduct.do?searchFlgSale=Y"


@dataclass(frozen=True)
class HeungkukScenarioConfig:
    list_url: str
    product_contains: str
    product_pick: str  # substring to pick suggestion item (optional)
    insurer: str
    insurer_code: str
    product_group: str
    out_dir: Path
    headless: bool = True
    user_agent: str = "yakkan-scenario/0.1 (+internal legal review)"


def _manifest_path(cfg: HeungkukScenarioConfig) -> Path:
    p = cfg.out_dir / cfg.insurer_code / cfg.product_group / "manifest_scenario.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log(manifest: Path, obj: dict) -> None:
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _parse_suggestions(body: str) -> list[str]:
    """
    saleProductAjax.do 응답 포맷(예):
      (무)흥국생명 ...%,%%|%(무)흥국생명 ...%,%%||%null%||%
    """
    names: list[str] = []
    for part in (body or "").split("|"):
        if not part.startswith("%"):
            continue
        s = part.strip("%")
        s = s.replace("%,%%", "").replace("%,%", "").replace("%,", "").replace("%%", "").strip()
        if s and s != "null":
            names.append(s)
    return names


def run(cfg: HeungkukScenarioConfig) -> dict[str, str]:
    """
    흥국생명 판매상품 공시에서:
    - 검색어 입력
    - 자동완성(Ajax) 목록에서 상품명을 골라 hidden 필드에 설정
    - 기간별 테이블에서 최신 행(첫 행)의 약관/사업방법서 PDF 다운로드

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

        ajax = {"body": None}

        def on_resp(resp):
            if resp.url.endswith("/front/public/saleProductAjax.do"):
                try:
                    ajax["body"] = resp.text()
                except Exception:
                    pass

        page.on("response", on_resp)

        _log(manifest, {"type": "goto", "url": cfg.list_url})
        page.goto(cfg.list_url, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)

        _log(manifest, {"type": "search", "keyword": cfg.product_contains})
        page.fill("#searchText", cfg.product_contains)
        # 자동완성 Ajax 호출
        page.evaluate("() => doSearch('Y','','','','')")
        page.wait_for_timeout(8000)

        suggestions = _parse_suggestions(ajax["body"] or "")
        _log(manifest, {"type": "suggestions", "count": len(suggestions), "top": suggestions[:10]})
        if not suggestions:
            raise RuntimeError("자동완성 목록(saleProductAjax)에서 상품명을 찾지 못했습니다.")

        picked = None
        if cfg.product_pick:
            for s in suggestions:
                if cfg.product_pick in s:
                    picked = s
                    break
        if picked is None:
            picked = suggestions[0]

        _log(manifest, {"type": "pick_product", "text": picked})
        # hidden 필드에 설정 후 조회(이 함수는 searchCdPublicPrtType3.replace를 수행하므로 반드시 문자열 전달)
        page.evaluate("(v) => { document.querySelector('#searchCdPublicPrtType3').value = v; }", picked)
        page.evaluate("(v) => doSearch('Y','','','', v)", picked)
        page.wait_for_timeout(8000)

        rows = page.locator("#productVoTr tr")
        if rows.count() == 0:
            raise RuntimeError("기간별 테이블 행을 찾지 못했습니다.")

        row = rows.first

        def unblock_pointer_modal() -> None:
            # 일부 환경에서 로딩 모달이 계속 남아 클릭을 가로챔(다운로드 트리거 자체는 JS로 진행 가능)
            page.evaluate(
                """() => {
                  const el = document.querySelector('#nppfs-loading-modal');
                  if (el) el.remove();
                }"""
            )

        def download_td(td_index: int, kind: str, out_path: Path) -> None:
            _log(manifest, {"type": "click_download", "kind": kind, "td_index": td_index})
            unblock_pointer_modal()
            with page.expect_download(timeout=120_000) as dl:
                row.locator("td").nth(td_index).locator("a").first.click()
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

        # 컬럼: 0판매기간 1상품코드? 2약관 3사업방법서 4요약서
        download_td(2, "TERMS", out_terms)
        download_td(3, "METHODS", out_methods)

        context.close()
        browser.close()

    return results


def build_product_pick_from_contains(product_contains: str) -> str:
    return product_contains.strip()

