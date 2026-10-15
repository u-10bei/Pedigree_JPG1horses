"""取得データ（staging）と既存データの照合・反映。

取得スクリプトは次の 2 ファイルを staging/ に書き出す。

- winners_raw.csv: Ryear, Rtitle, Horse, Source
- horses_raw.csv:  Horse, AltNames, Father, BirthYear, Source
  （AltNames は別表記を "|" 区切り。例：英名）

`build_review` はこれらを既存データと照合し、人が確認する review.csv の行を作る。
`apply_review` は Approve 欄が承認になっている行だけを data/ に反映する。
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, fields, replace
from pathlib import Path

from .models import Dataset, Horse, RaceWin
from .validate import Issue, validate

STAGING_DIR = Path(__file__).resolve().parent.parent / "staging"
WINNERS_RAW_FILE = "winners_raw.csv"
HORSES_RAW_FILE = "horses_raw.csv"
REVIEW_FILE = "review.csv"

APPROVED = {"y", "yes", "1", "o", "ok", "○", "✓"}

KIND_HORSE = "horse"
KIND_BIRTH_YEAR = "birth_year"
KIND_WIN = "win"
KIND_CHECK = "check"  # 参考情報。反映はしない

# 「エルコンドルパサー (USA)」「ハーツクライ (競走馬)」などの末尾の付記を取り除く
_SUFFIX = re.compile(r"[(（][^()（）]{1,10}[)）]$")


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).strip()
    name = _SUFFIX.sub("", name).strip()
    return re.sub(r"\s+", " ", name).casefold()


@dataclass
class ReviewRow:
    Approve: str = ""
    Kind: str = ""
    Ryear: str = ""
    Rtitle: str = ""
    Horse: str = ""
    Father: str = ""
    BirthYear: str = ""
    Note: str = ""
    Source: str = ""


REVIEW_COLUMNS = [f.name for f in fields(ReviewRow)]


@dataclass(frozen=True)
class RawHorse:
    name: str
    alt_names: tuple[str, ...]
    father: str | None
    birth_year: int | None
    source: str


@dataclass(frozen=True)
class RawWin:
    year: int
    race: str
    horse: str
    source: str


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_raw(staging_dir: Path = STAGING_DIR) -> tuple[list[RawWin], list[RawHorse]]:
    wins = [
        RawWin(int(r["Ryear"]), r["Rtitle"].strip(), r["Horse"].strip(), r.get("Source", ""))
        for r in read_csv(staging_dir / WINNERS_RAW_FILE)
    ]
    horses = []
    for r in read_csv(staging_dir / HORSES_RAW_FILE):
        birth = (r.get("BirthYear") or "").strip()
        horses.append(
            RawHorse(
                name=r["Horse"].strip(),
                alt_names=tuple(a.strip() for a in (r.get("AltNames") or "").split("|") if a.strip()),
                father=(r.get("Father") or "").strip() or None,
                birth_year=int(birth) if birth else None,
                source=r.get("Source", ""),
            )
        )
    return wins, horses


class NameIndex:
    """表記揺れを吸収して、取得データの馬名を既存または新規の正式名に解決する。"""

    def __init__(self, ds: Dataset, raw_horses: list[RawHorse]):
        self.existing: dict[str, Horse] = {}
        for h in ds.horses.values():
            self.existing.setdefault(normalize(h.name), h)

        # 取得データの別表記が既存馬に一致すれば、その馬として扱う
        self.alias: dict[str, str] = {}
        self.raw: dict[str, RawHorse] = {}
        for rh in raw_horses:
            canonical = rh.name
            for candidate in (rh.name, *rh.alt_names):
                hit = self.existing.get(normalize(candidate))
                if hit is not None:
                    canonical = hit.name
                    break
            for candidate in (rh.name, *rh.alt_names):
                self.alias.setdefault(normalize(candidate), canonical)
            self.raw.setdefault(normalize(canonical), rh)

    def canonical(self, name: str) -> str:
        key = normalize(name)
        if key in self.existing:
            return self.existing[key].name
        return self.alias.get(key, name)

    def existing_horse(self, name: str) -> Horse | None:
        return self.existing.get(normalize(self.canonical(name)))

    def raw_horse(self, name: str) -> RawHorse | None:
        return self.raw.get(normalize(self.canonical(name)))


def build_review(ds: Dataset, raw_wins: list[RawWin], raw_horses: list[RawHorse]) -> list[ReviewRow]:
    index = NameIndex(ds, raw_horses)
    existing_wins = {(w.year, w.race, w.winner_id) for w in ds.wins}

    horse_rows: dict[str, ReviewRow] = {}

    def propose_horse(name: str, chain: tuple[str, ...] = ()) -> bool:
        """新規馬とその未登録の祖先を提案する。既存馬につながれば True。"""
        name = index.canonical(name)
        if index.existing_horse(name) is not None:
            return True
        if name in horse_rows:
            return not horse_rows[name].Note
        if name in chain:
            horse_rows[name] = ReviewRow(Kind=KIND_HORSE, Horse=name, Note="父系が循環しています")
            return False
        rh = index.raw_horse(name)
        if rh is None:
            horse_rows[name] = ReviewRow(Kind=KIND_HORSE, Horse=name, Note="馬の情報が取得できていません")
            return False
        row = ReviewRow(
            Kind=KIND_HORSE,
            Horse=name,
            Father=index.canonical(rh.father) if rh.father else "",
            BirthYear=str(rh.birth_year or ""),
            Source=rh.source,
        )
        horse_rows[name] = row
        if not rh.father:
            row.Note = "父が取得できていません"
        elif not propose_horse(rh.father, (*chain, name)):
            row.Note = f"父「{row.Father}」が既存の馬につながりません"
        return not row.Note

    win_rows = []
    seen_wins = set()
    for w in sorted(raw_wins, key=lambda w: (w.year, w.race, w.horse)):
        name = index.canonical(w.horse)
        row = ReviewRow(Kind=KIND_WIN, Ryear=str(w.year), Rtitle=w.race, Horse=name, Source=w.source)
        race = ds.races.get(w.race)
        existing = index.existing_horse(name)
        if (w.year, w.race, name) in seen_wins:
            continue
        seen_wins.add((w.year, w.race, name))
        if existing is not None and (w.year, w.race, existing.id) in existing_wins:
            continue
        if race is None:
            row.Note = "races.csv にないレース名です"
        elif not race.held_in(w.year):
            continue  # G1 になる前の年など、対象外
        elif existing is None and not propose_horse(name):
            row.Note = "勝ち馬が既存の馬につながりません"
        win_rows.append(row)

    year_rows = []
    check_rows = []
    for rh in raw_horses:
        existing = index.existing_horse(rh.name)
        if existing is None:
            continue
        if rh.birth_year is not None and existing.birth_year is None:
            year_rows.append(
                ReviewRow(Kind=KIND_BIRTH_YEAR, Horse=existing.name, BirthYear=str(rh.birth_year), Source=rh.source)
            )
        elif rh.birth_year is not None and existing.birth_year != rh.birth_year:
            check_rows.append(
                ReviewRow(
                    Kind=KIND_CHECK,
                    Horse=existing.name,
                    BirthYear=str(rh.birth_year),
                    Note=f"生年が既存（{existing.birth_year}）と異なります",
                    Source=rh.source,
                )
            )
        if rh.father:
            father = index.existing_horse(rh.father)
            current = ds.horses.get(existing.father_id)
            if father is not None and current is not None and father.id != current.id:
                check_rows.append(
                    ReviewRow(
                        Kind=KIND_CHECK,
                        Horse=existing.name,
                        Father=father.name,
                        Note=f"父が既存（{current.name}）と異なります",
                        Source=rh.source,
                    )
                )

    rows = [*horse_rows.values(), *year_rows, *win_rows, *check_rows]
    for row in rows:
        if row.Kind != KIND_CHECK and not row.Note:
            row.Approve = "y"
    return rows


def write_review(rows: list[ReviewRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


def read_review(path: Path) -> list[ReviewRow]:
    return [ReviewRow(**{k: (r.get(k) or "").strip() for k in REVIEW_COLUMNS}) for r in read_csv(path)]


class ApplyError(Exception):
    def __init__(self, problems: list[str | Issue]):
        super().__init__("\n".join(map(str, problems)))
        self.problems = problems


def apply_review(ds: Dataset, rows: list[ReviewRow]) -> tuple[Dataset, dict[str, int]]:
    """承認された行を反映した新しい Dataset を返す。元の Dataset は変更しない。"""
    approved = [r for r in rows if r.Approve.casefold() in APPROVED and r.Kind != KIND_CHECK]
    horses = dict(ds.horses)
    wins = list(ds.wins)
    by_name = {h.name: h for h in horses.values()}
    problems: list[str | Issue] = []
    counts = {KIND_HORSE: 0, KIND_BIRTH_YEAR: 0, KIND_WIN: 0}

    def parse_year(value: str, label: str) -> int | None:
        if not value:
            return None
        if not value.isdigit():
            problems.append(f"{label}: 年「{value}」が数字ではありません")
            return None
        return int(value)

    # 父が先に登録されるよう、反映できるものから順に繰り返す
    pending = [r for r in approved if r.Kind == KIND_HORSE]
    while pending:
        remaining = []
        for r in pending:
            if r.Horse in by_name:
                problems.append(f"{r.Horse}: すでに登録されています")
            elif r.Father in by_name:
                horse = Horse(
                    id=max(horses) + 1,
                    name=r.Horse,
                    father_id=by_name[r.Father].id,
                    birth_year=parse_year(r.BirthYear, r.Horse),
                )
                horses[horse.id] = by_name[horse.name] = horse
                counts[KIND_HORSE] += 1
            else:
                remaining.append(r)
        if len(remaining) == len(pending):
            problems.extend(f"{r.Horse}: 父「{r.Father}」が登録されていません" for r in remaining)
            break
        pending = remaining

    for r in approved:
        if r.Kind == KIND_BIRTH_YEAR:
            horse = by_name.get(r.Horse)
            if horse is None:
                problems.append(f"{r.Horse}: 登録されていない馬です")
                continue
            horse = replace(horse, birth_year=parse_year(r.BirthYear, r.Horse))
            horses[horse.id] = by_name[horse.name] = horse
            counts[KIND_BIRTH_YEAR] += 1
        elif r.Kind == KIND_WIN:
            horse = by_name.get(r.Horse)
            year = parse_year(r.Ryear, f"{r.Rtitle} {r.Horse}")
            if horse is None:
                problems.append(f"{r.Ryear} {r.Rtitle}: 勝ち馬「{r.Horse}」が登録されていません")
            elif year is not None:
                wins.append(RaceWin(year, r.Rtitle, horse.id))
                counts[KIND_WIN] += 1
        elif r.Kind not in (KIND_HORSE,):
            problems.append(f"不明な種別です: {r.Kind}")

    result = Dataset(horses=horses, wins=wins, races=ds.races, lines=ds.lines)
    problems.extend(validate(result))
    if problems:
        raise ApplyError(problems)
    return result, counts
