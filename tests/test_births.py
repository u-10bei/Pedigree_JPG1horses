from pedigree import births
from pedigree.merge import ReviewRow
from pedigree.models import Dataset, Horse, Race, RaceWin


def ds() -> Dataset:
    return Dataset(
        horses={
            0: Horse(0, "__origin__", 0),
            1: Horse(1, "父", 0, 1990),
            2: Horse(2, "ダービー馬", 1),
            3: Horse(3, "2歳王者", 1),
            4: Horse(4, "古馬", 1),
            5: Horse(5, "矛盾", 1),
            6: Horse(6, "生年あり", 1, 2001),
        },
        wins=[
            RaceWin(2004, "東京優駿", 2),
            RaceWin(2004, "菊花賞", 2),
            RaceWin(2003, "朝日杯フューチュリティステークス", 3),
            RaceWin(2005, "天皇賞（春）", 4),
            RaceWin(2004, "皐月賞", 5),
            RaceWin(2006, "桜花賞", 5),
            RaceWin(2004, "東京優駿", 6),
        ],
        races={},
    )


def test_infer_from_age_restricted_races():
    rows = {r.Horse: r for r in births.infer_from_races(ds())}
    assert (rows["ダービー馬"].BirthYear, rows["ダービー馬"].Approve) == ("2001", "y")
    assert "2004 東京優駿" in rows["ダービー馬"].Source
    assert rows["2歳王者"].BirthYear == "2001"
    assert "古馬" not in rows  # 年齢限定戦を勝っていない
    assert "生年あり" not in rows  # すでに生年がある
    assert rows["矛盾"].Approve == "" and "一致しません" in rows["矛盾"].Note


def test_add_rows_skips_horses_already_in_review():
    existing = [ReviewRow(Kind="birth_year", Horse="ダービー馬", BirthYear="2001")]
    new = [ReviewRow(Kind="birth_year", Horse="ダービー馬", BirthYear="2001"), ReviewRow(Kind="birth_year", Horse="2歳王者", BirthYear="2001")]
    merged, added = births.add_rows(existing, new)
    assert added == 1 and [r.Horse for r in merged] == ["ダービー馬", "2歳王者"]
