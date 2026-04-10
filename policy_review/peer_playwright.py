from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Browser, Page, Playwright, sync_playwright


@dataclass(frozen=True)
class PWConfig:
    user_agent: str
    headless: bool = True
    timeout_ms: int = 60_000
    rate_limit_s: float = 1.0
    max_pages: int = 40
    max_clicks: int = 20


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _safe_filename(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", ".", " "):
            out.append(ch)
        else:
            out.append("_")
    s = "".join(out).strip().replace(" ", "_")
    return s[:180] if len(s) > 180 else s


def _is_same_domain(a: str, b: str) -> bool:
    pa = urlparse(a)
    pb = urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def _normalize_url(u: str) -> str:
    # fragment(#) 차이로 동일 페이지가 중복 방문되는 것 방지
    p = urlparse(u)
    return p._replace(fragment="").geturl()


def _should_enqueue(u: str) -> bool:
    lu = u.lower()
    if "login" in lu:
        return False
    if "mypage" in lu:
        return False
    # 공시/상품공시 영역만 우선(너무 넓은 탐색 방지)
    if any(x in lu for x in ["/disclosure", "disclosurenotice"]):
        return True
    return False


def _looks_like_pdf_url(u: str) -> bool:
    lu = u.lower()
    if ".pdf" in lu:
        return True
    # 종종 download endpoint가 pdf 확장자 없이 내려주는 경우가 있어, 힌트용으로만 사용
    return any(k in lu for k in ["download", "file", "attach"])


def _collect_links(page: Page, base_url: str) -> list[str]:
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    out: list[str] = []
    seen = set()
    for h in hrefs:
        if not h:
            continue
        u = urljoin(base_url, h)
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def discover_and_download(
    *,
    insurer: str,
    insurer_code: str,
    seed_urls: list[str],
    out_dir: str | Path = "peer_data/raw",
    cfg: PWConfig,
) -> Path:
    """
    Playwright 기반(동적 페이지 대응) PDF 수집기.
    - seed url 방문
    - 네트워크 응답에서 content-type: application/pdf 또는 url에 pdf 힌트가 있으면 저장
    - 페이지 내 링크를 따라 동일 도메인 탐색(상한 있음)
    - 일부 버튼(다운로드/약관) 자동 클릭 시도
    """
    out_dir = Path(out_dir) / insurer_code
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest_playwright.jsonl"

    visited = set()
    queue = [_normalize_url(u) for u in seed_urls]
    download_seq = 0

    def log(obj: dict):
        with manifest_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def save_pdf(url: str, body: bytes, suggested_name: str | None = None):
        sha = _sha256_bytes(body)
        name = suggested_name or (urlparse(url).path.split("/")[-1] or f"{insurer_code}.pdf")
        name = _safe_filename(name)
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        path = out_dir / name
        if path.exists():
            log({"type": "download_exists", "url": url, "path": str(path), "sha256": sha})
            return
        path.write_bytes(body)
        log(
            {
                "type": "download_ok",
                "insurer": insurer,
                "insurer_code": insurer_code,
                "url": url,
                "path": str(path),
                "bytes": len(body),
                "sha256": sha,
            }
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=cfg.headless)
        context = browser.new_context(user_agent=cfg.user_agent, accept_downloads=True)

        # response hook: PDF를 직접 받으면 저장
        def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                url = resp.url
                if "application/pdf" in ct.lower():
                    body = resp.body()
                    if body and body[:4] == b"%PDF":
                        save_pdf(url, body)
                elif _looks_like_pdf_url(url):
                    body = resp.body()
                    if body and body[:4] == b"%PDF":
                        save_pdf(url, body)
            except Exception as e:
                log({"type": "response_error", "error": str(e)})

        context.on("response", on_response)

        def on_download(download):
            nonlocal download_seq
            try:
                suggested = download.suggested_filename
                path = out_dir / _safe_filename(suggested or f"{insurer_code}_download_{download_seq}.pdf")
                if not path.name.lower().endswith(".pdf"):
                    path = path.with_name(path.name + ".pdf")
                download.save_as(path)
                data = path.read_bytes()
                sha = _sha256_bytes(data)
                log(
                    {
                        "type": "download_event_ok",
                        "insurer": insurer,
                        "insurer_code": insurer_code,
                        "url": download.url,
                        "path": str(path),
                        "bytes": len(data),
                        "sha256": sha,
                        "suggested_filename": suggested,
                    }
                )
                download_seq += 1
            except Exception as e:
                log({"type": "download_event_error", "error": str(e)})

        context.on("download", on_download)

        page = context.new_page()
        page.set_default_timeout(cfg.timeout_ms)

        while queue and len(visited) < cfg.max_pages:
            url = _normalize_url(queue.pop(0))
            if url in visited:
                continue
            visited.add(url)
            try:
                log({"type": "visit", "url": url})
                # networkidle은 광고/트래킹 때문에 무한 대기에 가까워질 수 있어 domcontentloaded 사용
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(800)

                # 링크 기반 pdf
                pdf_nav = 0
                for u in _collect_links(page, url):
                    u = _normalize_url(u)
                    if not _is_same_domain(url, u):
                        continue
                    if _looks_like_pdf_url(u) and pdf_nav < 3:
                        # 직접 네비게이션해서 response hook으로 저장되게 유도
                        try:
                            page.goto(u, wait_until="domcontentloaded", timeout=cfg.timeout_ms)
                            page.wait_for_timeout(300)
                            page.go_back(wait_until="domcontentloaded", timeout=cfg.timeout_ms)
                            pdf_nav += 1
                        except Exception:
                            pass
                    # 동일 도메인 탐색 큐
                    if u not in visited and len(visited) + len(queue) < cfg.max_pages and _should_enqueue(u):
                        queue.append(u)

                # 다운로드 버튼 클릭 힌트(보수적으로)
                clicks = 0
                selectors = [
                    "text=약관",
                    "text=사업방법서",
                    "text=다운로드",
                    "text=PDF",
                    "a:has-text(\"약관\")",
                    "a:has-text(\"사업방법서\")",
                    "a:has-text(\"다운로드\")",
                    "button:has-text(\"다운로드\")",
                ]
                for sel in selectors:
                    if clicks >= cfg.max_clicks:
                        break
                    try:
                        el = page.query_selector(sel)
                        if el:
                            el.click()
                            clicks += 1
                            time.sleep(0.6)
                    except Exception:
                        continue

            except Exception as e:
                log({"type": "visit_error", "url": url, "error": str(e)})
            time.sleep(cfg.rate_limit_s)

        context.close()
        browser.close()

    return manifest_path

