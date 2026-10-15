"""コマンドライン。

    python -m pedigree validate   data/*.csv の整合性を検証する
    python -m pedigree review     staging の取得データを照合し staging/review.csv を作る
    python -m pedigree apply      review.csv の承認済みの行を data/ に反映する
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import io, merge
from .validate import validate


def cmd_validate(args: argparse.Namespace) -> int:
    ds = io.load(args.data_dir)
    issues = validate(ds)
    for issue in issues:
        print(f"ERROR {issue}", file=sys.stderr)
    blank = sum(1 for h in ds.horses.values() if h.birth_year is None) - 1
    print(
        f"{len(ds.horses) - 1} 頭 / {len(ds.wins)} 勝 / {len(ds.races)} レース / "
        f"{len(ds.lines)} 系統（生年未入力 {blank} 頭）: エラー {len(issues)} 件"
    )
    return 1 if issues else 0


def cmd_review(args: argparse.Namespace) -> int:
    ds = io.load(args.data_dir)
    raw_wins, raw_horses = merge.load_raw(args.staging_dir)
    if not raw_wins and not raw_horses:
        print(f"{args.staging_dir} に取得データがありません", file=sys.stderr)
        return 1
    rows = merge.build_review(ds, raw_wins, raw_horses)
    path = args.staging_dir / merge.REVIEW_FILE
    merge.write_review(rows, path)

    kinds = Counter(r.Kind for r in rows)
    pending = sum(1 for r in rows if r.Note)
    print(
        f"{path}: 新規馬 {kinds[merge.KIND_HORSE]} / 生年 {kinds[merge.KIND_BIRTH_YEAR]} / "
        f"勝利 {kinds[merge.KIND_WIN]} / 要確認 {pending}"
    )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    ds = io.load(args.data_dir)
    rows = merge.read_review(args.staging_dir / merge.REVIEW_FILE)
    try:
        result, counts = merge.apply_review(ds, rows)
    except merge.ApplyError as e:
        for problem in e.problems:
            print(f"ERROR {problem}", file=sys.stderr)
        print("反映を中止しました（data/ は変更していません）", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"（確認のみ）新規馬 {counts['horse']} / 生年 {counts['birth_year']} / 勝利 {counts['win']}")
        return 0
    io.save(result, args.data_dir)
    print(f"反映しました：新規馬 {counts['horse']} / 生年 {counts['birth_year']} / 勝利 {counts['win']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pedigree")
    parser.add_argument("--data-dir", type=Path, default=io.DATA_DIR)
    parser.add_argument("--staging-dir", type=Path, default=merge.STAGING_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="data/*.csv の整合性を検証する").set_defaults(func=cmd_validate)
    sub.add_parser("review", help="取得データを照合して review.csv を作る").set_defaults(func=cmd_review)
    p_apply = sub.add_parser("apply", help="review.csv の承認済みの行を data/ に反映する")
    p_apply.add_argument("--dry-run", action="store_true", help="検証だけして保存しない")
    p_apply.set_defaults(func=cmd_apply)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
