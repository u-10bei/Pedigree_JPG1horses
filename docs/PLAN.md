# Python 移行・デプロイ計画

MariaDB + PHP + D3.js 構成を、Python + CSV + 静的サイト（GitHub Pages）に移行する。

## 決定事項

| 項目 | 決定 |
|---|---|
| データの正本 | `data/*.csv` を Git で管理（MariaDB・PHP は廃止し `legacy/` に退避） |
| 公開 | GitHub Actions で検証・ビルド → GitHub Pages で静的配信 |
| 作業環境 | GitHub Codespaces（`.devcontainer/`） |
| 追いつき（2005 年秋〜） | Wikipedia（勝ち馬）・Wikidata / Wikipedia（父・生年）から取得 → 照合 → 確認画面で承認 → `data/` に反映 |
| 定期更新 | 同じ仕組みで最新年のみ取得。手動補完は CLI |
| 対象レース | 旧八大競走・ジャパンカップ・1984 年以降の平地 G1（J・G1 は除く）。大阪杯・ホープフルS（2017〜）、ヴィクトリアマイル（2006〜）を含む |
| 階層図 | 折りたたみ式の横向きツリー。中継ぎ祖先の圧縮、父系の色分け（手動）、検索・ハイライト |
| 将来の拡張 | 放射状ツリー、サンバースト、時間軸ツリー |
| 生年 | `BirthYear` 列を追加。空欄可（エラーにしない） |
| 出典表示 | Wikipedia（CC BY-SA 4.0）、Wikidata（CC0） |

## データ（`data/`）

| ファイル | 列 | 備考 |
|---|---|---|
| `pedigree.csv` | `Id, Horse, FatherId, BirthYear, Wikidata` | Id 0 は三大始祖をまとめる仮想ルート `__origin__`。`BirthYear`・`Wikidata`（Q 番号）は空欄可。同名の別の馬は `Pharamond (1925)` のように生年を付けて区別する |
| `race_winner.csv` | `Ryear, Rtitle, WinnerId` | 同着に対応するため (年, レース, 勝ち馬) で一意 |
| `races.csv` | `Rtitle, FirstYear, LastYear, WikiTitle` | 対象レースと対象期間。`LastYear` 空欄は継続中。`WikiTitle` は Wikipedia の記事名がレース名と異なる場合のみ |
| `lines.csv` | `Horse, LineName, Color` | 父系の起点。各馬は自身を含む最も近い起点の系統に属する。`Color` は `#RRGGBB` または空欄 |

## 検証ルール（`python -m pedigree validate`）

- 馬名が重複しない（同名の別の馬は生年を付けて区別する）
- Wikidata の Q 番号は `Q` + 数字で、複数の馬に付いていない
- 父 Id が存在し、循環せずに仮想ルートまでたどれる
- 生年は空欄可。入力されている場合、父より後に生まれている
- レース名が `races.csv` にあり、対象期間内である
- 勝ち馬の生年が入力されている場合、勝利時に 2 歳以上
- (年, レース, 勝ち馬) が重複しない
- `lines.csv` の起点の馬が存在し、起点・系統名が重複せず、色が `#RRGGBB`

## フェーズ

1. **基盤** ✅：CSV 移行、ブラックホーク重複の統合（Id 979 → 939）、`BirthYear` 列、`races.csv`・`lines.csv`、検証、テスト、`.devcontainer`、CI
2. **取得と照合** ✅：Wikipedia・Wikidata の取得（キャッシュ・再試行付き）、照合（`review`）と反映（`apply`）。手順は [UPDATE.md](UPDATE.md)
3. **確認画面と CLI** ✅：確認画面（`python -m pedigree admin`）で絞り込み・修正・承認・反映・手動追加。CLI の `add horse` / `add win`
4. **追いつきの実行**：Codespaces で取得 → 確認
5. **階層図**：JSON 生成、折りたたみツリー
6. **CI/CD**：GitHub Pages へのデプロイ
