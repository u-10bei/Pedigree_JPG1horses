import shutil
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from pedigree import io, merge  # noqa: E402
from pedigree.merge import ReviewRow  # noqa: E402

APP = str(Path(io.__file__).with_name("admin_app.py"))


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    data, staging = tmp_path / "data", tmp_path / "staging"
    shutil.copytree(io.DATA_DIR, data)
    staging.mkdir()
    merge.write_review(
        [
            ReviewRow(Approve="y", Kind="horse", Horse="テスト馬", Father="ディープインパクト", BirthYear="2020"),
            ReviewRow(Approve="y", Kind="win", Ryear="2024", Rtitle="東京優駿", Horse="テスト馬"),
            ReviewRow(Approve="", Kind="horse", Horse="保留馬", Father="不明", Note="父が取得できていません"),
            ReviewRow(Kind="check", Horse="ディープインパクト", Note="参考"),
        ],
        staging / merge.REVIEW_FILE,
    )
    monkeypatch.setenv("PEDIGREE_DATA_DIR", str(data))
    monkeypatch.setenv("PEDIGREE_STAGING_DIR", str(staging))
    return data, staging


def button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def test_review_rows_are_listed(dirs):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert "全 4 行（承認 2 / 未承認 2）" in at.caption[0].value


def test_dry_run_and_apply(dirs):
    data, staging = dirs
    at = AppTest.from_file(APP, default_timeout=30).run()
    button(at, "検証だけする（反映しない）").click().run()
    assert any("検証に通りました" in s.value for s in at.success)
    assert "テスト馬" not in io.load(data).by_name()

    button(at, "検証して data/ に反映").click().run()
    assert not at.exception
    ds = io.load(data)
    horse = ds.by_name()["テスト馬"]
    assert any(w.winner_id == horse.id and w.year == 2024 for w in ds.wins)
    remaining = merge.read_review(staging / merge.REVIEW_FILE)
    assert [r.Horse for r in remaining] == ["保留馬", "ディープインパクト"]


def test_apply_errors_leave_data_unchanged(dirs):
    data, staging = dirs
    rows = merge.read_review(staging / merge.REVIEW_FILE)
    rows[2].Approve = "y"  # 父が登録されていない馬を承認
    merge.write_review(rows, staging / merge.REVIEW_FILE)
    before = (data / "pedigree.csv").read_text(encoding="utf-8")

    at = AppTest.from_file(APP, default_timeout=30).run()
    button(at, "検証して data/ に反映").click().run()
    assert any("エラーが" in e.value for e in at.error)
    assert (data / "pedigree.csv").read_text(encoding="utf-8") == before


def submit_horse(at: AppTest, name: str | None, father: str) -> AppTest:
    if name is not None:
        next(t for t in at.text_input if t.label == "馬名").input(name)
    next(s for s in at.selectbox if s.label == "父").set_value(father)
    return next(b for b in at.button if b.label == "追加").click().run()


def test_manual_add_horse(dirs):
    _, staging = dirs
    at = AppTest.from_file(APP, default_timeout=30).run()
    submit_horse(at, "手動の馬", "サンデーサイレンス")
    assert not at.exception
    rows = merge.read_review(staging / merge.REVIEW_FILE)
    assert rows[-1] == ReviewRow(Approve="y", Kind="horse", Horse="手動の馬", Father="サンデーサイレンス", Note="手動追加")


def test_manual_add_climbs_unregistered_fathers(dirs):
    data, staging = dirs
    at = AppTest.from_file(APP, default_timeout=30)
    # 一覧にない新しい名前は AppTest の selectbox で入力できないので、最初の描画の前に状態を設定する
    at.session_state["new_name"] = "子馬"
    at.session_state["new_father"] = "未登録の父"
    at.run()
    next(b for b in at.button if b.label == "追加").click().run()
    assert any("続けて 未登録の父 の父を入力" in i.value for i in at.info)
    assert next(t for t in at.text_input if t.label == "馬名").value == "未登録の父"

    submit_horse(at, None, "サンデーサイレンス")  # 馬名は案内で入力済み
    rows = {r.Horse: r for r in merge.read_review(staging / merge.REVIEW_FILE)}
    assert rows["子馬"].Father == "未登録の父"
    assert rows["未登録の父"].Father == "サンデーサイレンス"

    button(at, "検証して data/ に反映").click().run()
    names = io.load(data).by_name()
    assert names["子馬"].father_id == names["未登録の父"].id


def test_manual_add_updates_existing_review_row(dirs):
    _, staging = dirs
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(s for s in at.selectbox if s.label == "まだ既存の馬につながっていない馬から選ぶ").set_value("保留馬").run()
    assert next(t for t in at.text_input if t.label == "馬名").value == "保留馬"
    submit_horse(at, None, "Halo")
    rows = [r for r in merge.read_review(staging / merge.REVIEW_FILE) if r.Horse == "保留馬"]
    assert len(rows) == 1
    assert (rows[0].Father, rows[0].Approve, rows[0].Note) == ("Halo", "y", "手動で修正")


def test_manual_add_continues_with_unresolved_father_in_review(dirs):
    at = AppTest.from_file(APP, default_timeout=30).run()
    submit_horse(at, "保留馬の子", "保留馬")  # 保留馬は確認一覧にあるが、まだ父が不明
    assert any("続けて 保留馬 の父を入力" in i.value for i in at.info)
