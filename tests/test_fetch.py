import pytest

pytest.importorskip("bs4")
pytest.importorskip("requests")

from pedigree.fetch.client import Client  # noqa: E402
from pedigree.fetch.wikidata import parse_entity  # noqa: E402
from pedigree.fetch.wikipedia import parse_winners  # noqa: E402

# 実際の記事の構造（同着の rowspan、区切り行、脚注、リンク）をまねた表
RACE_HTML = """
<table><tr><th>概要</th></tr><tr><td>優勝馬とは関係のない表</td></tr></table>
<table>
<tr><th>回数</th><th>施行日</th><th>競馬場</th><th>優勝馬</th><th>性齢</th></tr>
<tr><td>第70回</td><td>2009年5月24日</td><td>東京</td>
    <td><a href="./ブエナビスタ_(競走馬)">ブエナビスタ</a><sup><a href="#n1">[注 1]</a></sup></td><td>牝3</td></tr>
<tr><td colspan="5">国際GIに格付け</td></tr>
<tr><td rowspan="2">第71回</td><td rowspan="2">2010年5月23日</td><td rowspan="2">東京</td>
    <td><a href="./アパパネ">アパパネ</a></td><td rowspan="2">牝3</td></tr>
<tr><td><a href="./サンテミリオン_(競走馬)">サンテミリオン</a></td></tr>
<tr><td>第72回</td><td>2011年5月22日</td><td>東京</td>
    <td><a href="./エリンコート?action=edit&amp;redlink=1">エリンコート</a></td><td>牝3</td></tr>
<tr><td>第73回</td><td>2012年5月20日</td><td>東京</td><td>ジェンティルドンナ</td><td>牝3</td></tr>
</table>
"""


def test_parse_winners_handles_rowspan_dividers_and_footnotes():
    winners = [(w.year, w.name, w.title) for w in parse_winners(RACE_HTML)]
    assert winners == [
        (2009, "ブエナビスタ", "ブエナビスタ (競走馬)"),
        (2010, "アパパネ", "アパパネ"),
        (2010, "サンテミリオン", "サンテミリオン (競走馬)"),
        (2011, "エリンコート", None),
        (2012, "ジェンティルドンナ", None),
    ]


def test_parse_winners_without_table():
    assert parse_winners("<p>曖昧さ回避</p>") == []


def entity(claims, labels=None, qid="Q1"):
    return {
        "id": qid,
        "labels": labels or {"ja": {"value": "ディープインパクト"}, "en": {"value": "Deep Impact"}},
        "aliases": {"en": [{"value": "Deep Impact (horse)"}]},
        "claims": {
            prop: [{"mainsnak": {"snaktype": "value", "datavalue": {"value": v}}} for v in values]
            for prop, values in claims.items()
        },
    }


def test_parse_entity_reads_father_birth_year_and_names():
    e = parse_entity(entity({"P31": [{"id": "Q726"}], "P22": [{"id": "Q180387"}], "P569": [{"time": "+2002-03-25T00:00:00Z"}]}))
    assert (e.ja, e.en, e.father, e.birth_year, e.is_horse) == ("ディープインパクト", "Deep Impact", "Q180387", 2002, True)
    assert "Deep Impact (horse)" in e.names


def test_parse_entity_year_precision_and_non_horses():
    e = parse_entity(entity({"P31": [{"id": "Q726"}], "P569": [{"time": "+2006-00-00T00:00:00Z"}]}))
    assert e.birth_year == 2006
    human = parse_entity(entity({"P31": [{"id": "Q5"}], "P22": [{"id": "Q2"}]}))
    assert not human.is_horse
    assert parse_entity({"id": "-1", "missing": ""}) is None


class FakeResponse:
    def __init__(self, status, text="", headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}
        self.ok = 200 <= status < 300


class FakeSession:
    def __init__(self, responses):
        self.responses, self.headers, self.calls = list(responses), {}, 0

    def get(self, url, timeout):
        self.calls += 1
        return self.responses.pop(0)


def test_client_retries_rate_limit_and_caches(tmp_path):
    session = FakeSession([FakeResponse(429, headers={"Retry-After": "3"}), FakeResponse(200, '{"ok": 1}')])
    waits = []
    client = Client(cache_dir=tmp_path, min_interval=0, session=session, sleep=waits.append)
    assert client.get_json("https://example.org/api", {"b": "2", "a": "1"}) == {"ok": 1}
    assert 3 in waits
    assert client.get_json("https://example.org/api", {"a": "1", "b": "2"}) == {"ok": 1}
    assert session.calls == 2  # 2 回目はキャッシュから


def test_client_treats_404_as_empty(tmp_path):
    client = Client(cache_dir=tmp_path, min_interval=0, session=FakeSession([FakeResponse(404)]), sleep=lambda s: None)
    assert client.wikipedia_html("存在しない記事") == ""


def test_parse_infobox_father():
    from pedigree.fetch.wikipedia import parse_infobox_father

    ja = """<table class="infobox"><tr><th>父</th><td><a href="./ハーツクライ">ハーツクライ</a><sup>[1]</sup></td></tr>
    <tr><th>生国</th><td><a href="./日本">日本</a>（北海道安平町）</td></tr></table>"""
    assert parse_infobox_father(ja) == ("ハーツクライ", "ハーツクライ")
    en = """<table class="infobox vcard"><tr><th>Sire</th><td>Encosta de Lago</td></tr>
    <tr><th>Country</th><td>Australia</td></tr></table>"""
    assert parse_infobox_father(en) == ("Encosta de Lago", None)
    assert parse_infobox_father("<p>情報欄なし</p>") is None


def test_jawiki_categories_follows_redirects(tmp_path):
    import json

    response = {
        "query": {
            "normalized": [{"from": "ヘネシー_(競走馬)", "to": "ヘネシー (競走馬)"}],
            "redirects": [{"from": "ストームキャット (競走馬)", "to": "ストームキャット"}],
            "pages": {
                "1": {"title": "ヘネシー (競走馬)", "categories": [{"title": "Category:日本供用種牡馬"}]},
                "2": {"title": "ストームキャット"},
            },
        }
    }
    session = FakeSession([FakeResponse(200, json.dumps(response))])
    client = Client(cache_dir=tmp_path, min_interval=0, session=session, sleep=lambda s: None)
    cats = client.jawiki_categories(["ヘネシー_(競走馬)", "ストームキャット (競走馬)"], ["日本供用種牡馬"])
    assert cats == {"ヘネシー_(競走馬)": {"日本供用種牡馬"}, "ストームキャット (競走馬)": set()}


def test_parse_infobox_birth_year():
    from pedigree.fetch.wikipedia import infobox_father_text, parse_infobox_birth_year

    ja = '<table class="infobox"><tr><th>生誕</th><td>1940年<sup>[1]</sup>4月5日</td></tr><tr><th>父</th><td>トウルヌソル</td></tr></table>'
    assert parse_infobox_birth_year(ja) == 1940
    assert infobox_father_text(ja) == "トウルヌソル"
    en = '<table class="infobox"><tr><th>Foaled</th><td>3 May 1764</td></tr></table>'
    assert parse_infobox_birth_year(en) == 1764
    assert parse_infobox_birth_year('<table class="infobox"><tr><th>生誕</th><td>不明</td></tr></table>') is None
