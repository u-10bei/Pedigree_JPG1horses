"""階層図用の JSON を作る。

    python -m pedigree build   → site/data/pedigree.json
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from .lines import assign_lines
from .models import ORIGIN_ID, Dataset, Line

SITE_DIR = Path(__file__).resolve().parent.parent / "site"
OUTPUT = SITE_DIR / "data" / "pedigree.json"


def line_colors(ds: Dataset) -> dict[str, str | None]:
    """系統名 → 色。色が空欄の系統は、最も近い祖先の系統の色を受け継ぐ（なければ None）。"""
    names = ds.by_name()
    by_root = {names[line.horse].id: line for line in ds.lines if line.horse in names}
    colors: dict[str, str | None] = {}
    for line in ds.lines:
        color = line.color
        horse = names.get(line.horse)
        while color is None and horse is not None and horse.id != ORIGIN_ID:
            horse = ds.horses.get(horse.father_id)
            if horse is not None and horse.id in by_root:
                color = by_root[horse.id].color
        colors[line.name] = color
    return colors


def build(ds: Dataset) -> dict:
    wins: dict[int, list[list]] = defaultdict(list)
    for w in sorted(ds.wins, key=lambda w: (w.year, w.race)):
        wins[w.winner_id].append([w.year, w.race])

    lines: dict[int, Line | None] = assign_lines(ds)
    colors = line_colors(ds)
    roots = {line.horse for line in ds.lines}

    horses = []
    for h in sorted(ds.horses.values(), key=lambda h: h.id):
        line = lines.get(h.id)
        record = {"id": h.id, "name": h.name, "father": None if h.id == ORIGIN_ID else h.father_id}
        if h.birth_year is not None:
            record["birth"] = h.birth_year
        if wins.get(h.id):
            record["wins"] = wins[h.id]
        if line is not None:
            record["line"] = line.name
        if h.name in roots:
            record["lineRoot"] = True
        horses.append(record)

    return {
        "generated": date.today().isoformat(),
        "lastYear": max((w.year for w in ds.wins), default=None),
        "lines": [{"name": line.name, "root": line.horse, "color": colors[line.name]} for line in ds.lines],
        "horses": horses,
    }


def write(ds: Dataset, path: Path = OUTPUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(ds), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path
