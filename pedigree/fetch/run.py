"""取得処理の本体。結果を staging/ の CSV に書き出す。"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from ..merge import HORSES_RAW_FILE, WINNERS_RAW_FILE, RawWin, normalize
from ..models import ORIGIN_ID, Dataset
from .client import Client
from .wikidata import Entity, Wikidata
from .wikipedia import parse_infobox_father, parse_winners

JAWIKI = "jawiki:"
WIKIDATA = "wikidata:"
MAX_DEPTH = 40
# この日本語版 Wikipedia のカテゴリに入っている馬は、日本で登録された馬としてカナで表記する
JAPAN_CATEGORIES = ["日本供用種牡馬", "日本調教の競走馬"]

_TRAILING_PAREN = re.compile(r"\s*[(（][^()（）]*[)）]$")


def clean_name(name: str) -> str:
    return _TRAILING_PAREN.sub("", name).strip()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# --- 勝ち馬 -------------------------------------------------------------


def fetch_winners(ds: Dataset, client: Client, year_from: int, year_to: int) -> list[RawWin]:
    found: list[tuple[str, int, str, str | None]] = []
    for race in ds.races.values():
        cells = parse_winners(client.wikipedia_html(race.article))
        if not cells:
            log(f"警告: {race.article} から歴代優勝馬の表を読み取れませんでした")
        for cell in cells:
            if year_from <= cell.year <= year_to and race.held_in(cell.year):
                found.append((race.name, cell.year, cell.name, cell.title))
        log(f"{race.name}: {sum(1 for f in found if f[0] == race.name)} 件")

    # Wikipedia は同じ馬へのリンクを最初の 1 回しか張らないことが多いので、他の行の記事名で補う
    titles = {normalize(name): title for _, _, name, title in found if title}
    return [
        RawWin(year, race, name, JAWIKI + (title or titles.get(normalize(name), "")))
        for race, year, name, title in found
    ]


def write_winners(rows: list[RawWin], staging_dir: Path) -> Path:
    path = staging_dir / WINNERS_RAW_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["Ryear", "Rtitle", "Horse", "Source"])
        for w in sorted(rows, key=lambda w: (w.year, w.race, w.horse)):
            writer.writerow([w.year, w.race, w.horse, w.source])
    return path


# --- 馬（父・生年） -----------------------------------------------------


class HorseResolver:
    """馬名から Wikidata のエンティティを探す。"""

    # (サイト, 記事名の作り方) を順に試す
    VARIANTS = (
        ("jawiki", lambda n: f"{n} (競走馬)"),
        ("jawiki", lambda n: n),
        ("enwiki", lambda n: f"{n} (horse)"),
        ("enwiki", lambda n: n),
    )

    def __init__(self, wikidata: Wikidata):
        self.wikidata = wikidata

    def resolve(self, requests: dict[str, str | None]) -> dict[str, Entity]:
        """馬名 → エンティティ。requests は 馬名 → 既知の日本語版記事名（なければ None）。"""
        found: dict[str, Entity] = {}

        known = {name: title for name, title in requests.items() if title}
        if known:
            self._try(known, "jawiki", found)
        for site, make in self.VARIANTS:
            pending = {name: make(clean_name(name)) for name in requests if name not in found}
            if not pending:
                break
            self._try(pending, site, found)
        return found

    def _try(self, titles: dict[str, str], site: str, found: dict[str, Entity]) -> None:
        results = self.wikidata.by_titles(list(titles.values()), site)
        by_title = {normalize(t): e for t, e in results if t}
        by_name: dict[str, list[Entity]] = {}
        for _, e in results:
            for n in e.names:
                by_name.setdefault(normalize(n), []).append(e)
        for name, title in titles.items():
            entity = by_title.get(normalize(title))
            if entity is None:
                # リダイレクトで記事名が変わった場合は名前で照合する（同名が複数なら採用しない）
                candidates = {e.qid: e for e in by_name.get(normalize(name), [])}
                if len(candidates) == 1:
                    entity = next(iter(candidates.values()))
            if entity is not None:
                found[name] = entity


def display_name(entity: Entity, fallback: str) -> str:
    return clean_name(entity.ja or entity.en or fallback)


def fetch_horses(
    ds: Dataset,
    client: Client,
    raw_wins: list[RawWin],
    include_existing: bool = True,
) -> list[dict[str, str]]:
    wikidata = Wikidata(client)
    resolver = HorseResolver(wikidata)

    existing_names = {normalize(h.name): h for h in ds.horses.values() if h.id != ORIGIN_ID}

    def existing_for(entity: Entity):
        for n in entity.names:
            hit = existing_names.get(normalize(n))
            if hit is not None:
                return hit
        return None

    # 1. 未登録の勝ち馬
    new_winners: dict[str, str | None] = {}
    for w in raw_wins:
        if normalize(w.horse) not in existing_names:
            title = w.source[len(JAWIKI) :] if w.source.startswith(JAWIKI) else ""
            new_winners.setdefault(w.horse, title or None)
    log(f"未登録の勝ち馬: {len(new_winners)} 頭")
    winners = resolver.resolve(new_winners)
    log(f"  Wikidata で見つかった馬: {len(winners)} 頭")

    rows: dict[str, dict[str, str]] = {}  # qid → 行
    entities: dict[str, Entity] = {}  # qid → エンティティ（新規の馬）
    father_of: dict[str, str] = {}  # 子の qid → 父の qid

    def add_row(entity: Entity, name: str, extra_names: tuple[str, ...] = ()) -> None:
        entities[entity.qid] = entity
        alt = [n for n in dict.fromkeys((*entity.names, *extra_names)) if n != name]
        rows[entity.qid] = {
            "Horse": name,
            "AltNames": "|".join(alt),
            "Father": "",
            "FatherQid": "",
            "BirthYear": str(entity.birth_year or ""),
            "Source": WIKIDATA + entity.qid,
        }

    def father_from_infobox(child: Entity) -> Entity | str | None:
        """情報欄の父。Wikidata で見つかればエンティティ、名前しか分からなければ既存名または馬名。"""
        info = None
        for lang, title in (("ja", child.jawiki), ("en", child.enwiki)):
            if title:
                info = parse_infobox_father(client.wikipedia_html(title, lang))
                if info is not None:
                    break
        if info is None:
            return None
        name, title = info
        hit = existing_names.get(normalize(name))
        if hit is not None:
            return hit.name
        site = "jawiki" if lang == "ja" else "enwiki"
        if title:
            for found_title, entity in wikidata.by_titles([title], site):
                if normalize(found_title or "") == normalize(title) or normalize(name) in map(normalize, entity.names):
                    return entity
        # 記事へのリンクがない場合は、名前で Wikidata を探す
        found = resolver.resolve({name: None})
        return found.get(name) or clean_name(name)

    # 2. 父をたどって既存の馬につながるまで登録する
    frontier: list[Entity] = []
    for name, entity in winners.items():
        add_row(entity, display_name(entity, name), (name,))
        frontier.append(entity)

    names_by_qid: dict[str, str] = {}
    for depth in range(MAX_DEPTH):
        fathers = wikidata.by_ids([e.father for e in frontier if e.father])
        next_frontier = []
        for child in frontier:
            if child.father:
                father = fathers.get(child.father)
            else:
                # Wikidata に父がない場合は、日本語版 Wikipedia の情報欄で補う
                father = father_from_infobox(child)
                if isinstance(father, str):
                    rows[child.qid]["Father"] = father
                    continue
            if father is None:
                continue
            father_of[child.qid] = father.qid
            rows[child.qid]["FatherQid"] = father.qid
            hit = existing_for(father)
            if hit is not None:
                names_by_qid[father.qid] = hit.name
            elif father.qid not in rows:
                add_row(father, display_name(father, father.qid))
                next_frontier.append(father)
            rows[child.qid]["Father"] = names_by_qid.get(father.qid, rows.get(father.qid, {}).get("Horse", ""))
        if not next_frontier:
            break
        log(f"  祖先 {depth + 1} 代目: 新規 {len(next_frontier)} 頭")
        frontier = next_frontier

    # 3. 表記：日本で登録された馬（日本の G1 勝ち馬、日本で供用された種牡馬、日本で調教された競走馬）は
    #    カナ、それ以外は英字。種牡馬・競走馬かどうかは日本語版 Wikipedia のカテゴリで判定する
    winner_qids = {e.qid for e in winners.values()}
    ancestors = {qid: e for qid, e in entities.items() if qid not in winner_qids}
    categories = client.jawiki_categories([e.jawiki for e in ancestors.values() if e.jawiki], JAPAN_CATEGORIES)
    renamed: dict[str, str] = {}
    for qid, entity in ancestors.items():
        registered = bool(entity.jawiki and categories.get(entity.jawiki))
        name = display_name(entity, qid) if registered else clean_name(entity.en or entity.ja or qid)
        old = rows[qid]["Horse"]
        if name != old:
            alt = [n for n in dict.fromkeys((old, *rows[qid]["AltNames"].split("|"))) if n and n != name]
            rows[qid]["Horse"], rows[qid]["AltNames"] = name, "|".join(alt)
            renamed[old] = name
    for row in rows.values():
        row["Father"] = renamed.get(row["Father"], row["Father"])
    katakana = sum(1 for qid in ancestors if not rows[qid]["Horse"].isascii())
    log(f"表記：カナ {katakana} 頭 / 英字 {len(ancestors) - katakana} 頭")

    # 4. 既存の馬の生年（と父の照合用の情報）
    #    Q 番号が分かっている馬はそれで引く。名前で引いた馬は父が既存データと合うか確かめ、
    #    合わなければ同名の別の馬を検索して、父が合うものを使う（なければ使わない）。
    if include_existing:
        known = {h.name: h.wikidata for h in ds.horses.values() if h.id != ORIGIN_ID and h.wikidata}
        by_qid = wikidata.by_ids(list(known.values()))
        found: dict[str, Entity] = {name: by_qid[q] for name, q in known.items() if by_qid.get(q)}
        targets = {h.name: None for h in ds.horses.values() if h.id != ORIGIN_ID and h.name not in known}
        log(f"既存の馬の生年を検索: {len(targets)} 頭（Q 番号で取得 {len(found)} 頭）")
        by_name = resolver.resolve(targets)
        by_name_horse = {h.name: h for h in ds.horses.values()}

        def father_matches(horse, entity: Entity, fathers: dict[str, Entity | None]) -> bool | None:
            expected = ds.horses.get(horse.father_id)
            if expected is None or expected.id == ORIGIN_ID or not entity.father:
                return None  # 照合できない
            father = fathers.get(entity.father)
            return father is not None and normalize(expected.name) in map(normalize, father.names)

        fathers = wikidata.by_ids([e.father for e in by_name.values() if e.father])
        replaced = 0
        for name, entity in by_name.items():
            horse = by_name_horse[name]
            if father_matches(horse, entity, fathers) is False:
                candidates = [c for c in wikidata.search(clean_name(name)) if c.qid != entity.qid]
                cand_fathers = wikidata.by_ids([c.father for c in candidates if c.father])
                good = [c for c in candidates if father_matches(horse, c, cand_fathers)]
                if len(good) == 1:
                    entity = good[0]
                    fathers.update(cand_fathers)
                    replaced += 1
            found[name] = entity
        log(f"  Wikidata で見つかった馬: {len(found)} 頭（同名の別の馬から選び直し {replaced} 頭）")

        fathers.update(wikidata.by_ids([e.father for e in found.values() if e.father and e.father not in fathers]))
        for name, entity in found.items():
            if entity.qid in rows:
                continue
            add_row(entity, name)
            father = fathers.get(entity.father) if entity.father else None
            if father is not None:
                hit = existing_for(father)
                rows[entity.qid]["Father"] = hit.name if hit else display_name(father, father.qid)
                rows[entity.qid]["FatherQid"] = father.qid

    # 父の行を先に（確認しやすいよう、名前順）
    return sorted(rows.values(), key=lambda r: r["Horse"])


def write_horses(rows: list[dict[str, str]], staging_dir: Path) -> Path:
    path = staging_dir / HORSES_RAW_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Horse", "AltNames", "Father", "FatherQid", "BirthYear", "Source"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path
