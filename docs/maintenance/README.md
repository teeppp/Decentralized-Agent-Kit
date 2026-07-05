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
| `dependency-triage.yml` | CI 完了(`workflow_run`) | 依存PRを判定し auto-merge or レビュー要求 | 0→2 |
| `feature-sync.yml` | weekly cron | 依存の新機能を要約し取り込み Issue 起票 | 2 |
| `tech-watch.yml` | 隔週 cron | 憲章に沿う新技術を探索し提案 Issue 起票 | 2 |
| `charter-review.yml` | 四半期 cron | 憲章の見直し Issue 起票 | 2 |
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
5. **Secrets 登録**（Tier2 用）: `ANTHROPIC_API_KEY`（または `CLAUDE_CODE_OAUTH_TOKEN`）を
   - **Actions secrets** と
   - **Dependabot secrets** の両方に登録
     （Dependabot PR には通常の Actions secrets が渡らないため。`dependency-triage` は `workflow_run` 連携でこれを回避するが、Tier2 呼び出しには必要）

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
- **Ollama on CPU は遅い**: nightly 限定・小型モデル・寛容アサーション・モデル cache。PR ゲートには載せない。
- **提案ノイズ**: `tech-watch`/`feature-sync` は 1 実行あたり件数上限と重複検出を持たせる。
