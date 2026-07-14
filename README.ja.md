# Data Format Lab

データ形式やデータベースの性能主張を、共通契約と形式固有ワークロードで検証する公開研究ラボです。単一の「最強形式」は決めません。

[English](README.md) | [研究ログ](docs/research-log.md) | [データ利用上の注意](DATA_NOTICE.md)

最初のケーススタディは、2026-07-03に固定した公開GitHub Starsメタデータ2,331件・13列です。特定のStarsデータ専用ツールではなく、今後ほかのデータセットや主張を追加できる構成です。

## 3つのlane

| lane | 検証する問い | 例 |
| --- | --- | --- |
| `fair` | 同じArrowテーブルを保存し、同じ検索結果を返すときの容量と速度 | CSV、JSONL、Parquet、Lance、Vortex、適応TsFile |
| `claims` | 公式が主張する強みを、適したワークロードで再現できるか | Lance FTS、Vortex scan、TsFile時系列 |
| `prompt` | 同じ7項目をLLMへ渡すときの正確なtoken数 | Compact TSV、object JSONL、array JSONL |

異なるlaneや異なる機種の結果は順位比較しません。同一laneの`FULL_COMPARABLE`だけが順位対象です。DuckDBはファイル形式ではなくSQL実行エンジンとして扱います。

## 証拠の流れ

```text
DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED
```

非対応は`UNSUPPORTED`、実行失敗は`FAILED`として公開記録に残します。13列の型・NULL・値・件数・canonical hashが一致しない形式は速度や容量の順位から除外します。

比較可能性は次の4種類です。

- `FULL_COMPARABLE`: そのlane内で公平に比較可能。
- `ADAPTED`: スキーマやワークロードの適応が必要。
- `PARTIAL`: 契約の一部だけ検証可能。
- `UNAVAILABLE`: 再現可能なreader/writerを確認できない。

## 実行

```bash
nix develop
uv sync --frozen
uv run --frozen format-bench run --profile prompt --dataset github-stars-2026-07-03 --fixture
```

`--fixture`は順位対象外のsmoke testです。公開Releaseの全データを使う場合は次の順です。

```bash
uv run --frozen format-bench dataset fetch github-stars-2026-07-03
uv run --frozen format-bench prepare --dataset github-stars-2026-07-03 --run-dir runs/fair-local
uv run --frozen format-bench verify --run-dir runs/fair-local
uv run --frozen format-bench run --profile fair --dataset github-stars-2026-07-03 --run-dir runs/fair-local
uv run --frozen format-bench report --run-dir runs/fair-local
```

測定値そのものはCIの合否に使いません。公開測定はmacOS ARMとLinux x86_64を別runにし、入力hash、commit、flake lock、依存版、seed、writer設定、失敗理由とともに保存します。

結果はまず[`v0.1.0`実測総括](reports/v0.1.0/README.md)を参照し、詳細値は機種別レポートとRelease assetで確認してください。

データはApple系リポジトリに偏り、分類は正解ラベルではありません。過去snapshotの生API応答と分類生成コードが残っていない制約もData Cardに明記しています。

## 参加方法

新しい形式や主張は、一次資料、検証するclaim、適合ワークロード、期待結果、比較可能性をIssueに記載してください。round-tripと検索結果を検証できない速度値は採用しません。作業規則は[`AGENTS.md`](AGENTS.md)、詳しい背景は英語版[`README.md`](README.md)を参照してください。

コードと独自文書はApache-2.0です。GitHub上の第三者メタデータに新しいライセンスは主張しません。
