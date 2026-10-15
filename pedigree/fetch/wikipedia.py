"""日本語版 Wikipedia のレース記事から「歴代優勝馬」の表を読む。"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

WINNER_HEADERS = ("優勝馬", "勝ち馬", "勝馬")
DATE_HEADERS = ("施行日", "開催日", "施行日程", "年度", "開催年", "年")
YEAR = re.compile(r"(\d{4})\s*年")


@dataclass(frozen=True)
class WinnerCell:
    year: int
    name: str
    title: str | None  # 馬の記事名（リンクがない場合は None）


def _clean(cell: Tag) -> Tag:
    for sup in cell.find_all("sup"):
        sup.decompose()
    return cell


def _grid(table: Tag) -> list[list[Tag | None]]:
    """rowspan / colspan を展開して、行ごとに列の位置がそろったセル配列にする。"""
    grid: list[list[Tag | None]] = []
    carry: dict[int, tuple[Tag, int]] = {}  # 列 → (セル, 残り行数)
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        row: list[Tag | None] = []
        cells = iter(tr.find_all(["th", "td"], recursive=False))
        col = 0
        while True:
            if col in carry:
                cell, remaining = carry[col]
                row.append(cell)
                if remaining > 1:
                    carry[col] = (cell, remaining - 1)
                else:
                    del carry[col]
                col += 1
                continue
            cell = next(cells, None)
            if cell is None:
                break
            span = int(cell.get("colspan", 1) or 1)
            rowspan = int(cell.get("rowspan", 1) or 1)
            for i in range(span):
                row.append(cell)
                if rowspan > 1:
                    carry[col + i] = (cell, rowspan - 1)
            col += span
        # 残りの rowspan が右端にある場合
        while col in carry:
            cell, remaining = carry.pop(col)
            row.append(cell)
            if remaining > 1:
                carry[col] = (cell, remaining - 1)
            col += 1
        grid.append(row)
    return grid


def _header_index(header: list[str], names: tuple[str, ...]) -> int | None:
    for name in names:
        for i, text in enumerate(header):
            if text == name:
                return i
    for name in names:
        for i, text in enumerate(header):
            if name in text:
                return i
    return None


def _link_title(a: Tag) -> str | None:
    href = a.get("href", "")
    if not href.startswith("./") or "redlink=1" in href:
        return None
    title = urllib.parse.unquote(href[2:]).split("#")[0]
    return title.replace("_", " ")


def parse_winners(html: str) -> list[WinnerCell]:
    """歴代優勝馬の表から (年, 馬名, 記事名) を取り出す。同着は複数件になる。"""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        grid = _grid(table)
        if not grid:
            continue
        header = [c.get_text(" ", strip=True) if c else "" for c in grid[0]]
        winner_col = _header_index(header, WINNER_HEADERS)
        date_col = _header_index(header, DATE_HEADERS)
        if winner_col is None or date_col is None:
            continue

        results: list[WinnerCell] = []
        seen: set[tuple[int, int]] = set()
        for row in grid[1:]:
            if len(row) <= max(winner_col, date_col):
                continue  # 「国際GIに格付け」などの区切り行
            date_cell, winner_cell = row[date_col], row[winner_col]
            if date_cell is winner_cell:
                continue
            match = YEAR.search(_clean(date_cell).get_text())
            if not match:
                continue
            if (id(winner_cell), int(match.group(1))) in seen:
                continue
            seen.add((id(winner_cell), int(match.group(1))))
            results.extend(_winners_in_cell(int(match.group(1)), _clean(winner_cell)))
        if results:
            return results
    return []


def _winners_in_cell(year: int, cell: Tag) -> list[WinnerCell]:
    links = [a for a in cell.find_all("a") if a.get_text(strip=True)]
    if links:
        return [WinnerCell(year, a.get_text(strip=True), _link_title(a)) for a in links]
    # 同着が <br> 区切りのテキストで書かれている場合
    names = [t.strip() for t in cell.get_text("\n").split("\n") if t.strip()]
    return [WinnerCell(year, name, None) for name in names]


FATHER_HEADERS = ("父", "Sire")
COUNTRY_HEADERS = ("生国", "Country")


def _infobox_cell(html: str, headers: tuple[str, ...]) -> Tag | None:
    soup = BeautifulSoup(html, "html.parser")
    for box in soup.find_all("table", class_=lambda c: c and "infobox" in c):
        for tr in box.find_all("tr"):
            th, td = tr.find("th"), tr.find("td")
            if th is not None and td is not None and th.get_text(strip=True) in headers:
                return _clean(td)
    return None


def parse_infobox_father(html: str) -> tuple[str, str | None] | None:
    """競走馬の記事の情報欄（日本語版の「父」、英語版の「Sire」）から父の (馬名, 記事名) を取り出す。"""
    td = _infobox_cell(html, FATHER_HEADERS)
    if td is None:
        return None
    for a in td.find_all("a"):
        name = a.get_text(strip=True)
        if name and "#" not in a.get("href", "#"):
            return name, _link_title(a)
    name = td.get_text(" ", strip=True)
    return (name, None) if name else None


def parse_infobox_country(html: str) -> str | None:
    """情報欄の生国（日本語版の「生国」、英語版の「Country」）。"""
    td = _infobox_cell(html, COUNTRY_HEADERS)
    if td is None:
        return None
    return td.get_text(" ", strip=True) or None
