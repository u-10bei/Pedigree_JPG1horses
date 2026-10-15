"""CSV の読み書き。

書き出しは行の並びと書式を固定し、Git の差分が最小になるようにする。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .models import Dataset, Horse, Line, Race, RaceWin

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PEDIGREE_FILE = "pedigree.csv"
RACE_WINNER_FILE = "race_winner.csv"
RACES_FILE = "races.csv"
LINES_FILE = "lines.csv"


def _optional_int(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


def _optional_str(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_rows(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])


def load(data_dir: Path = DATA_DIR) -> Dataset:
    horses = {}
    for row in _read_rows(data_dir / PEDIGREE_FILE):
        horse = Horse(
            id=int(row["Id"]),
            name=row["Horse"].strip(),
            father_id=int(row["FatherId"]),
            birth_year=_optional_int(row.get("BirthYear")),
            wikidata=_optional_str(row.get("Wikidata")),
        )
        if horse.id in horses:
            raise ValueError(f"{PEDIGREE_FILE}: Id {horse.id} が重複しています")
        horses[horse.id] = horse

    wins = [
        RaceWin(year=int(r["Ryear"]), race=r["Rtitle"].strip(), winner_id=int(r["WinnerId"]))
        for r in _read_rows(data_dir / RACE_WINNER_FILE)
    ]

    races = {}
    for r in _read_rows(data_dir / RACES_FILE):
        race = Race(
            name=r["Rtitle"].strip(),
            first_year=int(r["FirstYear"]),
            last_year=_optional_int(r.get("LastYear")),
            wiki_title=_optional_str(r.get("WikiTitle")),
        )
        races[race.name] = race

    lines_path = data_dir / LINES_FILE
    lines = []
    if lines_path.exists():
        lines = [
            Line(
                horse=r["Horse"].strip(),
                name=r["LineName"].strip(),
                color=_optional_str(r.get("Color")),
            )
            for r in _read_rows(lines_path)
        ]

    return Dataset(horses=horses, wins=wins, races=races, lines=lines)


def save(dataset: Dataset, data_dir: Path = DATA_DIR) -> None:
    _write_rows(
        data_dir / PEDIGREE_FILE,
        ["Id", "Horse", "FatherId", "BirthYear", "Wikidata"],
        [
            [h.id, h.name, h.father_id, h.birth_year, h.wikidata]
            for h in sorted(dataset.horses.values(), key=lambda h: h.id)
        ],
    )
    _write_rows(
        data_dir / RACE_WINNER_FILE,
        ["Ryear", "Rtitle", "WinnerId"],
        [
            [w.year, w.race, w.winner_id]
            for w in sorted(dataset.wins, key=lambda w: (w.year, w.race, w.winner_id))
        ],
    )
    _write_rows(
        data_dir / RACES_FILE,
        ["Rtitle", "FirstYear", "LastYear", "WikiTitle"],
        [
            [r.name, r.first_year, r.last_year, r.wiki_title]
            for r in sorted(dataset.races.values(), key=lambda r: (r.first_year, r.name))
        ],
    )
    _write_rows(
        data_dir / LINES_FILE,
        ["Horse", "LineName", "Color"],
        [[line.horse, line.name, line.color] for line in dataset.lines],
    )
