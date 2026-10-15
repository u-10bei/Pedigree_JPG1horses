"""血統データのモデル定義。"""

from __future__ import annotations

from dataclasses import dataclass, field

# 三大始祖をまとめる仮想ルート（Id 0）の Id
ORIGIN_ID = 0


@dataclass(frozen=True)
class Horse:
    id: int
    name: str
    father_id: int
    birth_year: int | None = None
    wikidata: str | None = None  # Wikidata の Q 番号（同名の馬と区別するため）


@dataclass(frozen=True)
class RaceWin:
    year: int
    race: str
    winner_id: int


@dataclass(frozen=True)
class Race:
    name: str
    first_year: int
    last_year: int | None = None
    wiki_title: str | None = None  # 日本語版 Wikipedia の記事名（レース名と同じなら空欄）

    @property
    def article(self) -> str:
        return self.wiki_title or self.name

    def held_in(self, year: int) -> bool:
        if year < self.first_year:
            return False
        return self.last_year is None or year <= self.last_year


@dataclass(frozen=True)
class Line:
    """父系の起点。この馬とその子孫（より近い起点がない限り）が同じ系統になる。"""

    horse: str
    name: str
    color: str | None = None


@dataclass
class Dataset:
    horses: dict[int, Horse]
    wins: list[RaceWin]
    races: dict[str, Race]
    lines: list[Line] = field(default_factory=list)

    def by_name(self) -> dict[str, Horse]:
        return {h.name: h for h in self.horses.values()}

    def children(self) -> dict[int, list[int]]:
        result: dict[int, list[int]] = {}
        for h in self.horses.values():
            if h.id != ORIGIN_ID:
                result.setdefault(h.father_id, []).append(h.id)
        return result

    def next_id(self) -> int:
        return max(self.horses, default=ORIGIN_ID) + 1
