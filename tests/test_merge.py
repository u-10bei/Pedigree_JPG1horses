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


def raw(name, father=None, birth=None, alt=(), qid=None, father_qid=None):
    return RawHorse(name, tuple(alt), father, birth, f"wikidata:{qid}" if qid else "test", father_qid)


def by_kind(rows, kind):
    return [r for r in rows if r.Kind == kind]


def test_normalize():
    assert normalize("エルコンドルパサー (USA)") == normalize("エルコンドルパサー")
    assert normalize("Pharamond (1925)") != normalize("Pharamond")  # 同名の馬を区別する生年は残す
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


def test_birth_year_conflict_is_reported_as_check(ds):
    ds.horses[3] = Horse(3, "ディープインパクト", 2, 2002)
    rows = build_review(ds, [], [raw("ディープインパクト", "サンデーサイレンス", 2003)])
    checks = by_kind(rows, merge.KIND_CHECK)
    assert len(checks) == 1 and "生年" in checks[0].Note and checks[0].Approve == ""


def test_same_name_with_different_father_is_another_horse(ds):
    # 既存のディープインパクト（父 サンデーサイレンス）と同名だが父が Halo の馬
    rows = build_review(ds, [], [raw("ディープインパクト", "Halo", 1925, qid="Q1")])
    assert by_kind(rows, merge.KIND_BIRTH_YEAR) == []  # 既存の馬の生年にはしない
    check = by_kind(rows, merge.KIND_CHECK)[0]
    assert "同名の別の馬" in check.Note and check.Approve == ""


def test_same_name_ancestor_gets_birth_year_suffix(ds):
    # 新しい勝ち馬の父が、既存の馬と同名の別の馬
    rows = build_review(
        ds,
        [RawWin(2010, "東京優駿", "新しい馬", "w")],
        [
            raw("新しい馬", "ディープインパクト", 2007, qid="Q10", father_qid="Q11"),
            raw("ディープインパクト", "Halo", 1990, qid="Q11"),
        ],
    )
    horses = {r.Horse: r for r in by_kind(rows, merge.KIND_HORSE)}
    assert horses["新しい馬"].Father == "ディープインパクト (1990)"
    clash = horses["ディープインパクト (1990)"]
    assert clash.Father == "Halo" and "同名の既存の馬" in clash.Note and clash.Approve == ""


def test_wikidata_id_identifies_existing_horse(ds):
    ds.horses[3] = Horse(3, "ディープインパクト", 2, None, "Q730381")
    # 名前は違っても Q 番号が同じなら既存の馬
    rows = build_review(ds, [], [raw("Deep Impact", "サンデーサイレンス", 2002, qid="Q730381")])
    assert [(r.Horse, r.BirthYear) for r in by_kind(rows, merge.KIND_BIRTH_YEAR)] == [("ディープインパクト", "2002")]
    # 名前が同じでも Q 番号が違えば別の馬
    rows = build_review(ds, [], [raw("ディープインパクト", "サンデーサイレンス", 2002, qid="Q999")])
    assert by_kind(rows, merge.KIND_BIRTH_YEAR) == []


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


def test_birth_year_conflicting_with_wins_needs_review(ds):
    rows = build_review(ds, [], [raw("ディープインパクト", "サンデーサイレンス", 2004)])
    row = by_kind(rows, merge.KIND_BIRTH_YEAR)[0]
    assert row.Approve == "" and "勝利年" in row.Note


def test_apply_records_wikidata_id(ds):
    rows = [
        ReviewRow(Approve="y", Kind="horse", Horse="新馬", Father="Halo", Source="wikidata:Q5"),
        ReviewRow(Approve="y", Kind="birth_year", Horse="ディープインパクト", BirthYear="2002", Source="wikidata:Q730381"),
    ]
    result, _ = apply_review(ds, rows)
    names = result.by_name()
    assert names["新馬"].wikidata == "Q5"
    assert names["ディープインパクト"].wikidata == "Q730381"
