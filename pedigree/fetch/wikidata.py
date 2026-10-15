"""Wikidata から馬の父（P22）・生年（P569）・名前（ラベルと別名）を取得する。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .client import Client

API = "https://www.wikidata.org/w/api.php"
BATCH = 50

# instance of（P31）がこれらなら馬とみなす：horse / racehorse / Thoroughbred 種の個体など
HORSE_CLASSES = {"Q726", "Q10855242", "Q26401003"}
HUMAN = "Q5"
YEAR = re.compile(r"^[+-]?(\d{4})-")


@dataclass(frozen=True)
class Entity:
    qid: str
    ja: str | None
    en: str | None
    aliases: tuple[str, ...]
    father: str | None  # Q 番号
    birth_year: int | None
    is_horse: bool
    jawiki: str | None = None  # 日本語版 Wikipedia の記事名
    enwiki: str | None = None  # 英語版 Wikipedia の記事名
    birth_place: str | None = None  # 出生地（P19）の Q 番号

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(n for n in (self.ja, self.en, *self.aliases) if n)


def _values(claims: dict, prop: str) -> list:
    return [
        c["mainsnak"]["datavalue"]["value"]
        for c in claims.get(prop, [])
        if c.get("mainsnak", {}).get("snaktype") == "value"
    ]


def parse_entity(data: dict) -> Entity | None:
    if "missing" in data or not data.get("id", "").startswith("Q"):
        return None
    claims = data.get("claims", {})
    classes = {v["id"] for v in _values(claims, "P31")}
    fathers = [v["id"] for v in _values(claims, "P22")]
    birth_year = None
    for v in _values(claims, "P569"):
        match = YEAR.match(v.get("time", ""))
        if match:
            birth_year = int(match.group(1))
            break
    labels = data.get("labels", {})
    aliases = tuple(a["value"] for lang in ("ja", "en") for a in data.get("aliases", {}).get(lang, []))
    return Entity(
        qid=data["id"],
        ja=labels.get("ja", {}).get("value"),
        en=labels.get("en", {}).get("value"),
        aliases=aliases,
        father=fathers[0] if fathers else None,
        birth_year=birth_year,
        is_horse=bool(classes & HORSE_CLASSES) or (bool(fathers) and HUMAN not in classes and bool(classes)),
        jawiki=data.get("sitelinks", {}).get("jawiki", {}).get("title"),
        enwiki=data.get("sitelinks", {}).get("enwiki", {}).get("title"),
        birth_place=next((v["id"] for v in _values(claims, "P19")), None),
    )


class Wikidata:
    def __init__(self, client: Client):
        self.client = client
        self._by_id: dict[str, Entity | None] = {}

    def _get(self, params: dict[str, str]) -> list[dict]:
        data = self.client.get_json(
            API,
            {
                "action": "wbgetentities",
                "props": "claims|labels|aliases|sitelinks",
                "languages": "ja|en",
                "sitefilter": "jawiki|enwiki",
                "format": "json",
                **params,
            },
        )
        return list(data.get("entities", {}).values())

    def by_ids(self, qids: list[str]) -> dict[str, Entity | None]:
        todo = sorted({q for q in qids if q not in self._by_id})
        for i in range(0, len(todo), BATCH):
            for data in self._get({"ids": "|".join(todo[i : i + BATCH])}):
                entity = parse_entity(data)
                if entity is not None:
                    self._by_id[entity.qid] = entity
            for q in todo[i : i + BATCH]:
                self._by_id.setdefault(q, None)
        return {q: self._by_id.get(q) for q in qids}

    def search(self, name: str) -> list[Entity]:
        """名前で検索した馬のエンティティ（同名の馬が複数いれば複数）。"""
        qids: list[str] = []
        for lang in ("ja", "en"):
            data = self.client.get_json(
                API,
                {"action": "wbsearchentities", "search": name, "language": lang, "uselang": lang,
                 "type": "item", "limit": "20", "format": "json"},
            )
            qids += [r["id"] for r in data.get("search", []) if r["id"] not in qids]
        return [e for e in self.by_ids(qids).values() if e is not None and e.is_horse]

    def by_titles(self, titles: list[str], site: str = "jawiki") -> list[tuple[str | None, Entity]]:
        """記事名から馬のエンティティを引く。(実際の記事名, エンティティ) の一覧を返す。

        リダイレクトされた場合、実際の記事名は要求した記事名と異なる。馬でないものは含めない。
        """
        result = []
        todo = sorted(set(titles))
        for i in range(0, len(todo), BATCH):
            for data in self._get({"sites": site, "titles": "|".join(todo[i : i + BATCH])}):
                entity = parse_entity(data)
                if entity is None or not entity.is_horse:
                    continue
                self._by_id[entity.qid] = entity
                result.append((data.get("sitelinks", {}).get(site, {}).get("title"), entity))
        return result
