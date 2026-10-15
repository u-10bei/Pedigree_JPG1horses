"""確認画面（Streamlit）。

    python -m pedigree admin

staging/review.csv を一覧表示し、絞り込み・修正・承認・反映を行う。手動での追加もできる。
"""

from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path

import pandas as pd
import streamlit as st

from pedigree import io, merge
from pedigree.models import ORIGIN_ID
from pedigree.validate import validate

DATA_DIR = Path(os.environ.get("PEDIGREE_DATA_DIR", io.DATA_DIR))
STAGING_DIR = Path(os.environ.get("PEDIGREE_STAGING_DIR", merge.STAGING_DIR))
REVIEW_PATH = STAGING_DIR / merge.REVIEW_FILE

KIND_LABELS = {
    merge.KIND_HORSE: "新規馬",
    merge.KIND_BIRTH_YEAR: "生年",
    merge.KIND_WIN: "勝利",
    merge.KIND_CHECK: "参考",
}
KIND_CODES = {label: code for code, label in KIND_LABELS.items()}
EDITABLE = ["承認", "馬名", "父", "生年", "年", "レース"]
COLUMN_NAMES = {
    "Kind": "種別",
    "Ryear": "年",
    "Rtitle": "レース",
    "Horse": "馬名",
    "Father": "父",
    "BirthYear": "生年",
    "Note": "注記",
    "AltNames": "別表記",
}


def source_url(source: str) -> str | None:
    if source.startswith("wikidata:"):
        return f"https://www.wikidata.org/wiki/{source.split(':', 1)[1]}"
    if source.startswith("jawiki:") and source != "jawiki:":
        return f"https://ja.wikipedia.org/wiki/{source.split(':', 1)[1].replace(' ', '_')}"
    return None


def to_frame(rows: list[merge.ReviewRow]) -> pd.DataFrame:
    df = pd.DataFrame([vars(r) for r in rows], columns=merge.REVIEW_COLUMNS)
    df.insert(0, "承認", df["Approve"].str.casefold().isin(merge.APPROVED))
    df["Kind"] = df["Kind"].map(lambda k: KIND_LABELS.get(k, k))
    df["リンク"] = df["Source"].map(source_url)
    return df.drop(columns=["Approve"]).rename(columns=COLUMN_NAMES)


def to_rows(df: pd.DataFrame) -> list[merge.ReviewRow]:
    back = {v: k for k, v in COLUMN_NAMES.items()}
    rows = []
    for record in df.rename(columns=back).to_dict("records"):
        values = {f.name: "" if pd.isna(record.get(f.name)) else str(record.get(f.name, "")) for f in fields(merge.ReviewRow)}
        values["Kind"] = KIND_CODES.get(values["Kind"], values["Kind"])
        values["Approve"] = "y" if record["承認"] and values["Kind"] != merge.KIND_CHECK else ""
        rows.append(merge.ReviewRow(**values))
    return rows


def load_state() -> None:
    if "df" not in st.session_state:
        st.session_state.df = to_frame(merge.read_review(REVIEW_PATH))
        st.session_state.editor_version = 0


def reset_editor() -> None:
    st.session_state.editor_version += 1


def save_review() -> None:
    merge.write_review(to_rows(st.session_state.df), REVIEW_PATH)


def review_tab() -> None:
    df: pd.DataFrame = st.session_state.df
    if df.empty:
        st.info(f"{REVIEW_PATH} に確認する行がありません。`python -m pedigree review` で作成してください。")
        return

    with st.sidebar:
        st.header("絞り込み")
        kinds = st.multiselect("種別", list(KIND_CODES), default=list(KIND_CODES), on_change=reset_editor)
        only_notes = st.checkbox("要確認（注記あり）のみ", on_change=reset_editor)
        only_unapproved = st.checkbox("未承認のみ", on_change=reset_editor)
        query = st.text_input("馬名・父・レースで検索", on_change=reset_editor)

    mask = df["種別"].isin(kinds)
    if only_notes:
        mask &= df["注記"] != ""
    if only_unapproved:
        mask &= ~df["承認"]
    if query:
        mask &= df[["馬名", "父", "レース"]].apply(lambda col: col.str.contains(query, regex=False)).any(axis=1)
    view = df[mask]

    approved = int(df["承認"].sum())
    st.caption(f"全 {len(df)} 行（承認 {approved} / 未承認 {len(df) - approved}）・表示 {len(view)} 行")

    edited = st.data_editor(
        view,
        key=f"editor-{st.session_state.editor_version}",
        hide_index=True,
        width="stretch",
        height=560,
        disabled=[c for c in view.columns if c not in EDITABLE],
        column_order=["承認", "種別", "年", "レース", "馬名", "別表記", "父", "生年", "注記", "リンク"],
        column_config={
            "承認": st.column_config.CheckboxColumn(width="small"),
            "種別": st.column_config.TextColumn(width="small"),
            "年": st.column_config.TextColumn(width="small"),
            "生年": st.column_config.TextColumn(width="small"),
            "注記": st.column_config.TextColumn(width="large"),
            "リンク": st.column_config.LinkColumn(display_text="出典", width="small"),
        },
    )
    df.loc[edited.index, EDITABLE] = edited[EDITABLE]

    col1, col2, col3, col4 = st.columns(4)
    if col1.button("表示中をすべて承認", width="stretch"):
        df.loc[view.index[view["種別"] != KIND_LABELS[merge.KIND_CHECK]], "承認"] = True
        reset_editor()
        st.rerun()
    if col2.button("表示中の承認を外す", width="stretch"):
        df.loc[view.index, "承認"] = False
        reset_editor()
        st.rerun()
    if col3.button("保存", type="secondary", width="stretch"):
        save_review()
        st.success(f"{REVIEW_PATH} に保存しました")
    if col4.button("検証して data/ に反映", type="primary", width="stretch"):
        apply(dry_run=False)

    if st.button("検証だけする（反映しない）"):
        apply(dry_run=True)


def apply(dry_run: bool) -> None:
    rows = to_rows(st.session_state.df)
    try:
        result, counts = merge.apply_review(io.load(DATA_DIR), rows)
    except merge.ApplyError as e:
        st.error(f"エラーが {len(e.problems)} 件あります。data/ は変更していません。")
        st.dataframe(pd.DataFrame({"エラー": [str(p) for p in e.problems]}), hide_index=True, width="stretch")
        return
    summary = f"新規馬 {counts['horse']} / 生年 {counts['birth_year']} / 勝利 {counts['win']}"
    if dry_run:
        st.success(f"検証に通りました（{summary}）")
        return
    io.save(result, DATA_DIR)
    remaining = merge.remaining_rows(rows)
    merge.write_review(remaining, REVIEW_PATH)
    st.session_state.df = to_frame(remaining)
    reset_editor()
    st.success(f"data/ に反映しました（{summary}）。反映した行は確認一覧から外しました。")


def known_names() -> list[str]:
    ds = io.load(DATA_DIR)
    df: pd.DataFrame = st.session_state.df
    pending = df.loc[df["種別"] == KIND_LABELS[merge.KIND_HORSE], "馬名"].tolist()
    return sorted({h.name for h in ds.horses.values() if h.id != ORIGIN_ID} | set(pending))


def unresolved_horses() -> list[str]:
    """確認一覧にある新規馬のうち、まだ既存の馬につながっていないもの（注記あり）。"""
    df: pd.DataFrame = st.session_state.df
    rows = df[(df["種別"] == KIND_LABELS[merge.KIND_HORSE]) & ~df["注記"].isin(["", "手動追加", "手動で修正"])]
    return rows["馬名"].tolist()


def submit_horse() -> None:
    """「馬を追加」の送信。父が未登録なら、続けてその父を入力できるようにする。"""
    state = st.session_state
    name = (state.get("new_name") or "").strip()
    father = (state.get("new_father") or "").strip()
    birth = (state.get("new_birth") or "").strip()
    if not name or not father:
        state.manual_msg = ("error", "馬名と父を入力してください")
        return
    if birth and not birth.isdigit():
        state.manual_msg = ("error", "生年は数字で入力してください")
        return

    # 父が確認一覧にあっても、まだ既存の馬につながっていなければ続けて入力してもらう
    father_known = father in known_names() and merge.normalize(father) not in {
        merge.normalize(n) for n in unresolved_horses()
    }
    upsert_horse(name, father, birth)
    if father_known:
        state.manual_msg = ("success", f"{name}（父 {father}）を追加しました")
        state.new_name = ""
    else:
        state.manual_msg = ("info", f"{name}（父 {father}）を追加しました。父「{father}」は未登録です。続けて {father} の父を入力してください。")
        state.new_name = father
    state.new_father = None
    state.new_birth = ""


def upsert_horse(name: str, father: str, birth: str) -> None:
    """確認一覧に同じ馬の新規行があれば更新し、なければ追加する。"""
    df: pd.DataFrame = st.session_state.df
    same = df.index[(df["種別"] == KIND_LABELS[merge.KIND_HORSE]) & (df["馬名"].map(merge.normalize) == merge.normalize(name))]
    if len(same):
        df.loc[same, ["父", "承認", "注記"]] = [father, True, "手動で修正"]
        if birth:
            df.loc[same, "生年"] = birth
        save_review()
        reset_editor()
    else:
        add_row(merge.ReviewRow(Approve="y", Kind=merge.KIND_HORSE, Horse=name, Father=father, BirthYear=birth, Note="手動追加"))


def manual_tab() -> None:
    ds = io.load(DATA_DIR)
    names = known_names()

    st.write("追加した行は確認一覧に「承認済み」で入ります。反映は「確認」タブから行ってください。")
    left, right = st.columns(2)
    with left:
        st.subheader("馬を追加")
        st.caption("父が未登録の場合は新しい名前を入力できます。その場合、続けてその父を入力するよう案内します（既存の馬につながるまで繰り返せます）。")
        unresolved = unresolved_horses()
        if unresolved:
            pick = st.selectbox(
                "まだ既存の馬につながっていない馬から選ぶ",
                unresolved,
                index=None,
                placeholder=f"{len(unresolved)} 頭（選ぶと下の馬名に入ります）",
                key="pick_unresolved",
            )
            if pick and st.session_state.get("new_name") != pick and st.session_state.get("_picked") != pick:
                st.session_state.new_name = pick
                st.session_state._picked = pick
        message = st.session_state.pop("manual_msg", None)
        if message:
            getattr(st, message[0])(message[1])
        with st.form("add-horse"):
            st.text_input("馬名", key="new_name")
            typed = st.session_state.get("new_father")
            options = names + [typed] if typed and typed not in names else names
            st.selectbox("父", options, index=None, placeholder="名前を入力して選択（新しい名前も可）", accept_new_options=True, key="new_father")
            st.text_input("生年（空欄可）", key="new_birth")
            st.form_submit_button("追加", on_click=submit_horse)

    with right, st.form("add-win", clear_on_submit=True):
        st.subheader("勝利を追加")
        year = st.number_input("年", min_value=1932, max_value=2100, value=None, step=1)
        race = st.selectbox("レース", sorted(ds.races), index=None, placeholder="選択")
        horse = st.selectbox("勝ち馬", names, index=None, placeholder="名前を入力して選択")
        if st.form_submit_button("追加"):
            if year is None or not race or not horse:
                st.error("年・レース・勝ち馬を入力してください")
            else:
                add_row(merge.ReviewRow(Approve="y", Kind=merge.KIND_WIN, Ryear=str(int(year)), Rtitle=race, Horse=horse, Note="手動追加"))
                st.success(f"{int(year)} {race}：{horse} を追加しました")


def add_row(row: merge.ReviewRow) -> None:
    st.session_state.df = pd.concat([st.session_state.df, to_frame([row])], ignore_index=True)
    save_review()
    reset_editor()


def data_tab() -> None:
    ds = io.load(DATA_DIR)
    issues = validate(ds)
    horses = len(ds.horses) - 1
    blank = sum(1 for h in ds.horses.values() if h.birth_year is None and h.id != ORIGIN_ID)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("馬", horses)
    c2.metric("勝利", len(ds.wins))
    c3.metric("生年未入力", blank)
    c4.metric("検証エラー", len(issues))
    for issue in issues:
        st.error(str(issue))
    last_year = max((w.year for w in ds.wins), default=None)
    st.write(f"勝利の最新年：{last_year}")


def main() -> None:
    st.set_page_config(page_title="血統データの確認", layout="wide")
    st.title("血統データの確認")
    load_state()
    tab_review, tab_manual, tab_data = st.tabs(["確認", "手動追加", "データ"])
    with tab_review:
        review_tab()
    with tab_manual:
        manual_tab()
    with tab_data:
        data_tab()


main()
