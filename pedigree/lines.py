"""父系（系統）の割り当て。"""

from __future__ import annotations

from .models import ORIGIN_ID, Dataset, Line


def assign_lines(ds: Dataset) -> dict[int, Line | None]:
    """各馬について、自身を含めて最も近い祖先の起点（lines.csv）を返す。"""
    roots = {}
    names = ds.by_name()
    for line in ds.lines:
        horse = names.get(line.horse)
        if horse is not None:
            roots[horse.id] = line

    result: dict[int, Line | None] = {ORIGIN_ID: roots.get(ORIGIN_ID)}

    def resolve(horse_id: int) -> Line | None:
        path = []
        current = horse_id
        while current not in result and current not in roots:
            path.append(current)
            current = ds.horses[current].father_id
        line = result.setdefault(current, roots.get(current))
        for hid in path:
            result[hid] = line
        return line

    for horse_id in ds.horses:
        resolve(horse_id)
    return result
