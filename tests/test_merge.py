import pytest

from pedigree import merge
from pedigree.merge import RawHorse, RawWin, ReviewRow, apply_review, build_review, normalize
from pedigree.models import Dataset, Horse, Race, RaceWin


@pytest.fixture
def ds() -> Dataset:
    return Dataset(
        horses={
            0: Horse(0, "__origin__", 0),
            1: Horse(1, "Halo", 0),
            2: Horse(2, "サンデーサイレンス", 1),
            3: Horse(3, "ディープインパクト", 2),
        },
        wins=[RaceWin(2005, "東京優駿", 3)],
        races={"東京優駿": Race("東京優駿", 1932), "大阪杯": Race("大阪杯", 2017)},
    )


def raw(name, father=None, birth=None, alt=()):
    return RawHorse(name, tuple(alt), father, birth, "test")


def by_kind(rows, kind):
    return [r for r in rows if r.Kind == kind]


def test_normalize():
    assert normalize("エルコンドルパサー (USA)") == normalize("エルコンドルパサー")
    assert normalize("ハーツクライ（競走馬）") == normalize("ハーツクライ")
    assert normalize("Ｈａｌｏ") == normalize("halo")


def test_new_winner_with_unknown_sire_chain(ds):
    rows = build_review(
        ds,
        [RawWin(2012, "東京優駿", "ディープブリランテ", "w")],
        [
            raw("ディープブリランテ", "ディープインパクト", 2009),
            raw("ディープインパクト", "サンデーサイレンス", 2002),
        ],
    )
    horses = by_kind(rows, merge.KIND_HORSE)
    assert [(r.Horse, r.Father, r.BirthYear, r.Approve) for r in horses] == [
        ("ディープブリランテ", "ディープインパクト", "2009", "y")
    ]
    assert [(r.Horse, r.BirthYear) for r in by_kind(rows, merge.KIND_BIRTH_YEAR)] == [("ディープインパクト", "2002")]
    assert [(r.Ryear, r.Horse, r.Approve) for r in by_kind(rows, merge.KIND_WIN)] == [("2012", "ディープブリランテ", "y")]


def test_ancestors_are_proposed_until_known_horse(ds):
    rows = build_review(
        ds,
        [RawWin(2020, "東京優駿", "コントレイル", "w")],
        [
            raw("コントレイル", "ディープインパクト"),
            raw("ステイゴールド", "サンデーサイレンス"),
        ],
    )
    assert [r.Horse for r in by_kind(rows, merge.KIND_HORSE)] == ["コントレイル"]

    rows = build_review(
        ds,
        [RawWin(2011, "東京優駿", "オルフェーヴル", "w")],
        [raw("オルフェーヴル", "ステイゴールド"), raw("ステイゴールド", "サンデーサイレンス")],
    )
    assert [(r.Horse, r.Approve) for r in by_kind(rows, merge.KIND_HORSE)] == [
        ("オルフェーヴル", "y"),
        ("ステイゴールド", "y"),
    ]


def test_alt_name_matches_existing_horse(ds):
    rows = build_review(
        ds,
        [RawWin(2010, "東京優駿", "エイシンフラッシュ", "w")],
        [raw("エイシンフラッシュ", "King's Best"), raw("キングズベスト", "Halo", alt=["King's Best"])],
    )
    horses = {r.Horse: r for r in by_kind(rows, merge.KIND_HORSE)}
    assert horses["エイシンフラッシュ"].Father == "キングズベスト"
    assert horses["キングズベスト"].Father == "Halo"


def test_unresolvable_chain_needs_review(ds):
    rows = build_review(ds, [RawWin(2010, "東京優駿", "謎の馬", "w")], [raw("謎の馬", "謎の父")])
    win = by_kind(rows, merge.KIND_WIN)[0]
    assert win.Approve == "" and "つながりません" in win.Note
    notes = {r.Horse: r.Note for r in by_kind(rows, merge.KIND_HORSE)}
    assert "取得できていません" in notes["謎の父"]


def test_existing_and_out_of_range_wins_are_skipped(ds):
    rows = build_review(
        ds,
        [RawWin(2005, "東京優駿", "ディープインパクト", "w"), RawWin(2016, "大阪杯", "ディープインパクト", "w")],
        [],
    )
    assert by_kind(rows, merge.KIND_WIN) == []


def test_unknown_race_needs_review(ds):
    rows = build_review(ds, [RawWin(2010, "架空賞", "ディープインパクト", "w")], [])
    assert "races.csv" in by_kind(rows, merge.KIND_WIN)[0].Note


def test_conflicts_are_reported_as_checks(ds):
    ds.horses[3] = Horse(3, "ディープインパクト", 2, 2002)
    rows = build_review(ds, [], [raw("ディープインパクト", "Halo", 2003)])
    notes = [r.Note for r in by_kind(rows, merge.KIND_CHECK)]
    assert any("生年" in n for n in notes) and any("父" in n for n in notes)
    assert all(r.Approve == "" for r in by_kind(rows, merge.KIND_CHECK))


def test_apply_approved_rows_in_dependency_order(ds):
    rows = [
        ReviewRow(Approve="y", Kind="win", Ryear="2011", Rtitle="東京優駿", Horse="オルフェーヴル"),
        ReviewRow(Approve="y", Kind="horse", Horse="オルフェーヴル", Father="ステイゴールド", BirthYear="2008"),
        ReviewRow(Approve="y", Kind="horse", Horse="ステイゴールド", Father="サンデーサイレンス"),
        ReviewRow(Approve="y", Kind="birth_year", Horse="ディープインパクト", BirthYear="2002"),
        ReviewRow(Approve="", Kind="horse", Horse="未承認", Father="Halo"),
    ]
    result, counts = apply_review(ds, rows)
    assert counts == {"horse": 2, "birth_year": 1, "win": 1}
    names = result.by_name()
    assert names["オルフェーヴル"].father_id == names["ステイゴールド"].id
    assert names["ディープインパクト"].birth_year == 2002
    assert "未承認" not in names
    assert "オルフェーヴル" not in ds.by_name()  # 元のデータは変更しない


def test_apply_rejects_invalid_result(ds):
    rows = [ReviewRow(Approve="y", Kind="horse", Horse="孤児", Father="いない馬")]
    with pytest.raises(merge.ApplyError, match="登録されていません"):
        apply_review(ds, rows)

    rows = [ReviewRow(Approve="y", Kind="birth_year", Horse="ディープインパクト", BirthYear="1980")]
    ds.horses[2] = Horse(2, "サンデーサイレンス", 1, 1986)
    with pytest.raises(merge.ApplyError, match="より先に生まれています"):
        apply_review(ds, rows)


def test_review_file_roundtrip(tmp_path, ds):
    rows = build_review(ds, [RawWin(2012, "東京優駿", "ディープブリランテ", "w")], [raw("ディープブリランテ", "ディープインパクト")])
    path = tmp_path / "review.csv"
    merge.write_review(rows, path)
    assert merge.read_review(path) == rows
