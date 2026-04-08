from __future__ import annotations

import argparse

from .pipeline import run_single


def main():
    ap = argparse.ArgumentParser(description="보험 약관 검토 엑셀 생성기(MVP)")
    ap.add_argument("--rules", required=True, help="룰 YAML 경로 (예: rules/payment_rules.yaml)")
    ap.add_argument("--input", required=True, help="입력 JSON 경로 (예: examples/input.json)")
    ap.add_argument("--out", required=True, help="출력 xlsx 경로 (예: out/PolicyReview.xlsx)")
    ap.add_argument("--th-sim", type=float, default=0.60, help="타사 유사 판정 임계치(복합 유사도 기준)")
    args = ap.parse_args()

    run_single(rules_path=args.rules, input_path=args.input, out_xlsx_path=args.out, th_sim=args.th_sim)


if __name__ == "__main__":
    main()

