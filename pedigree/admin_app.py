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

from pedigree import births, io, merge
from pedigree.lines import assign_lines
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
EDITABLE = ["承認", "馬名", "父", "生年", "年", "レース", "外す"]
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
    df["外す"] = False  # 画面上だけの列（一覧から外す行の印）
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
        column_order=["承認", "外す", "種別", "年", "レース", "馬名", "別表記", "父", "生年", "注記", "リンク"],
        column_config={
            "承認": st.column_config.CheckboxColumn(width="small"),
            "種別": st.column_config.TextColumn(width="small"),
            "年": st.column_config.TextColumn(width="small"),
            "生年": st.column_config.TextColumn(width="small"),
            "注記": st.column_config.TextColumn(width="large"),
            "リンク": st.column_config.LinkColumn(display_text="出典", width="small"),
            "外す": st.column_config.CheckboxColumn(width="small", help="チェックして下のボタンを押すと、確認一覧から外します"),
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

    col5, col6 = st.columns(2)
    if col5.button("検証だけする（反映しない）", width="stretch"):
        apply(dry_run=True)
    marked = int(df["外す"].sum())
    if col6.button(f"「外す」にチェックした行を一覧から外す（{marked} 行）", width="stretch", disabled=not marked):
        st.session_state.df = df[~df["外す"]]
        save_review()
        reset_editor()
        st.rerun()


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

    registered = registered_horse(name)
    if registered is not None:
        add_registered_birth_year(registered, father, birth)
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


def registered_horse(name: str):
    """data/ に登録済みの同じ名前の馬。"""
    key = merge.normalize(name)
    return next((h for h in io.load(DATA_DIR).horses.values() if merge.normalize(h.name) == key), None)


def add_registered_birth_year(horse, father: str, birth: str) -> None:
    """登録済みの馬を「馬を追加」で入力したとき。新規行は作らず、生年だけ受け付ける。"""
    state = st.session_state
    ds = io.load(DATA_DIR)
    current_father = ds.horses[horse.father_id].name
    note = "" if merge.normalize(father) == merge.normalize(current_father) else f"（登録済みの父は {current_father} です。父は変更していません）"
    if birth and str(horse.birth_year or "") != birth:
        df: pd.DataFrame = state.df
        same = df.index[(df["種別"] == KIND_LABELS[merge.KIND_BIRTH_YEAR]) & (df["馬名"] == horse.name)]
        if len(same):
            df.loc[same, ["生年", "承認", "注記"]] = [birth, True, "手動で修正"]
            save_review()
            reset_editor()
        else:
            add_row(merge.ReviewRow(Approve="y", Kind=merge.KIND_BIRTH_YEAR, Horse=horse.name, BirthYear=birth, Note="手動追加"))
        state.manual_msg = ("success", f"{horse.name} は登録済みのため、生年 {birth} を設定する行を追加しました{note}")
    else:
        state.manual_msg = ("warning", f"{horse.name} はすでに登録されています。追加しませんでした{note}")
    state.new_name = ""
    state.new_father = None
    state.new_birth = ""


def submit_win() -> None:
    """「勝利を追加」の送信。登録済み・確認一覧にある勝利は二重に追加しない。"""
    state = st.session_state
    year, race, horse = state.get("win_year"), state.get("win_race"), state.get("win_horse")
    if year is None or not race or not horse:
        state.win_msg = ("error", "年・レース・勝ち馬を入力してください")
        return
    year = int(year)
    label = f"{year} {race}：{horse}"
    ds = io.load(DATA_DIR)
    names = ds.by_name()
    if horse in names and any(w.year == year and w.race == race and w.winner_id == names[horse].id for w in ds.wins):
        state.win_msg = ("warning", f"{label} はすでに登録されています。追加しませんでした")
        return
    df: pd.DataFrame = state.df
    same = df.index[
        (df["種別"] == KIND_LABELS[merge.KIND_WIN]) & (df["年"] == str(year)) & (df["レース"] == race) & (df["馬名"] == horse)
    ]
    if len(same):
        df.loc[same, "承認"] = True
        save_review()
        reset_editor()
        state.win_msg = ("success", f"{label} は確認一覧にあったので、その行を承認済みにしました")
    else:
        add_row(merge.ReviewRow(Approve="y", Kind=merge.KIND_WIN, Ryear=str(year), Rtitle=race, Horse=horse, Note="手動追加"))
        state.win_msg = ("success", f"{label} を追加しました")
    state.win_year, state.win_race, state.win_horse = None, None, None


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

    with right:
        st.subheader("勝利を追加")
        message = st.session_state.pop("win_msg", None)
        if message:
            getattr(st, message[0])(message[1])
        with st.form("add-win"):
            st.number_input("年", min_value=1932, max_value=2100, value=None, step=1, key="win_year")
            st.selectbox("レース", sorted(ds.races), index=None, placeholder="選択", key="win_race")
            st.selectbox("勝ち馬", names, index=None, placeholder="名前を入力して選択", key="win_horse")
            st.form_submit_button("追加", on_click=submit_win)


def add_row(row: merge.ReviewRow) -> None:
    st.session_state.df = pd.concat([st.session_state.df, to_frame([row])], ignore_index=True)
    save_review()
    reset_editor()


def birth_rows(ds) -> pd.DataFrame:
    """生年が空欄の馬の一覧（同じ父系の馬が続けて並ぶ順）。父・子の生年や初勝利から、ありうる生年の範囲を目安として出す。"""
    df: pd.DataFrame = st.session_state.df
    is_year = df["種別"] == KIND_LABELS[merge.KIND_BIRTH_YEAR]
    pending = dict(zip(df.loc[is_year, "馬名"], df.loc[is_year, "生年"]))
    children = ds.children()
    lines = assign_lines(ds)
    first_win: dict[int, tuple[int, str]] = {}
    for w in sorted(ds.wins, key=lambda w: w.year):
        first_win.setdefault(w.winner_id, (w.year, w.race))
    records = []
    for horse_id in births.lineage_order(ds):
        h = ds.horses[horse_id]
        if h.id == ORIGIN_ID or h.birth_year is not None:
            continue
        father = ds.horses[h.father_id]
        kid_years = [ds.horses[c].birth_year for c in children.get(h.id, []) if ds.horses[c].birth_year]
        low = father.birth_year + 3 if father.birth_year else None
        highs = [min(kid_years) - 3] if kid_years else []
        if h.id in first_win:
            highs.append(first_win[h.id][0] - 2)
        high = min(highs) if highs else None
        line = lines.get(h.id)
        records.append(
            {
                "系統": line.name if line else "",
                "馬名": h.name,
                "父": father.name if father.id != ORIGIN_ID else "",
                "父の生年": father.birth_year or "",
                "初勝利": f"{first_win[h.id][0]} {first_win[h.id][1]}" if h.id in first_win else "",
                "目安": f"{low or '?'}〜{high or '?'}" if (low or high) else "",
                "確認一覧の値": pending.get(h.name, ""),
                "生年": "",
            }
        )
    return pd.DataFrame(records)


def add_birth_years(entries: list[tuple[str, str]]) -> None:
    """(馬名, 生年) を確認一覧に生年の行として追加する（同じ馬の生年の行があれば更新）。"""
    for name, year in entries:
        df: pd.DataFrame = st.session_state.df
        same = df.index[(df["種別"] == KIND_LABELS[merge.KIND_BIRTH_YEAR]) & (df["馬名"] == name)]
        if len(same):
            df.loc[same, ["生年", "承認", "注記"]] = [year, True, "手動入力"]
        else:
            row = merge.ReviewRow(Approve="y", Kind=merge.KIND_BIRTH_YEAR, Horse=name, BirthYear=year, Note="手動入力")
            st.session_state.df = pd.concat([df, to_frame([row])], ignore_index=True)
    save_review()
    reset_editor()


def paste_section(ds) -> None:
    st.subheader("まとめて貼り付け")
    st.caption("1 行に 1 頭、「馬名 生年」の形で貼り付けてください（区切りはタブ・空白・カンマなど。「Eclipse（1764）」も可）。カナ・英字のどちらの表記でも探します。")
    text = st.text_area("貼り付け", key="paste_births", height=140, label_visibility="collapsed")
    if not text.strip():
        return
    aliases = births.load_aliases(ds, STAGING_DIR / merge.HORSES_RAW_FILE)
    parsed = births.parse_pasted(text, ds, aliases)
    table = birth_rows(ds).set_index("馬名")
    preview = []
    for p in parsed:
        note = p.note
        if not note and p.horse in table.index:
            hint = table.loc[p.horse, "目安"]
            low, _, high = str(hint).partition("〜")
            if (low.isdigit() and p.year < int(low)) or (high.isdigit() and p.year > int(high)):
                note = f"目安（{hint}）の範囲外です"
        preview.append({"貼り付けた行": p.text, "対応する馬": p.horse or "", "生年": p.year or "", "注意": note})
    st.dataframe(pd.DataFrame(preview), hide_index=True, width="stretch")
    ok = [(p.horse, str(p.year)) for p in parsed if p.horse and p.year and not p.note]
    if st.button(f"対応できた {len(ok)} 頭を確認一覧に追加", type="primary", disabled=not ok, key="paste_add"):
        add_birth_years(ok)
        st.session_state.births_msg = f"{len(ok)} 頭の生年を確認一覧に追加しました（「目安の範囲外」の行も含みます。確認タブで確かめてください）。"
        del st.session_state["paste_births"]
        st.rerun()


def births_tab() -> None:
    ds = io.load(DATA_DIR)
    message = st.session_state.pop("births_msg", None)
    if message:
        st.success(message)
    st.write(
        "data/ で生年が空欄の馬です。貼り付けるか、一覧の「生年」に入力して確認一覧に追加してください"
        "（反映は「確認」タブから）。「目安」は父の生年＋3 年から、子の生年－3 年・初勝利－2 年までの範囲です。"
    )
    st.caption("自動で埋められる分は、先に `python -m pedigree births` を実行すると確認一覧に入ります。")
    paste_section(ds)

    st.subheader("一覧から入力")
    table = birth_rows(ds)
    if table.empty:
        st.success("生年が空欄の馬はいません")
        return
    left, right = st.columns(2)
    only_new = left.checkbox("確認一覧にまだ生年の行がない馬だけ表示", value=True)
    line = right.selectbox("系統で絞り込む", ["すべて", *sorted({x for x in table["系統"] if x})])
    view = table[table["確認一覧の値"] == ""] if only_new else table
    if line != "すべて":
        view = view[view["系統"] == line]
    st.caption(f"空欄 {len(table)} 頭（確認一覧に生年の行あり {int((table['確認一覧の値'] != '').sum())} 頭）・表示 {len(view)} 頭（同じ父系の馬が続けて並びます）")
    edited = st.data_editor(
        view,
        key=f"births-{st.session_state.editor_version}-{only_new}-{line}",
        hide_index=True,
        width="stretch",
        height=520,
        disabled=[c for c in view.columns if c != "生年"],
        column_config={"生年": st.column_config.TextColumn(help="4 桁の西暦（例：1957）")},
    )
    entered = edited[edited["生年"].astype(str).str.strip() != ""]
    if st.button(f"入力した生年を確認一覧に追加（{len(entered)} 頭）", type="primary", disabled=entered.empty):
        bad = [n for n, y in zip(entered["馬名"], entered["生年"]) if not str(y).strip().isdigit() or len(str(y).strip()) != 4]
        if bad:
            st.error(f"生年は 4 桁の数字で入力してください：{'、'.join(bad)}")
            return
        add_birth_years([(n, str(y).strip()) for n, y in zip(entered["馬名"], entered["生年"])])
        st.session_state.births_msg = f"{len(entered)} 頭の生年を確認一覧に追加しました。「確認」タブで反映してください。"
        st.rerun()


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
    tab_review, tab_manual, tab_births, tab_data = st.tabs(["確認", "手動追加", "生年の入力", "データ"])
    with tab_review:
        review_tab()
    with tab_manual:
        manual_tab()
    with tab_births:
        births_tab()
    with tab_data:
        data_tab()


main()
