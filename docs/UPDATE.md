# データ更新の手順

Wikipedia（勝ち馬）と Wikidata（父・生年）から取得し、確認してから `data/` に反映します。
GitHub Codespaces で作業することを想定しています（必要なパッケージは自動でインストールされます）。

## 1. 取得

```sh
# 勝ち馬（例：2005 年以降）→ staging/winners_raw.csv
python -m pedigree fetch winners --from 2005

# 父・生年 → staging/horses_raw.csv
#   未登録の勝ち馬は、既存の馬につながるまで父をさかのぼって取得します
#   既存の馬の生年も取得します（不要なら --no-existing）
python -m pedigree fetch horses
```

- 応答は `.cache/http/` に保存されるので、途中で止まっても再実行すれば続きから取得します。
- アクセス過多（HTTP 429）の場合は自動で待って再試行します。間隔は `--interval`（秒）で変えられます。

## 2. 照合

```sh
python -m pedigree review   # → staging/review.csv
```

`review.csv` の各行は次のとおりです。

| Kind | 内容 |
|---|---|
| `horse` | 新しく登録する馬（父・生年つき） |
| `birth_year` | 既存の馬に生年を追加 |
| `win` | 新しく登録する勝利 |
| `check` | 参考情報（既存データとの食い違い）。反映はされません |

- 問題のない行は `Approve` が `y` になっています。
- `Note` に理由が書かれた行は `Approve` が空欄です。内容を確認し、正しければ `y` を入れてください。
  馬名や父を直して承認することもできます。
- 反映したくない行は `Approve` を空欄にしてください。

## 3. 反映

```sh
python -m pedigree apply --dry-run   # 確認だけ
python -m pedigree apply             # data/ に反映
python -m pedigree validate
```

反映後のデータが検証に通らない場合は中止し、`data/` は変更しません。

## 4. コミット

```sh
git add data/
git commit -m "2026 年の勝ち馬を追加"
git push
```

## 出典

- Wikipedia（CC BY-SA 4.0）：各レースの記事の「歴代優勝馬」
- Wikidata（CC0）：父（P22）、生年月日（P569）
