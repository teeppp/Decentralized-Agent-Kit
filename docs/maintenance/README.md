# DAK 持続可能化システム — 運用マニュアル

このリポジトリを継続的・サステナブルに更新し続けるための自動化群の説明。
全体設計は plan file（`DAK Sustainability & Self-Improvement System`）に対応する。

## 判断エンジンの階層

| Tier | 実行者 | 用途 | コスト |
|------|--------|------|--------|
| 0 | 決定論ルール | semver 判定 + CI green/red。自動マージ可否の大半 | 無料・即時 |
| 1 | Ollama 小型 / DAK 自エージェント | changelog リスク・機能差分の一次判定、nightly eval、golden 生成 | 安価（ドッグフード） |
| 2 | `anthropic/claude-code-action` | major/破壊的疑いの精査、機能取り込み提案、新技術ウォッチ、憲章レビュー | 従量 |

## ワークフロー一覧

| ファイル | トリガ | 役割 | Tier |
|----------|--------|------|------|
| `ci.yml` | PR / push(main) | unit マトリクス + fake-LLM 統合（既存） | — |
| `labels.yml` | `labels.yml` 変更 / 手動 | ラベル体系を宣言的に同期 | — |
| `project-autoadd.yml` | Issue/PR open | 新規 Issue/PR を Project に自動追加 | — |
| `dependency-triage.yml` | `pull_request_target`(dependabot) | 依存PRを判定し auto-merge or レビュー要求 | 0→1 |
| `feature-sync.yml` | weekly cron | 依存の新機能を要約し取り込み Issue 起票 | LLM(中立) |
| `tech-watch.yml` | 隔週 cron | 憲章に沿う新技術を探索し提案 Issue 起票 | LLM(中立)+検索 |
| `charter-review.yml` | 四半期 cron | 憲章の見直し Issue 起票 | LLM(中立)+検索 |
| `nightly-eval.yml` | nightly cron | 小型 Ollama で実LLMスモークを実行し pass-rate 記録 | 1 |
| `capture-golden.yml` | 手動 / nightly | 実LLMセッションを決定論テスト化して PR 提案 | 1 |

## 初期セットアップ（一度だけ）

1. **Project 作成**: `bash scripts/setup/bootstrap_project.sh`
   → 出力された URL を登録:
   - `gh variable set DAK_PROJECT_URL --body "<URL>"`
   - `gh secret set DAK_PROJECT_TOKEN --body "<project スコープ付き PAT>"`（`project-autoadd` が user-level Project に書くため、既定 `GITHUB_TOKEN` では不可）
2. **バックログ投入**: `bash scripts/setup/seed_backlog.sh`（Phase 2-4 を Issue 化）
3. **ラベル同期**: `labels.yml` を main に push（`labels.yml` ワークフローが反映）
4. **リポジトリ設定**:
   - Settings → General → Pull Requests → **Allow auto-merge** を ON
   - Settings → Branches → `main` の branch protection で **CI を必須チェック** に
5. **LLM プロバイダ設定（provider 中立・実行時選択）**: reasoning 系ワークフロー
   （tech-watch / feature-sync / charter-review）と triage の LLM リスク評価は、以下の
   env で任意のプロバイダを選ぶ（Gemini / Ollama / OpenAI / Anthropic すべて OpenAI 互換で叩ける）:
   - `gh variable set MAINT_LLM_BASE_URL --body "<base url>"`
   - `gh variable set MAINT_LLM_MODEL --body "<model id>"`
   - `gh secret set MAINT_LLM_API_KEY --body "<api key>"`（Ollama は任意の値でOK）
   - プリセット例（2026-08 時点の参考価格 in/out per 1M tok）:
     - **OpenAI**: `https://api.openai.com/v1` / `gpt-5.6-luna`（$0.20/$1.20 — **有料の第一推奨**。tool calling 対応・1M ctx でこの価格帯では最も能力/コスト比が良い。さらに絞るなら `gpt-5-nano` $0.05/$0.40）
     - **Gemini**: `https://generativelanguage.googleapis.com/v1beta/openai` / `gemini-3.5-flash-lite`（$0.30/$2.50、AI Studio 無料枠あり — **ゼロコスト運用ならこれ**。tool 信頼性は 2.5-lite より向上。品質重視なら `gemini-3.7-flash` $0.75/$3.75 プロモ価格・無料枠あり。※2.5 系は世代落ちで Vertex 側は 2026-10 引退予定のため新規設定では避ける）
     - **Ollama**: `http://<host>:11434/v1` / `llama3.1:8b`（無料・要ホスト）
   - **triage で LLM 評価も使う場合**は上記を **Dependabot secrets/variables にも登録**
     （Dependabot PR には通常の Actions secrets が渡らないため）。未設定なら triage は
     heuristic（キーワード）評価にフォールバックし、reasoning 系は提案 0 件で失敗しない。
   - **Web 検索は Tavily を使用**: `gh secret set TAVILY_API_KEY`（+ Dependabot は不要）。
     `tech-watch` / `charter-review` は Web 検索が必須なので、未設定だと提案 0 件になる
     （`feature-sync` は changelog ベースなので Tavily 不要）。
     ※ 規約遵守のため DuckDuckGo 等の HTML スクレイピングは行わない。

## エスカレーション経路（依存更新）

```
Dependabot PR
  └─ CI (ci.yml) 完了
       └─ dependency-triage.yml
            ├─ Tier0: semver 判定 + CI 結果
            │    ├─ patch/minor + green + 非破壊 → auto-merge-candidate → gh pr merge --auto
            │    └─ それ以外 → 次へ
            └─ Tier2(必要時): changelog/CVE 精査
                 └─ needs-human-review ラベル + リスク要約コメント + Project 追跡
```

## 注意・既知の制約

- **Dependabot と secrets**: 上記のとおり両方のストアに登録が必要。
- **project-autoadd と Dependabot**: 以前 `project-autoadd.yml` は `pull_request`（`_target`
  ではない）で動いており、Dependabot が起点のイベントは Dependabot secrets ストアからしか
  secrets が供給されないため、通常の Actions secrets である `DAK_PROJECT_TOKEN` が空になって
  必ず失敗していた。このジョブは PR コードの checkout を一切行わない（GitHub API 呼び出しのみ）
  ため `pull_request_target` に切り替えても信頼できないコード実行のリスクがなく、常に通常の
  Actions secrets が使われるようになった（`dependency-triage.yml` と同じ設計）。
- **Ollama on CPU は遅い**: nightly 限定・小型モデル・寛容アサーション・モデル cache。PR ゲートには載せない。
- **提案ノイズ**: `tech-watch`/`feature-sync` は 1 実行あたり件数上限と重複検出を持たせる。
