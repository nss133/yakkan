from __future__ import annotations

import argparse
from pathlib import Path

from .scenarios.hanwhalife import DEFAULT_LIST_URL, HanwhaScenarioConfig, build_product_pick_from_contains, run
from .scenarios.kyobo import (
    DEFAULT_LIST_URL as KYOBO_LIST_URL,
    KyoboScenarioConfig,
    build_product_pick_from_contains as build_kyobo_pick,
    run as run_kyobo,
)
from .scenarios.dongyanglife import (
    DEFAULT_LIST_URL as DONGYANG_LIST_URL,
    DongyangScenarioConfig,
    build_product_pick_from_contains as build_dongyang_pick,
    run as run_dongyang,
)
from .scenarios.heungkuklife import (
    DEFAULT_LIST_URL as HEUNGKUK_LIST_URL,
    HeungkukScenarioConfig,
    build_product_pick_from_contains as build_heungkuk_pick,
    run as run_heungkuk,
)
from .scenarios.shinhanlife import (
    DEFAULT_LIST_URL as SHINHAN_LIST_URL,
    ShinhanScenarioConfig,
    build_product_pick_from_contains as build_shinhan_pick,
    run as run_shinhan,
)
from .scenarios.samsunglife import (
    DEFAULT_LIST_URL as SAMSUNG_LIST_URL,
    SamsungScenarioConfig,
    build_product_pick_from_contains as build_samsung_pick,
    run as run_samsung,
)


def _add_common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--insurer", required=True)
    ap.add_argument("--insurer-code", required=True)
    ap.add_argument("--product-group", required=True, help="whole_life / cancer / dementia 등")
    ap.add_argument("--out-dir", default="peer_data/raw_auto", help="다운로드 저장 루트")
    ap.add_argument("--headful", action="store_true", help="브라우저 표시")
    ap.add_argument(
        "--i-accept-site-tos",
        action="store_true",
        help="해당 사이트 이용약관/robots 준수 책임을 이해하고 실행",
    )


def main():
    ap = argparse.ArgumentParser(description="보험사 공시실 시나리오 다운로더(자동)")
    subs = ap.add_subparsers(dest="scenario", required=True)

    p_ss = subs.add_parser("samsunglife", help="삼성생명 판매상품 목록 → 팝업(iframe) PDF 캡처")
    _add_common(p_ss)
    p_ss.add_argument("--list-url", default=SAMSUNG_LIST_URL, help="삼성생명 상품목록 URL")
    p_ss.add_argument("--product-contains", required=True, help="상품명 검색어(부분일치)")
    p_ss.add_argument(
        "--product-pick",
        default="",
        help="결과 표에서 선택할 상품명 문자열(부분일치). 비우면 product-contains를 사용",
    )

    p_kb = subs.add_parser("kyobo", help="교보생명 전체상품조회 → 기간별 다운로드(모달) PDF")
    _add_common(p_kb)
    p_kb.add_argument("--list-url", default=KYOBO_LIST_URL, help="교보생명 전체상품조회 URL")
    p_kb.add_argument("--product-contains", required=True, help="상품명 검색어(부분일치)")
    p_kb.add_argument(
        "--product-pick",
        default="",
        help="결과 표에서 선택할 상품명 문자열(부분일치). 비우면 product-contains를 사용",
    )

    p_dy = subs.add_parser("dongyanglife", help="동양생명 판매상품 → MasFiledownload(PDF) 다운로드")
    _add_common(p_dy)
    p_dy.add_argument("--list-url", default=DONGYANG_LIST_URL, help="동양생명 판매상품 공시 URL")
    p_dy.add_argument("--product-contains", required=True, help="상품명 검색어(부분일치)")
    p_dy.add_argument(
        "--product-pick",
        default="",
        help="결과 표에서 선택할 상품명 문자열(부분일치). 비우면 product-contains를 사용",
    )

    p_hk = subs.add_parser("heungkuklife", help="흥국생명 판매상품 → 자동완성 선택 후 약관/사업방법서 PDF")
    _add_common(p_hk)
    p_hk.add_argument("--list-url", default=HEUNGKUK_LIST_URL, help="흥국생명 판매상품 공시 URL")
    p_hk.add_argument("--product-contains", required=True, help="상품명 검색어(부분일치, 자동완성 키워드)")
    p_hk.add_argument(
        "--product-pick",
        default="",
        help="자동완성 목록에서 선택할 상품명 문자열(부분일치). 비우면 첫 항목을 사용",
    )

    p_sh = subs.add_parser("shinhanlife", help="신한라이프 판매중 상품공시 → bizxpress PDF(GET) 저장")
    _add_common(p_sh)
    p_sh.add_argument("--list-url", default=SHINHAN_LIST_URL, help="신한라이프 상품공시(판매중) URL")
    p_sh.add_argument("--product-contains", required=True, help="상품명 검색어(부분일치)")
    p_sh.add_argument(
        "--product-pick",
        default="",
        help="#GoodsList 표에서 선택할 상품명 문자열(부분일치). 비우면 product-contains를 사용",
    )

    p_hw = subs.add_parser("hanwhalife", help="한화생명 상품목록 → 최신 행 약관/사업방법서 PDF")
    _add_common(p_hw)
    p_hw.add_argument("--list-url", default=DEFAULT_LIST_URL, help="한화생명 상품목록 URL")
    p_hw.add_argument("--product-contains", required=True, help="상품명 검색어(부분일치)")
    p_hw.add_argument(
        "--product-pick",
        default="",
        help="검색 결과 목록에서 클릭할 상품명 문자열(부분일치). 비우면 product-contains를 사용",
    )

    args = ap.parse_args()
    if not args.i_accept_site_tos:
        raise SystemExit("중단: --i-accept-site-tos 플래그가 필요합니다.")

    if args.scenario == "samsunglife":
        pick = args.product_pick.strip() or build_samsung_pick(args.product_contains)
        cfg = SamsungScenarioConfig(
            list_url=args.list_url,
            product_contains=args.product_contains,
            product_pick=pick,
            insurer=args.insurer,
            insurer_code=args.insurer_code,
            product_group=args.product_group,
            out_dir=Path(args.out_dir),
            headless=not args.headful,
        )
        paths = run_samsung(cfg)
        print("[ok]", paths)
        return

    if args.scenario == "kyobo":
        pick = args.product_pick.strip() or build_kyobo_pick(args.product_contains)
        cfg = KyoboScenarioConfig(
            list_url=args.list_url,
            product_contains=args.product_contains,
            product_pick=pick,
            insurer=args.insurer,
            insurer_code=args.insurer_code,
            product_group=args.product_group,
            out_dir=Path(args.out_dir),
            headless=not args.headful,
        )
        paths = run_kyobo(cfg)
        print("[ok]", paths)
        return

    if args.scenario == "dongyanglife":
        pick = args.product_pick.strip() or build_dongyang_pick(args.product_contains)
        cfg = DongyangScenarioConfig(
            list_url=args.list_url,
            product_contains=args.product_contains,
            product_pick=pick,
            insurer=args.insurer,
            insurer_code=args.insurer_code,
            product_group=args.product_group,
            out_dir=Path(args.out_dir),
            headless=not args.headful,
        )
        paths = run_dongyang(cfg)
        print("[ok]", paths)
        return

    if args.scenario == "heungkuklife":
        pick = args.product_pick.strip() or build_heungkuk_pick(args.product_contains)
        cfg = HeungkukScenarioConfig(
            list_url=args.list_url,
            product_contains=args.product_contains,
            product_pick=pick if args.product_pick.strip() else "",
            insurer=args.insurer,
            insurer_code=args.insurer_code,
            product_group=args.product_group,
            out_dir=Path(args.out_dir),
            headless=not args.headful,
        )
        paths = run_heungkuk(cfg)
        print("[ok]", paths)
        return

    if args.scenario == "shinhanlife":
        pick = args.product_pick.strip() or build_shinhan_pick(args.product_contains)
        cfg = ShinhanScenarioConfig(
            list_url=args.list_url,
            product_contains=args.product_contains,
            product_pick=pick,
            insurer=args.insurer,
            insurer_code=args.insurer_code,
            product_group=args.product_group,
            out_dir=Path(args.out_dir),
            headless=not args.headful,
        )
        paths = run_shinhan(cfg)
        print("[ok]", paths)
        return

    if args.scenario == "hanwhalife":
        pick = args.product_pick.strip() or build_product_pick_from_contains(args.product_contains)
        cfg = HanwhaScenarioConfig(
            list_url=args.list_url,
            product_contains=args.product_contains,
            product_pick=pick,
            insurer=args.insurer,
            insurer_code=args.insurer_code,
            product_group=args.product_group,
            out_dir=Path(args.out_dir),
            headless=not args.headful,
        )
        paths = run(cfg)
        print("[ok]", paths)
        return

    raise SystemExit(f"unknown scenario: {args.scenario}")


if __name__ == "__main__":
    main()
