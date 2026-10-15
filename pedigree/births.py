"""生年が空欄の馬の生年を埋める。

1. 年齢限定戦の勝ち馬は、勝った年と出走できる年齢から生年を計算する（確定値）
2. それ以外は Wikipedia の情報欄（日本語版「生誕」、英語版「Foaled」）から取る（fetch 側）

結果は staging/review.csv に「生年」の行として追加し、確認画面で確認してから反映する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .merge import KIND_BIRTH_YEAR, ReviewRow, normalize
from .models import ORIGIN_ID, Dataset

# 出走できる年齢が決まっているレース（年齢は満年齢）
AGE_RESTRICTED = {
    "皐月賞": 3,
    "東京優駿": 3,
    "菊花賞": 3,
    "桜花賞": 3,
    "優駿牝馬": 3,
    "NHKマイルカップ": 3,
    "秋華賞": 3,
    "朝日杯フューチュリティステークス": 2,
    "阪神ジュベナイルフィリーズ": 2,
    "ホープフルステークス": 2,
}

SOURCE_RACE = "race:"


def missing_horses(ds: Dataset) -> list:
    return [h for h in ds.horses.values() if h.id != ORIGIN_ID and h.birth_year is None]


def infer_from_races(ds: Dataset) -> list[ReviewRow]:
    """年齢限定戦の勝ち馬の生年を計算する。勝利によって計算結果が食い違う場合は要確認にする。"""
    candidates: dict[int, dict[int, list[str]]] = {}
    for w in ds.wins:
        age = AGE_RESTRICTED.get(w.race)
        if age is None:
            continue
        candidates.setdefault(w.winner_id, {}).setdefault(w.year - age, []).append(f"{w.year} {w.race}")

    rows = []
    for horse in missing_horses(ds):
        years = candidates.get(horse.id)
        if not years:
            continue
        if len(years) == 1:
            (year, races), = years.items()
            rows.append(
                ReviewRow(
                    Approve="y",
                    Kind=KIND_BIRTH_YEAR,
                    Horse=horse.name,
                    BirthYear=str(year),
                    Source=SOURCE_RACE + "、".join(races),
                )
            )
        else:
            detail = " / ".join(f"{y}年（{'、'.join(r)}）" for y, r in sorted(years.items()))
            rows.append(
                ReviewRow(
                    Kind=KIND_BIRTH_YEAR,
                    Horse=horse.name,
                    Note=f"勝ったレースから計算した生年が一致しません：{detail}",
                    Source=SOURCE_RACE,
                )
            )
    return rows


def add_rows(existing: list[ReviewRow], new: list[ReviewRow]) -> tuple[list[ReviewRow], int]:
    """確認一覧に生年の行を追加する。同じ馬の生年の行がすでにあれば追加しない。"""
    have = {r.Horse for r in existing if r.Kind == KIND_BIRTH_YEAR}
    added = [r for r in new if r.Horse not in have]
    return [*existing, *added], len(added)


# --- 貼り付けた「馬名 生年」の読み取り ---------------------------------------

# 生年（直後の「年」「年生」も含めて取り除く。馬名の中の「年」「生」は残す）
_YEAR_IN_LINE = re.compile(r"(?<!\d)(1[6-9]\d\d|20\d\d)(?!\d)(?:年生?)?")
_SEPARATORS = re.compile(r"[\t,，、|：:（）()\[\]「」]+")


@dataclass(frozen=True)
class PastedYear:
    text: str  # 貼り付けた行
    name: str  # 行から読み取った馬名
    year: int | None
    horse: str | None  # 対応する data/ の馬名（見つからなければ None）
    note: str = ""


def parse_pasted(text: str, ds: Dataset, aliases: dict[str, str] | None = None) -> list[PastedYear]:
    """1 行に 1 頭の「馬名 生年」を読み取り、data/ の馬に対応付ける。

    区切りはタブ・空白・カンマなど何でもよい。「Eclipse（1764）」「1764年生」のような書き方も読む。
    aliases は 別表記（正規化済み）→ data/ の馬名。
    """
    by_name = {normalize(h.name): h for h in ds.horses.values() if h.id != ORIGIN_ID}
    aliases = aliases or {}
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _YEAR_IN_LINE.search(line)
        year = int(match.group(1)) if match else None
        rest = (line[: match.start()] + " " + line[match.end() :]) if match else line
        name = re.sub(r"\s+", " ", _SEPARATORS.sub(" ", rest)).strip()
        horse = by_name.get(normalize(name))
        if horse is None and normalize(name) in aliases:
            horse = by_name.get(normalize(aliases[normalize(name)]))
        if year is None:
            results.append(PastedYear(line, name, None, horse.name if horse else None, "生年が読み取れません"))
        elif horse is None:
            results.append(PastedYear(line, name, year, None, "data/ に該当する馬がいません"))
        elif horse.birth_year is not None and horse.birth_year != year:
            results.append(PastedYear(line, name, year, horse.name, f"登録済みの生年（{horse.birth_year}）と異なります"))
        elif horse.birth_year == year:
            results.append(PastedYear(line, name, year, horse.name, "登録済みの生年と同じです"))
        else:
            results.append(PastedYear(line, name, year, horse.name))
    return results


def lineage_order(ds: Dataset) -> list[int]:
    """始祖から深さ優先でたどった馬の順。同じ父系の馬が続けて並ぶ。"""
    children = ds.children()
    order, stack = [], [ORIGIN_ID]
    while stack:
        horse_id = stack.pop()
        order.append(horse_id)
        stack.extend(sorted(children.get(horse_id, []), key=lambda c: ds.horses[c].name, reverse=True))
    return order


def load_aliases(ds: Dataset, horses_raw_path) -> dict[str, str]:
    """取得時に保存した別表記（staging/horses_raw.csv）から、別表記（正規化済み）→ data/ の馬名。"""
    import csv
    from pathlib import Path

    path = Path(horses_raw_path)
    if not path.exists():
        return {}
    known = {normalize(h.name): h.name for h in ds.horses.values() if h.id != ORIGIN_ID}
    aliases: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            names = [row["Horse"], *[a for a in (row.get("AltNames") or "").split("|") if a]]
            target = next((known[normalize(n)] for n in names if normalize(n) in known), None)
            if target:
                for n in names:
                    aliases.setdefault(normalize(n), target)
    return aliases
