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

from .models import ORIGIN_ID, Dataset, Horse, RaceWin
from .validate import MIN_RACE_AGE, Issue, validate

STAGING_DIR = Path(__file__).resolve().parent.parent / "staging"
WINNERS_RAW_FILE = "winners_raw.csv"
HORSES_RAW_FILE = "horses_raw.csv"
REVIEW_FILE = "review.csv"

APPROVED = {"y", "yes", "1", "o", "ok", "○", "✓"}

KIND_HORSE = "horse"
KIND_BIRTH_YEAR = "birth_year"
KIND_WIN = "win"
KIND_CHECK = "check"  # 参考情報。反映はしない

# 「エルコンドルパサー (USA)」「ハーツクライ (競走馬)」などの末尾の付記を取り除く。
# ただし同名の馬を区別するための生年（「Pharamond (1925)」）は残す
_SUFFIX = re.compile(r"[(（](?!\d{4}[)）])[^()（）]{1,10}[)）]$")


# 古い表記（「ガヴアナー」「ヒカリデユール」）と現代の表記を同一視するため、小書きの仮名を並字にそろえる
_SMALL_KANA = str.maketrans("ァィゥェォッャュョヮヵヶ", "アイウエオツヤユヨワカケ")


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).strip()
    name = _SUFFIX.sub("", name).strip()
    # 「Man o' War」と「Man o'War」、「St. Albans」と「St Albans」などを同一視する
    name = re.sub(r"[\s'’`.\-・]", "", name)
    return name.translate(_SMALL_KANA).casefold()


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
    AltNames: str = ""  # 別表記（"|" 区切り）。表記を選び直すときの参考


REVIEW_COLUMNS = [f.name for f in fields(ReviewRow)]


@dataclass(frozen=True)
class RawHorse:
    name: str
    alt_names: tuple[str, ...]
    father: str | None
    birth_year: int | None
    source: str
    father_qid: str | None = None  # 父の Wikidata の Q 番号（同名の馬と区別するため）

    @property
    def qid(self) -> str | None:
        return self.source.split(":", 1)[1] if self.source.startswith("wikidata:") else None


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
                father_qid=(r.get("FatherQid") or "").strip() or None,
            )
        )
    return wins, horses


class NameIndex:
    """表記揺れを吸収して、取得データの馬名を既存または新規の正式名に解決する。

    Wikidata の Q 番号が分かっている場合はそれを優先する。名前が同じでも、Q 番号や父が
    既存の馬と食い違う場合は同名の別の馬とみなし、馬名に生年を付けて区別する。
    """

    def __init__(self, ds: Dataset, raw_horses: list[RawHorse]):
        self.existing: dict[str, Horse] = {}
        for h in ds.horses.values():
            self.existing.setdefault(normalize(h.name), h)
        existing_by_qid = {h.wikidata: h for h in ds.horses.values() if h.wikidata}

        def by_name(rh: RawHorse) -> Horse | None:
            for candidate in (rh.name, *rh.alt_names):
                hit = self.existing.get(normalize(candidate))
                if hit is not None:
                    return hit
            return None

        # 1 回目：Q 番号、なければ名前で既存の馬に対応付ける
        self.match: list[Horse | None] = []  # raw_horses と同じ順
        self.same_name: list[Horse | None] = []  # 同名だが別の馬と判断した既存馬
        for rh in raw_horses:
            hit = existing_by_qid.get(rh.qid) if rh.qid else None
            clash = None
            if hit is None:
                hit = by_name(rh)
                if hit is not None and hit.wikidata and rh.qid and hit.wikidata != rh.qid:
                    hit, clash = None, hit
            self.match.append(hit)
            self.same_name.append(clash)

        # 2 回目：父が既存の馬の父と食い違うものも、同名の別の馬とみなす
        qid_to_existing = {rh.qid: hit for rh, hit in zip(raw_horses, self.match) if rh.qid and hit}
        for i, rh in enumerate(raw_horses):
            hit = self.match[i]
            if hit is None or hit.id == ORIGIN_ID or (hit.wikidata and hit.wikidata == rh.qid):
                continue
            father = qid_to_existing.get(rh.father_qid) if rh.father_qid else None
            if father is None and rh.father:
                father = self.existing.get(normalize(rh.father))
            if father is not None and father.id != hit.father_id:
                self.match[i], self.same_name[i] = None, hit

        self.alias: dict[str, str] = {}
        self.raw: dict[str, RawHorse] = {}
        self.by_qid: dict[str, str] = {}  # Q 番号 → 正式名
        self.clashes: dict[str, Horse] = {}  # 生年を付けた新規名 → 同名の既存馬
        for rh, hit, clash in zip(raw_horses, self.match, self.same_name):
            if hit is not None:
                canonical = hit.name
            elif clash is not None:
                canonical = f"{rh.name} ({rh.birth_year or rh.qid or '?'})"
                self.clashes[canonical] = clash
            else:
                canonical = rh.name
            if clash is None:
                for candidate in (rh.name, *rh.alt_names):
                    self.alias.setdefault(normalize(candidate), canonical)
            self.raw.setdefault(normalize(canonical), rh)
            if rh.qid:
                self.by_qid[rh.qid] = canonical

    def canonical(self, name: str) -> str:
        key = normalize(name)
        if key in self.existing:
            return self.existing[key].name
        return self.alias.get(key, name)

    def father_of(self, rh: RawHorse) -> str:
        """取得データの父の正式名（Q 番号で引けるならそれを優先）。"""
        if rh.father_qid and rh.father_qid in self.by_qid:
            return self.by_qid[rh.father_qid]
        return self.canonical(rh.father) if rh.father else ""

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
            Father=index.father_of(rh),
            BirthYear=str(rh.birth_year or ""),
            Source=rh.source,
            AltNames="|".join(a for a in rh.alt_names if a != name),
        )
        horse_rows[name] = row
        if name in index.clashes:
            clash = index.clashes[name]
            row.Note = (
                f"同名の既存の馬（{clash.name}、父 {ds.horses[clash.father_id].name}）とは別の馬と判断し、"
                "馬名に生年を付けました。同じ馬なら行を削除してください"
            )
            propose_horse(row.Father, (*chain, name)) if row.Father else None
        elif not row.Father:
            row.Note = "父が取得できていません"
        elif not propose_horse(row.Father, (*chain, name)):
            row.Note = f"父「{row.Father}」が既存の馬につながりません"
        return not row.Note

    winners_by_race: dict[tuple[int, str], list[str]] = {}
    for w in ds.wins:
        winners_by_race.setdefault((w.year, w.race), []).append(ds.horses[w.winner_id].name)

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
        if existing is None and (w.year, w.race) in winners_by_race:
            # 既存データにある年の勝ち馬が別名で取得された（表記揺れか、データの誤り）
            row.Kind = KIND_CHECK
            row.Note = f"既存の勝ち馬（{'・'.join(winners_by_race[(w.year, w.race)])}）と名前が一致しません"
            win_rows.append(row)
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
    for rh, existing, clash in zip(raw_horses, index.match, index.same_name):
        if clash is not None:
            check_rows.append(
                ReviewRow(
                    Kind=KIND_CHECK,
                    Horse=clash.name,
                    Father=index.father_of(rh),
                    BirthYear=str(rh.birth_year or ""),
                    Note=f"同名の別の馬（父 {index.father_of(rh) or '不明'}）の情報です。"
                    f"既存の {clash.name}（父 {ds.horses[clash.father_id].name}）には反映しません",
                    Source=rh.source,
                )
            )
        if existing is None:
            continue
        father = index.existing_horse(index.father_of(rh)) if rh.father else None
        note = ""
        if rh.father and father is None:
            note = f"取得した父「{rh.father}」を既存データと照合できません（別の馬の可能性があります）"
        if rh.birth_year is not None and existing.birth_year is None:
            year_rows.append(
                ReviewRow(
                    Kind=KIND_BIRTH_YEAR,
                    Horse=existing.name,
                    BirthYear=str(rh.birth_year),
                    Note=note,
                    Source=rh.source,
                )
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

    # 生年が勝利年と矛盾する（勝利時に 2 歳未満）ものは自動承認しない
    first_win: dict[str, int] = {}
    for w in ds.wins:
        name = ds.horses[w.winner_id].name
        first_win[name] = min(first_win.get(name, w.year), w.year)
    for r in win_rows:
        if r.Kind == KIND_WIN:
            first_win[r.Horse] = min(first_win.get(r.Horse, int(r.Ryear)), int(r.Ryear))
    for r in [*horse_rows.values(), *year_rows]:
        if r.BirthYear and r.Horse in first_win and first_win[r.Horse] - int(r.BirthYear) < MIN_RACE_AGE and not r.Note:
            r.Note = f"生年が勝利年（{first_win[r.Horse]}年）と合いません"

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


def is_approved(row: ReviewRow) -> bool:
    return row.Kind != KIND_CHECK and row.Approve.strip().casefold() in APPROVED


def remaining_rows(rows: list[ReviewRow]) -> list[ReviewRow]:
    """反映後も review.csv に残す行（未承認の行と参考情報）。"""
    return [r for r in rows if not is_approved(r)]


def source_qid(row: ReviewRow) -> str | None:
    return row.Source.split(":", 1)[1] if row.Source.startswith("wikidata:") else None


def apply_review(ds: Dataset, rows: list[ReviewRow]) -> tuple[Dataset, dict[str, int]]:
    """承認された行を反映した新しい Dataset を返す。元の Dataset は変更しない。"""
    approved = [r for r in rows if is_approved(r)]
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
                    wikidata=source_qid(r),
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
            # 生年の出典の Q 番号も記録し、次回からは名前ではなく Q 番号で照合する
            horse = replace(horse, birth_year=parse_year(r.BirthYear, r.Horse), wikidata=horse.wikidata or source_qid(r))
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
