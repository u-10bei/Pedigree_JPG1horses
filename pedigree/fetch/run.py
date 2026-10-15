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
from .wikipedia import parse_winners

JAWIKI = "jawiki:"
WIKIDATA = "wikidata:"
MAX_DEPTH = 40

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

    def add_row(entity: Entity, name: str, extra_names: tuple[str, ...] = ()) -> None:
        alt = [n for n in dict.fromkeys((*entity.names, *extra_names)) if n != name]
        rows[entity.qid] = {
            "Horse": name,
            "AltNames": "|".join(alt),
            "Father": "",
            "BirthYear": str(entity.birth_year or ""),
            "Source": WIKIDATA + entity.qid,
        }

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
            if not child.father:
                continue
            father = fathers.get(child.father)
            if father is None:
                continue
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

    # 3. 既存の馬の生年（と父の照合用の情報）
    if include_existing:
        targets = {h.name: None for h in ds.horses.values() if h.id != ORIGIN_ID}
        log(f"既存の馬の生年を検索: {len(targets)} 頭")
        found = resolver.resolve(targets)
        log(f"  Wikidata で見つかった馬: {len(found)} 頭")
        fathers = wikidata.by_ids([e.father for e in found.values() if e.father])
        for name, entity in found.items():
            if entity.qid in rows:
                continue
            add_row(entity, name)
            father = fathers.get(entity.father) if entity.father else None
            if father is not None:
                hit = existing_for(father)
                rows[entity.qid]["Father"] = hit.name if hit else display_name(father, father.qid)

    # 父の行を先に（確認しやすいよう、名前順）
    return sorted(rows.values(), key=lambda r: r["Horse"])


def write_horses(rows: list[dict[str, str]], staging_dir: Path) -> Path:
    path = staging_dir / HORSES_RAW_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Horse", "AltNames", "Father", "BirthYear", "Source"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path
