"""データの整合性チェック。

エラーが 1 件でもあれば CI を失敗させる。BirthYear など任意項目の空欄はエラーにしない。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .models import ORIGIN_ID, Dataset

# 三大始祖（1680 年前後生まれ）より前の生年はありえない
MIN_BIRTH_YEAR = 1600
# G1 に出走できる最低年齢（2 歳戦）
MIN_RACE_AGE = 2

COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class Issue:
    file: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.message}"


def validate(ds: Dataset) -> list[Issue]:
    return [
        *_check_horses(ds),
        *_check_ancestry(ds),
        *_check_birth_years(ds),
        *_check_wins(ds),
        *_check_lines(ds),
    ]


def _check_horses(ds: Dataset) -> list[Issue]:
    issues = []
    if ORIGIN_ID not in ds.horses:
        issues.append(Issue("pedigree.csv", f"仮想ルート（Id {ORIGIN_ID}）がありません"))

    for h in ds.horses.values():
        if not h.name:
            issues.append(Issue("pedigree.csv", f"Id {h.id}: 馬名が空です"))
        if h.id != ORIGIN_ID and h.father_id not in ds.horses:
            issues.append(
                Issue("pedigree.csv", f"{h.name}（Id {h.id}）: 父 Id {h.father_id} が存在しません")
            )

    counts = Counter(h.name for h in ds.horses.values())
    for name, count in sorted(counts.items()):
        if count > 1:
            ids = sorted(h.id for h in ds.horses.values() if h.name == name)
            issues.append(Issue("pedigree.csv", f"馬名「{name}」が重複しています（Id {ids}）"))
    return issues


def _check_ancestry(ds: Dataset) -> list[Issue]:
    """全頭が循環せずに仮想ルートまでたどれるか。"""
    issues = []
    reachable = {ORIGIN_ID}
    for start in ds.horses.values():
        path: list[int] = []
        seen: set[int] = set()
        current = start.id
        while current not in reachable:
            if current in seen:
                issues.append(Issue("pedigree.csv", f"{start.name}（Id {start.id}）: 父系が循環しています"))
                break
            horse = ds.horses.get(current)
            if horse is None:
                break  # 父 Id の欠落は _check_horses で報告済み
            seen.add(current)
            path.append(current)
            current = horse.father_id
        else:
            reachable.update(path)
    return issues


def _check_birth_years(ds: Dataset) -> list[Issue]:
    issues = []
    for h in ds.horses.values():
        if h.birth_year is None:
            continue
        if h.birth_year < MIN_BIRTH_YEAR:
            issues.append(Issue("pedigree.csv", f"{h.name}: 生年 {h.birth_year} が古すぎます"))
        father = ds.horses.get(h.father_id)
        if (
            h.id != ORIGIN_ID
            and father is not None
            and father.birth_year is not None
            and father.birth_year >= h.birth_year
        ):
            issues.append(
                Issue(
                    "pedigree.csv",
                    f"{h.name}（{h.birth_year}年生）: 父 {father.name}（{father.birth_year}年生）より先に生まれています",
                )
            )
    return issues


def _check_wins(ds: Dataset) -> list[Issue]:
    issues = []
    for w in ds.wins:
        label = f"{w.year} {w.race}"
        horse = ds.horses.get(w.winner_id)
        if horse is None or w.winner_id == ORIGIN_ID:
            issues.append(Issue("race_winner.csv", f"{label}: 勝ち馬 Id {w.winner_id} が存在しません"))
        race = ds.races.get(w.race)
        if race is None:
            issues.append(Issue("race_winner.csv", f"{label}: races.csv にないレース名です"))
        elif not race.held_in(w.year):
            issues.append(Issue("race_winner.csv", f"{label}: 対象期間外の年です（{race.first_year}年から）"))
        if horse is not None and horse.birth_year is not None and w.year - horse.birth_year < MIN_RACE_AGE:
            issues.append(
                Issue("race_winner.csv", f"{label}: {horse.name}（{horse.birth_year}年生）の年齢が合いません")
            )

    counts = Counter((w.year, w.race, w.winner_id) for w in ds.wins)
    for (year, race, winner_id), count in sorted(counts.items()):
        if count > 1:
            issues.append(Issue("race_winner.csv", f"{year} {race}: 勝ち馬 Id {winner_id} が重複しています"))
    return issues


def _check_lines(ds: Dataset) -> list[Issue]:
    issues = []
    names = ds.by_name()
    for line in ds.lines:
        if line.horse not in names:
            issues.append(Issue("lines.csv", f"{line.name}: 起点の馬「{line.horse}」が pedigree.csv にありません"))
        if not line.name:
            issues.append(Issue("lines.csv", f"{line.horse}: 系統名が空です"))
        if line.color is not None and not COLOR_PATTERN.match(line.color):
            issues.append(Issue("lines.csv", f"{line.name}: 色 {line.color} は #RRGGBB 形式で指定してください"))

    for field_name, counter in (
        ("起点の馬", Counter(line.horse for line in ds.lines)),
        ("系統名", Counter(line.name for line in ds.lines)),
    ):
        for value, count in sorted(counter.items()):
            if count > 1:
                issues.append(Issue("lines.csv", f"{field_name}「{value}」が重複しています"))
    return issues
