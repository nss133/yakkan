from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

DEFAULT_LIST_URL = "https://www.shinhanlife.co.kr/hp/cdhi0030.do"


@dataclass(frozen=True)
class ShinhanScenarioConfig:
    list_url: str
    product_contains: str
    product_pick: str  # substring to pick a product row inside #GoodsList
    insurer: str
    insurer_code: str
    product_group: str
    out_dir: Path
    headless: bool = True
    user_agent: str = "yakkan-scenario/0.1 (+internal legal review)"


def _manifest_path(cfg: ShinhanScenarioConfig) -> Path:
    p = cfg.out_dir / cfg.insurer_code / cfg.product_group / "manifest_scenario.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log(manifest: Path, obj: dict) -> None:
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _encode_path(rel: str) -> str:
    if not rel.startswith("/"):
        rel = "/" + rel
    parts = rel.split("/")
    return "/" + "/".join(quote(p, safe="") for p in parts if p != "")


def _resolve_bizxpress_url(ws_id: str, repo_path: str, origin: str) -> str:
    """
    dp.Utils.getFileObject(wsId, path) 와 동일한 경로 치환:
      /repo/<wsId>/... -> /<CONTEXT_PATH>bizxpress/...
    (페이지에서 CONTEXT_PATH는 보통 '/')
    """
    path = repo_path
    needle = f"/repo/{ws_id}"
    if needle in path:
        path = path.replace(needle, "/bizxpress")
    return origin + _encode_path(path)


def run(cfg: ShinhanScenarioConfig) -> dict[str, str]:
    """
    신한라이프 판매중 상품공시(cdhi0030)에서:
    - 상품명 검색
    - #GoodsList 영역에서 상품 행 선택
    - 버튼 data-url을 bizxpress 경로로 치환한 뒤, 세션 쿠키를 포함해 PDF(GET)로 저장

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
        context = browser.new_context(user_agent=cfg.user_agent)
        page = context.new_page()
        page.set_default_timeout(180_000)

        _log(manifest, {"type": "goto", "url": cfg.list_url})
        page.goto(cfg.list_url, wait_until="networkidle")
        page.wait_for_timeout(2500)

        _log(manifest, {"type": "search", "keyword": cfg.product_contains})
        page.fill("#meta05", cfg.product_contains)
        page.locator("#btnSearch").click()
        page.wait_for_timeout(5000)

        # NOTE: 페이지에서 `#GoodsList` 자체가 <tbody>로 잡히는 경우가 있어 `tbody tr` 이중 선택은 0건이 될 수 있음
        rows = page.locator("#GoodsList > tr")
        if rows.count() == 0:
            raise RuntimeError("검색 결과(#GoodsList > tr)를 찾지 못했습니다.")

        _log(manifest, {"type": "pick_row", "text": cfg.product_pick})
        picked = None
        for i in range(min(rows.count(), 80)):
            t = rows.nth(i).inner_text() or ""
            if cfg.product_pick in t:
                picked = rows.nth(i)
                break
        if picked is None:
            sample = (rows.first.inner_text() or "")[:400]
            _log(manifest, {"type": "pick_row_failed", "sample_row0": sample})
            raise RuntimeError(f"상품 행을 찾지 못했습니다: {cfg.product_pick!r}")

        # 버튼 인덱스: cdhi0030.js 기준 _1 요약서, _2 방법서, _3 약관
        methods_btn = picked.locator('button[id$="_2"]')
        terms_btn = picked.locator('button[id$="_3"]')
        if methods_btn.count() == 0 or terms_btn.count() == 0:
            raise RuntimeError("방법서/약관 버튼을 찾지 못했습니다.")

        ws_m = methods_btn.first.get_attribute("data-ws-id") or ""
        path_m = methods_btn.first.get_attribute("data-url") or ""
        ws_t = terms_btn.first.get_attribute("data-ws-id") or ""
        path_t = terms_btn.first.get_attribute("data-url") or ""
        origin = page.evaluate("() => location.origin")

        url_m = _resolve_bizxpress_url(ws_m, path_m, origin)
        url_t = _resolve_bizxpress_url(ws_t, path_t, origin)
        _log(manifest, {"type": "http_get", "kind": "METHODS", "url": url_m})
        _log(manifest, {"type": "http_get", "kind": "TERMS", "url": url_t})

        def save_pdf(kind: str, url: str, out_path: Path) -> None:
            resp = page.request.get(url)
            if not resp.ok:
                raise RuntimeError(f"{kind} PDF 요청 실패: HTTP {resp.status} url={url}")
            body = resp.body()
            if len(body) < 4 or body[:4] != b"%PDF":
                raise RuntimeError(f"{kind} 응답이 PDF가 아닙니다(bytes={len(body)})")
            out_path.write_bytes(body)
            _log(
                manifest,
                {"type": "download_saved", "kind": kind, "path": str(out_path), "bytes": len(body)},
            )
            results[kind] = str(out_path)

        save_pdf("METHODS", url_m, out_methods)
        save_pdf("TERMS", url_t, out_terms)

        context.close()
        browser.close()

    return results


def build_product_pick_from_contains(product_contains: str) -> str:
    return product_contains.strip()
