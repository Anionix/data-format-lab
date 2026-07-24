# Data Format Lab

データ形式やデータベースの性能主張を、共通契約と形式固有ワークロードで検証する公開研究ラボです。単一の「最強形式」は決めません。

[English](README.md) | [形式選定ガイド](docs/format-selection.md) | [研究ログ](docs/research-log.md) | [データ利用上の注意](DATA_NOTICE.md)

最初のケーススタディは、2026-07-03に固定した公開GitHub Starsメタデータ2,331件・13列です。特定のStarsデータ専用ツールではなく、今後ほかのデータセットや主張を追加できる構成です。

equivalence拡張では、UCI Online Retail II、UCI Bank Marketing、NYC 311、OWID Energy、GeoNames cities500の小さな契約fixtureも扱います。これらは順位対象外です。manifestには公式取得URL、観測したsource hash、schema・NULL規則、正規化判断を記録し、更新され得る完全snapshotはGitではなくRelease assetとして保持します。

## ベンチマークlane

| lane | 検証する問い | 例 |
| --- | --- | --- |
| `fair` | 同じArrowテーブルを保存し、同じ検索結果を返すときの容量と速度 | CSV、JSONL、Arrow IPC、Parquet、Lance、Vortex、適応TsFile |
| `claims` | 公式が主張する強みを、適したワークロードで再現できるか | Lance FTS、Vortex scan、適応TsFile時系列、実験FastLanes証拠 |
| `prompt` | 同じ7項目をLLMへ渡すときの正確なtoken数 | Compact TSV、object JSONL、array JSONL |
| `equivalence` | 一般には同等に見える形式が、このデータとworkloadでも同等か | CSV対TSV、Arrow IPC対Feather、Parquet対ORC、JSONL対row serializer |
| `engine_container` | SQL engineが固有のdatabase fileを操作するときにどう異なるか | SQLite、DuckDB |

異なるlaneや異なる機種の結果は順位比較しません。同一laneの`FULL_COMPARABLE`だけが順位対象です。DuckDBはファイル形式ではなくSQL実行エンジンとして扱います。

equivalence laneは登録済みのpairだけを比較します。native bytes、外部zstd bytes、p50/p95比の区間、IQR、最大RSSを記録します。容量比の区間が±2%、p50が±5%、p95が±10%の境界内なら`PRACTICALLY_EQUIVALENT`、区間が境界をまたぐ場合は`INCONCLUSIVE`です。この判定は、すべてのdatasetやworkloadで同等だという主張ではありません。

Arrow IPCのcodec variant（`none`、`lz4`、`zstd`）は同じArrow schema、往復検証、検索結果契約を使う`fair` lane内の比較です。別形式やlane横断のscoreとしては扱いません。

Parquetのcodec variant（`snappy`、`gzip`、`zstd`、既存の高圧縮設定`zstd-19`）も同じfair laneの規則で比較し、canonical tableの契約を維持します。

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

NixはPython 3.12、`rust-src`付き`nightly-2026-07-15`、`cargo-fuzz`、C/C++ネイティブツールを固定します。Python環境は`uv.lock`で固定します。

```bash
nix develop
uv sync --frozen
uv run --frozen format-bench run --profile prompt --dataset github-stars-2026-07-03 --fixture
uv run --frozen format-bench run --profile equivalence --dataset github-stars-2026-07-03 --fixture --pair csv-tsv
```

`--fixture`は順位対象外のsmoke testです。公開Releaseの全データを使う場合は次の順です。

```bash
uv run --frozen format-bench dataset fetch github-stars-2026-07-03
uv run --frozen format-bench prepare --dataset github-stars-2026-07-03 --run-dir runs/fair-local
uv run --frozen format-bench verify --run-dir runs/fair-local
uv run --frozen format-bench run --profile fair --dataset github-stars-2026-07-03 --run-dir runs/fair-local
uv run --frozen format-bench report --run-dir runs/fair-local
```

native robustness suiteは固定したArrow、Vortex、FastLanesのtargetを記録します。Arrowは記録したsource commitのcheckoutと`native/arrow/build`のbinary、VortexとFastLanesは記録したsource commitと`HEAD`が一致するcheckoutのharnessを使います。FastLanesはcoverage-guidedではなくproject-seededとして扱います。公式native targetを確認できないLance、object JSONL、TsFileも`UNSUPPORTED`証拠として残します。未ビルドbinaryやsource不一致は成功扱いにしません。`--target`は複数指定でき、`--duration-seconds`と`--artifact-budget-mib`で実行上限を指定します。

robustness reportには、targetごとのケース数、PASS/FAIL、crash、timeout、未完了理由、duration p50、artifact/source identityも集約します。これは信頼性の証拠であり、laneをまたぐscoreではありません。

```bash
uv run --frozen format-bench run --profile robustness --suite native --dataset github-stars-2026-07-03 \
  --target vortex-file-io --target vortex-compress-roundtrip --duration-seconds 900
```

手動の[`Native robustness Linux x86_64`](.github/workflows/benchmark-native.yml) workflowは、利用可能なnative targetをmatrixの1 job 1 targetで実行し、保持証拠を1 GiBに制限して14日間uploadします。LinuxとmacOSのartifact名は分離され、native crashやharness failureでも先にraw evidenceを保存してからjobを失敗扱いにします。

dispatchコマンドと証拠確認の手順は[`docs/native-robustness.md`](docs/native-robustness.md)に記録しています。

測定値そのものはCIの合否に使いません。公開測定はmacOS ARMとLinux x86_64を別runにし、入力hash、commit、flake lock、依存版、seed、writer設定、失敗理由とともに保存します。

結果はまず[`v0.1.0`実測総括](reports/v0.1.0/README.md)を参照し、詳細値は機種別レポートとRelease assetで確認してください。

データはApple系リポジトリに偏り、分類は正解ラベルではありません。過去snapshotの生API応答と分類生成コードが残っていない制約もData Cardに明記しています。

## 参加方法

新しい形式や主張は、一次資料、検証するclaim、適合ワークロード、期待結果、比較可能性をIssueに記載してください。round-tripと検索結果を検証できない速度値は採用しません。作業規則は[`AGENTS.md`](AGENTS.md)、詳しい背景は英語版[`README.md`](README.md)を参照してください。

コードと独自文書はApache-2.0です。GitHub上の第三者メタデータに新しいライセンスは主張しません。
