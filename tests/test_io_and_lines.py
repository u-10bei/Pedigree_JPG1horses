import filecmp

from pedigree import io
from pedigree.lines import assign_lines
from pedigree.validate import validate


def test_repository_data_is_valid():
    issues = validate(io.load())
    assert issues == [], "\n".join(map(str, issues))


def test_save_roundtrip_is_byte_identical(tmp_path):
    io.save(io.load(), tmp_path)
    for name in (io.PEDIGREE_FILE, io.RACE_WINNER_FILE, io.RACES_FILE, io.LINES_FILE):
        assert filecmp.cmp(io.DATA_DIR / name, tmp_path / name, shallow=False), name


def test_black_hawk_is_merged():
    ds = io.load()
    black_hawk = ds.by_name()["ブラックホーク"]
    assert sum(1 for w in ds.wins if w.winner_id == black_hawk.id) == 2


def test_nearest_line_wins():
    ds = io.load()
    lines = assign_lines(ds)
    names = ds.by_name()
    assert lines[names["ディープインパクト"].id].name == "サンデーサイレンス系"
    assert lines[names["Halo"].id].name == "ヘイルトゥリーズン系"
    assert lines[names["Eclipse"].id].name == "ダーレーアラビアン系"
    assert lines[names["シンボリルドルフ"].id].name == "バイアリーターク系"
