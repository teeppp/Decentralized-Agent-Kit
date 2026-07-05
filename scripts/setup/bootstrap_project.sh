#!/usr/bin/env bash
# bootstrap_project.sh — GitHub Project v2 を作成し、DAK 用のカスタムフィールドを整える。
#
# 冪等: 同名 Project が既にあれば再利用し、フィールドも存在すればスキップする。
# 前提: gh CLI が `project` スコープでログイン済み（gh auth status で確認）。
#
# 使い方:
#   bash scripts/setup/bootstrap_project.sh            # 実行
#   DRY_RUN=1 bash scripts/setup/bootstrap_project.sh  # 何をするかだけ表示
#
# 実行後、出力される Project URL を Actions の Variables / Secrets に登録すること:
#   gh variable set DAK_PROJECT_URL --body "<URL>"
#   gh secret   set DAK_PROJECT_TOKEN --body "<project スコープ付き PAT>"
set -euo pipefail

OWNER="${DAK_PROJECT_OWNER:-@me}"
TITLE="${DAK_PROJECT_TITLE:-DAK Sustainability}"
DRY_RUN="${DRY_RUN:-0}"

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN> $*"
  else
    "$@"
  fi
}

echo ">> gh 認証確認"
gh auth status >/dev/null || { echo "gh auth login が必要です"; exit 1; }

echo ">> 既存 Project の検索: '$TITLE'"
PROJECT_NUMBER="$(gh project list --owner "$OWNER" --format json \
  | jq -r --arg t "$TITLE" '.projects[] | select(.title == $t) | .number' | head -n1 || true)"

if [[ -z "${PROJECT_NUMBER:-}" ]]; then
  echo ">> Project を新規作成"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY_RUN> gh project create --owner $OWNER --title \"$TITLE\""
    PROJECT_NUMBER="<new>"
  else
    PROJECT_NUMBER="$(gh project create --owner "$OWNER" --title "$TITLE" --format json | jq -r '.number')"
  fi
else
  echo ">> 既存 Project #$PROJECT_NUMBER を再利用"
fi

# --- カスタムフィールド。Status は新規 Project に既定で存在するので Area/Type/Priority を足す ---
ensure_field() {
  local name="$1" datatype="$2" options="${3:-}"
  local exists=""
  if [[ "$DRY_RUN" != "1" ]]; then
    exists="$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json \
      | jq -r --arg n "$name" '.fields[] | select(.name == $n) | .name' | head -n1 || true)"
  fi
  if [[ -n "$exists" ]]; then
    echo ">> フィールド '$name' は既に存在（スキップ）"
    return
  fi
  echo ">> フィールド '$name' を作成"
  if [[ -n "$options" ]]; then
    run gh project field-create "$PROJECT_NUMBER" --owner "$OWNER" \
      --name "$name" --data-type "$datatype" --single-select-options "$options"
  else
    run gh project field-create "$PROJECT_NUMBER" --owner "$OWNER" \
      --name "$name" --data-type "$datatype"
  fi
}

ensure_field "Area"     SINGLE_SELECT "agent,mcp,bff,cli,infra"
ensure_field "Type"     SINGLE_SELECT "bug,feature,deps,tech-watch,eval,chore"
ensure_field "Priority" SINGLE_SELECT "P0,P1,P2,P3"

PROJECT_URL="$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json 2>/dev/null | jq -r '.url' || echo "<URL>")"
cat <<EOF

完了。
  Project number: $PROJECT_NUMBER
  Project URL   : $PROJECT_URL

次の手順:
  gh variable set DAK_PROJECT_URL --body "$PROJECT_URL"
  gh secret   set DAK_PROJECT_TOKEN --body "<project スコープ付き PAT>"
  bash scripts/setup/seed_backlog.sh   # Phase 2-4 の作業を Issue 化して投入
EOF
