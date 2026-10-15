"""コマンドライン。

    python -m pedigree validate   data/*.csv の整合性を検証する
    python -m pedigree fetch winners --from 2005   Wikipedia から勝ち馬を取得する
    python -m pedigree fetch horses                Wikidata から父・生年を取得する
    python -m pedigree review     staging の取得データを照合し staging/review.csv を作る
    python -m pedigree apply      review.csv の承認済みの行を data/ に反映する
    python -m pedigree add horse 馬名 --father 父 [--birth 生年]   馬を 1 頭追加する
    python -m pedigree add win 年 レース 馬名                      勝利を 1 件追加する
    python -m pedigree admin      確認画面（Streamlit）を開く
    python -m pedigree build      階層図用の site/data/pedigree.json を作る
    python -m pedigree births     生年が空欄の馬の生年を review.csv に追加する
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
    merge.write_review(merge.remaining_rows(rows), args.staging_dir / merge.REVIEW_FILE)
    print(f"反映しました：新規馬 {counts['horse']} / 生年 {counts['birth_year']} / 勝利 {counts['win']}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    if args.target == "horse":
        row = merge.ReviewRow(
            Approve="y", Kind=merge.KIND_HORSE, Horse=args.name, Father=args.father, BirthYear=args.birth or ""
        )
    else:
        row = merge.ReviewRow(Approve="y", Kind=merge.KIND_WIN, Ryear=args.year, Rtitle=args.race, Horse=args.name)
    try:
        result, _ = merge.apply_review(io.load(args.data_dir), [row])
    except merge.ApplyError as e:
        for problem in e.problems:
            print(f"ERROR {problem}", file=sys.stderr)
        return 1
    io.save(result, args.data_dir)
    print("追加しました")
    return 0


def cmd_admin(args: argparse.Namespace) -> int:
    import subprocess

    app = Path(__file__).with_name("admin_app.py")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), *args.extra])


def cmd_fetch(args: argparse.Namespace) -> int:
    from .fetch import run
    from .fetch.client import Client

    ds = io.load(args.data_dir)
    client = Client(min_interval=args.interval)
    if args.target == "winners":
        rows = run.fetch_winners(ds, client, args.year_from, args.year_to)
        path = run.write_winners(rows, args.staging_dir)
        print(f"{path}: {len(rows)} 件")
    else:
        raw_wins, _ = merge.load_raw(args.staging_dir)
        rows = run.fetch_horses(ds, client, raw_wins, include_existing=not args.no_existing)
        path = run.write_horses(rows, args.staging_dir)
        print(f"{path}: {len(rows)} 頭")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from . import build

    ds = io.load(args.data_dir)
    issues = validate(ds)
    if issues:
        for issue in issues:
            print(f"ERROR {issue}", file=sys.stderr)
        return 1
    print(f"{build.write(ds, args.output)}")
    return 0


def cmd_births(args: argparse.Namespace) -> int:
    from . import births

    ds = io.load(args.data_dir)
    rows = births.infer_from_races(ds)
    print(f"年齢限定戦から計算：{len(rows)} 頭")
    if not args.no_fetch:
        from .fetch import run
        from .fetch.client import Client

        done = {r.Horse for r in rows}
        rest = [h for h in births.missing_horses(ds) if h.name not in done]
        fetched = run.fetch_birth_years(ds, Client(min_interval=args.interval), rest)
        print(f"Wikipedia の情報欄から取得：{len(fetched)} 頭（対象 {len(rest)} 頭）")
        rows += fetched
    path = args.staging_dir / merge.REVIEW_FILE
    merged, added = births.add_rows(merge.read_review(path), rows)
    merge.write_review(merged, path)
    left = len(births.missing_horses(ds)) - len({r.Horse for r in rows})
    print(f"{path} に {added} 行を追加しました（まだ分からない馬 {left} 頭は確認画面の「生年の入力」タブで入力できます）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pedigree")
    parser.add_argument("--data-dir", type=Path, default=io.DATA_DIR)
    parser.add_argument("--staging-dir", type=Path, default=merge.STAGING_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="data/*.csv の整合性を検証する").set_defaults(func=cmd_validate)
    sub.add_parser("review", help="取得データを照合して review.csv を作る").set_defaults(func=cmd_review)
    p_fetch = sub.add_parser("fetch", help="Wikipedia・Wikidata から取得して staging/ に保存する")
    p_fetch.add_argument("target", choices=["winners", "horses"])
    p_fetch.add_argument("--from", dest="year_from", type=int, default=1932, help="勝ち馬を取得する最初の年")
    p_fetch.add_argument("--to", dest="year_to", type=int, default=9999, help="勝ち馬を取得する最後の年")
    p_fetch.add_argument("--no-existing", action="store_true", help="既存の馬の生年は取得しない")
    p_fetch.add_argument("--interval", type=float, default=1.0, help="リクエストの最小間隔（秒）")
    p_fetch.set_defaults(func=cmd_fetch)
    p_apply = sub.add_parser("apply", help="review.csv の承認済みの行を data/ に反映する")
    p_apply.add_argument("--dry-run", action="store_true", help="検証だけして保存しない")
    p_apply.set_defaults(func=cmd_apply)
    p_add = sub.add_parser("add", help="馬または勝利を 1 件追加する")
    add_sub = p_add.add_subparsers(dest="target", required=True)
    p_add_horse = add_sub.add_parser("horse", help="馬を追加する")
    p_add_horse.add_argument("name")
    p_add_horse.add_argument("--father", required=True)
    p_add_horse.add_argument("--birth", help="生年（省略可）")
    p_add_win = add_sub.add_parser("win", help="勝利を追加する")
    p_add_win.add_argument("year")
    p_add_win.add_argument("race")
    p_add_win.add_argument("name")
    p_add.set_defaults(func=cmd_add)
    p_build = sub.add_parser("build", help="階層図用の JSON を作る")
    p_build.add_argument("--output", type=Path, default=Path(__file__).resolve().parent.parent / "site" / "data" / "pedigree.json")
    p_build.set_defaults(func=cmd_build)
    p_births = sub.add_parser("births", help="生年が空欄の馬の生年を review.csv に追加する")
    p_births.add_argument("--no-fetch", action="store_true", help="Wikipedia から取得せず、年齢限定戦からの計算だけ行う")
    p_births.add_argument("--interval", type=float, default=1.0, help="リクエストの最小間隔（秒）")
    p_births.set_defaults(func=cmd_births)
    p_admin = sub.add_parser("admin", help="確認画面（Streamlit）を開く。後ろのオプションは Streamlit に渡す")
    p_admin.set_defaults(func=cmd_admin)
    args, extra = parser.parse_known_args(argv)
    if extra and args.command != "admin":
        parser.error(f"不明な引数です: {' '.join(extra)}")
    args.extra = extra
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
