from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class FetchConfig:
    user_agent: str
    request_timeout_s: int = 30
    rate_limit_s: float = 1.0
    max_pages: int = 30


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


def extract_pdf_links(page_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        u = urljoin(page_url, href)
        if ".pdf" in u.lower():
            links.append(u)
    # 중복 제거
    out = []
    seen = set()
    for u in links:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def extract_same_domain_links(page_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        u = urljoin(page_url, href)
        if _is_same_domain(page_url, u):
            links.append(u)
    out = []
    seen = set()
    for u in links:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def discover_pdfs(
    *,
    seed_urls: list[str],
    cfg: FetchConfig,
) -> tuple[list[str], list[dict]]:
    """
    매우 보수적인 MVP:
    - seed url들을 GET
    - 페이지에서 pdf 링크 추출
    - 동일 도메인 링크를 max_pages까지 따라가며 추가 pdf를 찾음
    """
    s = requests.Session()
    s.headers.update({"User-Agent": cfg.user_agent})

    pdfs: list[str] = []
    logs: list[dict] = []
    seen_pages = set()
    queue: list[str] = list(seed_urls)

    while queue and len(seen_pages) < cfg.max_pages:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        try:
            r = s.get(url, timeout=cfg.request_timeout_s)
            logs.append({"type": "fetch_page", "url": url, "status": r.status_code})
            if r.status_code != 200:
                continue
            html = r.text
            found = extract_pdf_links(url, html)
            for p in found:
                if p not in pdfs:
                    pdfs.append(p)
            # 다음 탐색 링크(동일 도메인)
            for nxt in extract_same_domain_links(url, html):
                if nxt not in seen_pages and len(seen_pages) + len(queue) < cfg.max_pages:
                    queue.append(nxt)
        except Exception as e:
            logs.append({"type": "fetch_page_error", "url": url, "error": str(e)})
        time.sleep(cfg.rate_limit_s)

    return pdfs, logs


def download_pdfs(
    *,
    insurer_code: str,
    insurer_name: str,
    pdf_urls: list[str],
    cfg: FetchConfig,
    out_dir: str | Path = "peer_data/raw",
) -> Path:
    out_dir = Path(out_dir) / insurer_code
    out_dir.mkdir(parents=True, exist_ok=True)

    s = requests.Session()
    s.headers.update({"User-Agent": cfg.user_agent})

    manifest_path = out_dir / "manifest.jsonl"
    with manifest_path.open("a", encoding="utf-8") as mf:
        for url in pdf_urls:
            try:
                r = s.get(url, timeout=cfg.request_timeout_s)
                status = r.status_code
                if status != 200:
                    mf.write(json.dumps({"type": "download_skip", "url": url, "status": status}, ensure_ascii=False) + "\n")
                    time.sleep(cfg.rate_limit_s)
                    continue

                content_type = r.headers.get("content-type", "")
                data = r.content
                sha = _sha256_bytes(data)

                name = urlparse(url).path.split("/")[-1] or f"{insurer_code}.pdf"
                name = _safe_filename(name)
                if not name.lower().endswith(".pdf"):
                    name += ".pdf"
                file_path = out_dir / name

                # 같은 해시가 이미 있으면 저장 생략
                if file_path.exists():
                    mf.write(json.dumps({"type": "download_exists", "url": url, "path": str(file_path), "sha256": sha}, ensure_ascii=False) + "\n")
                else:
                    file_path.write_bytes(data)
                    mf.write(
                        json.dumps(
                            {
                                "type": "download_ok",
                                "insurer": insurer_name,
                                "insurer_code": insurer_code,
                                "url": url,
                                "path": str(file_path),
                                "content_type": content_type,
                                "bytes": len(data),
                                "sha256": sha,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except Exception as e:
                mf.write(json.dumps({"type": "download_error", "url": url, "error": str(e)}, ensure_ascii=False) + "\n")
            time.sleep(cfg.rate_limit_s)

    return manifest_path


def load_targets(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

