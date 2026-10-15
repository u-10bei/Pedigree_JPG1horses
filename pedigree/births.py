"""生年が空欄の馬の生年を埋める。

1. 年齢限定戦の勝ち馬は、勝った年と出走できる年齢から生年を計算する（確定値）
2. それ以外は Wikipedia の情報欄（日本語版「生誕」、英語版「Foaled」）から取る（fetch 側）

結果は staging/review.csv に「生年」の行として追加し、確認画面で確認してから反映する。
"""

from __future__ import annotations

from .merge import KIND_BIRTH_YEAR, ReviewRow
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
