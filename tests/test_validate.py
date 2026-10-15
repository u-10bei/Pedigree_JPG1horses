from dataclasses import replace

import pytest

from pedigree.models import Dataset, Horse, Line, Race, RaceWin
from pedigree.validate import validate


@pytest.fixture
def ds() -> Dataset:
    horses = {
        0: Horse(0, "__origin__", 0),
        1: Horse(1, "始祖", 0, 1700),
        2: Horse(2, "父", 1, 1990),
        3: Horse(3, "子", 2),
    }
    return Dataset(
        horses=horses,
        wins=[RaceWin(2000, "東京優駿", 3)],
        races={"東京優駿": Race("東京優駿", 1932), "大阪杯": Race("大阪杯", 2017)},
        lines=[Line("始祖", "始祖系", "#123456")],
    )


def messages(ds: Dataset) -> list[str]:
    return [str(issue) for issue in validate(ds)]


def test_valid_dataset_has_no_issues(ds):
    assert messages(ds) == []


def test_blank_birth_years_are_allowed(ds):
    ds.horses = {hid: replace(h, birth_year=None) for hid, h in ds.horses.items()}
    assert messages(ds) == []


def test_duplicate_name(ds):
    ds.horses[4] = Horse(4, "子", 2)
    assert any("「子」が重複" in m for m in messages(ds))


def test_missing_father(ds):
    ds.horses[4] = Horse(4, "孤児", 99)
    assert any("父 Id 99 が存在しません" in m for m in messages(ds))


def test_cycle(ds):
    ds.horses[4] = Horse(4, "甲", 5)
    ds.horses[5] = Horse(5, "乙", 4)
    assert any("循環" in m for m in messages(ds))


def test_father_born_after_child(ds):
    ds.horses[3] = replace(ds.horses[3], birth_year=1985)
    assert any("より先に生まれています" in m for m in messages(ds))


def test_unknown_race(ds):
    ds.wins.append(RaceWin(2000, "架空賞", 3))
    assert any("races.csv にないレース名" in m for m in messages(ds))


def test_race_before_first_year(ds):
    ds.wins.append(RaceWin(2016, "大阪杯", 3))
    assert any("対象期間外" in m for m in messages(ds))


def test_winner_too_young(ds):
    ds.horses[3] = replace(ds.horses[3], birth_year=1999)
    assert any("年齢が合いません" in m for m in messages(ds))


def test_dead_heat_is_allowed(ds):
    ds.horses[4] = Horse(4, "同着馬", 2)
    ds.wins.append(RaceWin(2000, "東京優駿", 4))
    assert messages(ds) == []


def test_duplicate_win(ds):
    ds.wins.append(RaceWin(2000, "東京優駿", 3))
    assert any("重複" in m for m in messages(ds))


def test_line_with_unknown_horse_and_bad_color(ds):
    ds.lines.append(Line("不明馬", "不明系", "red"))
    msgs = messages(ds)
    assert any("「不明馬」が pedigree.csv にありません" in m for m in msgs)
    assert any("#RRGGBB" in m for m in msgs)
