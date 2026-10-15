# Pedigree_JPG1horses
Represent the pedigree of a Japanese G1 horse in a hierarchical tree.

日本の G1 勝利馬（J・G1 を除き、1983 年までの旧八大競走、ジャパンカップを含む）の父系を階層図にしています。

> Python への移行中です。計画は [docs/PLAN.md](docs/PLAN.md) を参照してください。
> 旧構成（MariaDB・PHP・D3.js）は `legacy/` にあります。

## データ

`data/` の CSV が正本です。列の意味は [docs/PLAN.md](docs/PLAN.md#データdata) を参照してください。

## 開発

GitHub Codespaces で開くと、必要なものが自動でインストールされます。ローカルで動かす場合は次のとおりです。

```sh
pip install -e '.[dev,fetch,admin]'
python -m pedigree validate   # データの整合性を検証
pytest                        # テスト
```

データの更新手順は [docs/UPDATE.md](docs/UPDATE.md) を参照してください。

## 出典

- Wikipedia（CC BY-SA 4.0）：各レースの「歴代優勝馬」
- Wikidata（CC0）：父・生年
