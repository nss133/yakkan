from __future__ import annotations

import argparse
from pathlib import Path

from .peer_fetch import FetchConfig, discover_pdfs, download_pdfs, load_targets


def main():
    ap = argparse.ArgumentParser(description="타사 약관 PDF 수집기(MVP)")
    ap.add_argument("--targets", default="peers/targets.yaml", help="타깃 YAML 경로")
    ap.add_argument("--out-dir", default="peer_data/raw", help="다운로드 저장 폴더")
    ap.add_argument("--max-pages", type=int, default=30, help="도메인 내 탐색 페이지 상한")
    ap.add_argument("--rate-limit-s", type=float, default=1.0, help="요청 간 최소 대기(초)")
    ap.add_argument("--timeout-s", type=int, default=30, help="요청 타임아웃(초)")
    ap.add_argument("--only", default="", help="특정 보험사 code만 실행(쉼표 구분)")
    ap.add_argument(
        "--i-accept-site-tos",
        action="store_true",
        help="각 사이트 이용약관/robots 준수 책임을 이해하고 실행",
    )
    args = ap.parse_args()

    if not args.i_accept_site_tos:
        raise SystemExit("중단: --i-accept-site-tos 플래그가 필요합니다.")

    cfg_defaults = load_targets(args.targets).get("defaults", {})
    user_agent = cfg_defaults.get("user_agent", "yakkan-peer-fetcher/0.1")
    cfg = FetchConfig(
        user_agent=user_agent,
        request_timeout_s=args.timeout_s,
        rate_limit_s=args.rate_limit_s,
        max_pages=args.max_pages,
    )

    spec = load_targets(args.targets)
    targets = spec.get("targets", [])
    only = {x.strip() for x in args.only.split(",") if x.strip()} if args.only else None

    for t in targets:
        code = t.get("code")
        insurer = t.get("insurer")
        if only and code not in only:
            continue
        seed_urls = list(t.get("seed_urls", []))
        if not seed_urls:
            print(f"[skip] {insurer}({code}): seed_urls 없음")
            continue

        print(f"[discover] {insurer}({code}) seeds={len(seed_urls)}")
        pdfs, logs = discover_pdfs(seed_urls=seed_urls, cfg=cfg)
        print(f"[found] {insurer}({code}) pdf_links={len(pdfs)}")

        manifest_path = download_pdfs(
            insurer_code=code,
            insurer_name=insurer,
            pdf_urls=pdfs,
            cfg=cfg,
            out_dir=args.out_dir,
        )
        print(f"[done] {insurer}({code}) manifest={manifest_path}")


if __name__ == "__main__":
    main()

