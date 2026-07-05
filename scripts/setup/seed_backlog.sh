#!/usr/bin/env bash
# seed_backlog.sh — Phase 2-4 の各成果物を Issue 化し、GitHub Project に投入する。
# 「この時点で全ての作業を Project 管理へ移す」ための一括シード。
#
# 冪等: 同一タイトルの Open Issue が既にあれば作成をスキップする。
# 前提: bootstrap_project.sh 実行済み。DAK_PROJECT_URL を環境 or gh variable で解決。
#
# 使い方:
#   bash scripts/setup/seed_backlog.sh
#   DRY_RUN=1 bash scripts/setup/seed_backlog.sh
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
OWNER="${DAK_PROJECT_OWNER:-@me}"
PROJECT_URL="${DAK_PROJECT_URL:-$(gh variable get DAK_PROJECT_URL 2>/dev/null || true)}"

run() { if [[ "$DRY_RUN" == "1" ]]; then echo "DRY_RUN> $*"; else "$@"; fi; }

# create_issue <title> <label-csv> <body>
create_issue() {
  local title="$1" labels="$2" body="$3"
  local existing
  existing="$(gh issue list --state open --search "$title in:title" --json title \
    | jq -r --arg t "$title" '.[] | select(.title == $t) | .title' | head -n1 || true)"
  if [[ -n "$existing" ]]; then
    echo ">> Issue 既存（スキップ）: $title"
    return
  fi
  echo ">> Issue 作成: $title"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN> gh issue create --title \"$title\" --label \"$labels\""
    return
  fi
  local url
  url="$(gh issue create --title "$title" --label "$labels" --body "$body")"
  echo "   -> $url"
  if [[ -n "$PROJECT_URL" ]]; then
    gh project item-add "${PROJECT_URL##*/}" --owner "$OWNER" --url "$url" >/dev/null || \
      echo "   (project item-add に失敗。DAK_PROJECT_URL/権限を確認)"
  fi
}

# ---- Epic ----
create_issue "Epic: 持続可能化システム (Phase 2-4)" "automation" \
"計画: docs/maintenance/README.md / plan file を参照。

- [ ] Phase 2: 依存自動化 (Dependabot + triage engine)
- [ ] Phase 3: 憲章 + tech-watch
- [ ] Phase 4: 継続テスト + Claude 強化
"

# ---- Phase 2 ----
create_issue "Phase 2: Dependabot 設定 (uv x5 + github-actions)" "deps,automation" \
"5 つの pyproject ディレクトリと github-actions に対する .github/dependabot.yml を追加。"
create_issue "Phase 2: トリアージエンジン maintenance/ (classify/assess/decide)" "deps,automation" \
"semver 判定 + changelog リスク評価 + 判断ロジック。fake-LLM/モックで単体テスト。"
create_issue "Phase 2: dependency-triage ワークフロー + 安全な自動マージ" "deps,automation" \
"workflow_run 連携で CI 後に判定。patch/minor+green+非破壊は auto-merge。"
create_issue "Phase 2: feature-sync ワークフロー (新機能取り込み提案)" "feature-sync,automation" \
"更新依存の release notes から新機能を要約し Issue 起票（要件3）。"
create_issue "Phase 2: DAK スキル化 (dependency-maintenance)" "deps,automation" \
"maintenance/ を agent/skills/ の SKILL.md として公開しドッグフード。"

# ---- Phase 3 ----
create_issue "Phase 3: docs/CHARTER.md 初版" "charter" \
"README/AGENTS.md/gap分析から目的憲章を起草。四半期見直しサイクルを定義。"
create_issue "Phase 3: tech-watch ワークフロー (隔週)" "tech-watch,automation" \
"憲章を軸に新技術を探索し提案 Issue を起票（件数上限・重複検出つき）。"
create_issue "Phase 3: charter-review ワークフロー (四半期)" "charter,automation" \
"landscape 変化と憲章改訂案を提示する Issue を起票。"

# ---- Phase 4 ----
create_issue "Phase 4: nightly-eval (小型 Ollama 継続テスト)" "eval,automation" \
"CPU ランナーで小型モデルを起動しゲート済みスモークを実行、pass-rate を記録。"
create_issue "Phase 4: golden capture/replay (育つテスト資産)" "eval,automation" \
"実LLMセッションを決定論的 fake-LLM テストへ凍結する仕組み。"
create_issue "Phase 4: Claude 強化 (CLAUDE.md, .claude/commands, settings)" "automation" \
"repo 特化ガイド・スラッシュコマンド・権限 allowlist。"

echo "完了。gh project item-list \"${PROJECT_URL##*/}\" --owner $OWNER で確認できます。"
