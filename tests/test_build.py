from pedigree import build, io
from pedigree.models import Dataset, Horse, Line, Race, RaceWin


def small() -> Dataset:
    return Dataset(
        horses={
            0: Horse(0, "__origin__", 0),
            1: Horse(1, "始祖", 0),
            2: Horse(2, "大系統の祖", 1),
            3: Horse(3, "小系統の祖", 2),
            4: Horse(4, "勝ち馬", 3, 2000),
        },
        wins=[RaceWin(2003, "東京優駿", 4), RaceWin(2003, "菊花賞", 4)],
        races={"東京優駿": Race("東京優駿", 1932), "菊花賞": Race("菊花賞", 1938)},
        lines=[Line("大系統の祖", "大系統", "#2a78d6"), Line("小系統の祖", "小系統", None), Line("始祖", "始祖系", None)],
    )


def test_line_without_color_inherits_ancestor_line_color():
    colors = build.line_colors(small())
    assert colors == {"大系統": "#2a78d6", "小系統": "#2a78d6", "始祖系": None}


def test_build_json_contents():
    data = build.build(small())
    horses = {h["name"]: h for h in data["horses"]}
    assert horses["勝ち馬"] == {
        "id": 4, "name": "勝ち馬", "father": 3, "birth": 2000,
        "wins": [[2003, "東京優駿"], [2003, "菊花賞"]], "line": "小系統",
    }
    assert horses["小系統の祖"]["lineRoot"] is True
    assert horses["__origin__"]["father"] is None
    assert data["lastYear"] == 2003


def test_build_repository_data(tmp_path):
    path = build.write(io.load(), tmp_path / "pedigree.json")
    assert path.stat().st_size > 0
