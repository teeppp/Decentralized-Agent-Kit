# DAK 持続可能化システム — 設計書

> このリポジトリを**継続的・サステナブルに自己更新し続ける**ための仕組みの設計。
> アーキテクチャ図: [`architecture.drawio`](./architecture.drawio)（diagrams.net で開く / 2ページ構成）。
> 運用手順は [`README.md`](./README.md)、目的の判断軸は [`../CHARTER.md`](../CHARTER.md)。

## 1. 目的とゴール（要件との対応）

| # | 要件 | 実現手段 |
|---|------|----------|
| 1 | GitHub Project / Issue を活用 | Issue/PR テンプレ・labels・CODEOWNERS・**Project を単一の真実**にする自動投入 + bootstrap/seed |
| 2 | 脆弱性更新の自動判定・自動更新 | Dependabot → `dependency-triage` が **semver×CI×リスク** で判定し安全なものだけ auto-merge |
| 3 | 機能更新の迅速な取り込み | `feature-sync` が release notes の**新機能**を要約し取り込み Issue 化 |
| 4 | 新技術の目的ベース提案・目的の定期見直し | `docs/CHARTER.md`（憲章）+ `tech-watch`（隔週）+ `charter-review`（四半期） |
| 5 | Claude 自身がより高度に扱える | `CLAUDE.md`・`.claude/commands`・権限 allowlist・保守ロジックの **DAK スキル化** |
| 6 | 使うほど自動化が進む継続テスト | `nightly-eval`（小型 Ollama）+ **golden capture/replay**（決定論回帰が自動増殖） |

## 2. 設計の核: 階層型（Tiered）判断エンジン

コストと品質を両立するため、判断を 3 層に分ける。**大半は無料の Tier0 で決まり**、
必要なときだけ上位に委ねる。

| Tier | 実行者 | 使いどころ | コスト |
|------|--------|-----------|--------|
| **0** | 決定論ルール（`semver` + CI 結果） | auto-merge 可否の一次判定 | 無料・即時 |
| **1** | Ollama 小型モデル / DAK 自エージェント | changelog リスクの一次評価、nightly eval、golden 生成 | 安価（ドッグフード） |
| **LLM（provider 中立）** | 任意プロバイダ（Gemini / Ollama / OpenAI / …）を **実行時に選択** | major/破壊的の精査、機能取り込み提案、新技術ウォッチ、憲章レビュー | 選んだプロバイダ次第（Ollama なら無料） |

**重要（設計の是正）**: reasoning 系は当初 `claude-code-action`（Anthropic 固定）にしていたが、
本 repo は Gemini 既定＆ LiteLLM でマルチ LLM 中立という思想。そこで **ベンダ非依存**に作り直した。
すべての主要プロバイダは OpenAI 互換 `/chat/completions` を持つため、httpx 一本（litellm 不要）で
`MAINT_LLM_BASE_URL/MODEL/API_KEY` を切り替えるだけでプロバイダを選べる。Web 検索は LLM と分離し、
`TAVILY_API_KEY` があれば Tavily、無ければ DuckDuckGo（キー不要）にフォールバックする。

この階層は要件2（「repo 自身の機能で」= ドッグフード）と要件6（「Ollama 軽量テスト」）の
両方を同時に満たす。**tech-watch を Ollama `llama3.1:8b` + DuckDuckGo で実機検証済み**（API キー不要で提案生成）。

## 3. コンポーネント構成

```
.github/
  ISSUE_TEMPLATE/ · PULL_REQUEST_TEMPLATE.md · CODEOWNERS · labels.yml   ← Phase1 基盤
  dependabot.yml                                                          ← Phase2 依存検知
  workflows/
    ci.yml                  (既存: unit + fake-LLM integration。matrix に maintenance 追加)
    labels.yml              ラベル宣言同期
    project-autoadd.yml     新 Issue/PR を Project へ
    dependency-triage.yml   Phase2: 依存判定 + auto-merge
    feature-sync.yml        Phase2/要件3: 新機能取り込み提案
    tech-watch.yml          Phase3: 新技術ウォッチ
    charter-review.yml      Phase3: 憲章の四半期見直し
    nightly-eval.yml        Phase4/要件6: 小型 Ollama 実LLMスモーク
    capture-golden.yml      Phase4/要件6: 実セッションを golden 化して PR 提案
maintenance/                Phase2: 独立 Python パッケージ（判断エンジン本体）
  src/dak_maintenance/{semver,risk,decide,changelog,llm_client,cli}.py
  tests/                    29 unit tests
agent/skills/dependency_maintenance/   要件5: 同じ判定を DAK エージェントが実行（ドッグフード）
docs/
  CHARTER.md                目的憲章（判断軸）
  maintenance/{README,DESIGN,architecture.drawio}
  eval/{README.md,history.jsonl}
tests/integration/
  golden/*.json             決定論回帰コーパス（増える）
  test_golden_replay.py     golden を fake-LLM で再生
  tools/capture_golden.py   実LLMセッション → golden 変換
scripts/setup/
  bootstrap_project.sh      Project v2 作成 + フィールド
  seed_backlog.sh           Phase2-4 を Issue 化して Project 投入
```

## 4. 判断エンジン（`maintenance/dak_maintenance`）

疎結合の独立パッケージ（`httpx` のみ依存、CLI `dak-maint`）。3 つの純関数が核:

- `classify_update(from, to) -> BumpLevel` … semver 判定（**Tier0**、LLM 不要）。
  `0.x` は minor 変化も破壊的とみなす保守設計。
- `assess_risk(pkg, from, to, changelog, assessor) -> RiskVerdict` … changelog リスク評価。
  - `HeuristicAssessor`（**Tier1**、キーワード走査、常に使える）
  - `LLMAssessor`（**Tier1/2**、注入した `complete(prompt)->str` に委譲。不正応答時は heuristic にフォールバック）
- `decide(bump, ci_passed, risk) -> Decision` … 承認方針を**唯一の場所**にまとめる:
  - `patch/minor` かつ `CI green` かつ `SAFE` → **auto-merge**
  - それ以外（major/unknown、CI 赤、risky/breaking/unknown risk）→ **needs-human-review**

テストは `complete` を fake 化するので、ネットワークもモデルも不要（29 tests）。
同じ関数群を DAK スキルが import（無ければ self-contained fallback）し、**エージェントも同一方針で判定**できる。

## 5. 主要フロー

### 5-1. 依存更新（要件2/3）— 図②参照

```
Dependabot PR
 └ ci.yml（unit + fake-LLM integration）
     └ dependency-triage.yml  (pull_request_target: base の信頼コードのみ実行)
         ├ Tier0: classify_update + CI 結果
         │   ├ patch/minor → assess_risk（Tier1、必要なら Tier2 へ escalate）
         │   │     └ SAFE → gh pr merge --auto --squash（+ auto-merge-candidate）
         │   │     └ それ以外 → needs-human-review + リスク要約コメント
         │   └ major/unknown/none または CI 赤 → needs-human-review
         └ すべて GitHub Project に追跡
```

- **セキュリティ**: `pull_request_target` は base ブランチのコードのみ checkout・実行し、PR の
  信頼できないコードは動かさない。Dependabot イベントの秘密情報は **Dependabot secrets** ストアから供給。
- **実マージの安全**: `gh pr merge --auto` は branch protection の必須チェック（CI）が green に
  なるまで GitHub 側が保留する。ワークフローは可否を決めるだけ。
- **機能取り込み（要件3）**: `feature-sync` が週次で release notes の**新機能のみ**を Tier2 で要約し、
  `feature-sync` Issue を起票（重複検出・件数上限つき）。

### 5-2. 新技術ウォッチと目的の見直し（要件4）

- `tech-watch`（隔週）: `dak-maint watch` が (1) LLM で憲章から検索クエリ生成 →
  (2) Web 検索（Tavily/DuckDuckGo）で候補収集 → (3) LLM で憲章の採用基準に照らし評価 →
  基準を満たすものだけ `tech-watch` Issue 化（重複検出・件数上限つき）。LLM は provider 中立。
- `charter-review`（四半期）: landscape 変化を踏まえ憲章そのものの改訂案 Issue を起票。
  → **初期の目的に縛られず、目的自体を定期的に更新**する（要件4後段）。

### 5-3. 継続テストと「使うほど育つ」ループ（要件6）— 設計の要点

2 層のテストが噛み合う:

1. **決定論 golden replay**（PR CI・高速・実LLM不要）
   `golden/*.json` を fake-LLM の制御API（`/script`）で再生し、ツール呼び出しの回帰を検出。
2. **nightly 実LLM eval**（夜間・小型 Ollama・寛容アサーション）
   小型モデルで gated スモークを実行し pass-rate を `history.jsonl` に追記（PR ゲートではない傾向シグナル）。

**育つ仕組み**:

```
実LLMスモークで新しい成功セッション
 └ capture_golden.py が観測したツール系列を golden に凍結
     └ capture-golden ワークフローが PR 提案
         └ マージで PR CI の決定論回帰スイートが増える  ← 使うほどテストが増殖
```

fake-LLM がモデル名ごとに応答をスクリプトできること（`/script/{model}`, `/requests/{model}`）が、
実行を決定論に固定する継ぎ目。

## 6. GitHub Project を単一の真実に（要件1）

- `scripts/setup/bootstrap_project.sh` が Project v2 とカスタムフィールド（Status/Area/Type/Priority）を冪等作成。
- `scripts/setup/seed_backlog.sh` が Phase2-4 の作業を Issue 化して Project に投入。
- `project-autoadd.yml` が以後の新 Issue/PR を自動追加（未設定時はスキップして CI を汚さない）。
- すべての自動化アウトプット（auto-merge PR・レビュー要求・各種提案 Issue）が Project に集約される。

## 7. セットアップ（マージ後・コード外の手動作業）

1. `bash scripts/setup/bootstrap_project.sh` → `gh variable set DAK_PROJECT_URL` / `gh secret set DAK_PROJECT_TOKEN`
2. `bash scripts/setup/seed_backlog.sh`
3. Settings: **Allow auto-merge** ON、`main` の branch protection で CI を必須チェックに
4. **LLM プロバイダを選択**（provider 中立）: `MAINT_LLM_BASE_URL` / `MAINT_LLM_MODEL`（variables）
   と `MAINT_LLM_API_KEY`（secret）を設定。Gemini なら既存 `GOOGLE_API_KEY` を流用（プリセットは README 参照）。
   triage で LLM 評価も使うなら **Dependabot secrets/variables にも**登録。未設定でも
   reasoning 系は提案 0 件・triage は heuristic で失敗しない。
5. （任意）オープンWeb検索を強化するなら `TAVILY_API_KEY` を登録（無ければ DuckDuckGo）。

## 8. 設計上のトレードオフ・既知の制約

- **Dependabot と secrets**: 通常の Actions secrets が渡らないため両ストア登録が前提。
- **CPU の Ollama は遅い**: nightly 限定・小型モデル・寛容アサーション・モデル cache。PR ゲートには載せない。
- **提案ノイズ**: `tech-watch`/`feature-sync` は 1 実行あたり件数上限と重複検出で抑制。
- **changelog 取得のベストエフォート**: 取得不能時は risk=UNKNOWN → 保守的に人間レビューへ。
- **DAK スキルの二重実装**: 独立コンテナ原則のため、toolkit import 優先・不可なら inline fallback。
  CI の `maintenance/` を真実とし、乖離に注意（スキル内コメントで明示）。
