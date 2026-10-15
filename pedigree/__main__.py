"""`python -m pedigree validate` でデータを検証する。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import io
from .validate import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pedigree")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate", help="data/*.csv の整合性を検証する")
    p_validate.add_argument("--data-dir", type=Path, default=io.DATA_DIR)
    args = parser.parse_args(argv)

    if args.command == "validate":
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
    return 2


if __name__ == "__main__":
    sys.exit(main())
