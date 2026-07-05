---
description: 依存更新を maintenance トリアージエンジンで判定する
---
`maintenance/` のトリアージエンジンで依存更新を判定します（CI と同じ方針）。

引数（`$ARGUMENTS` に `<package> <from> <to> [ci_passed]` の形で渡される想定）を解釈し、
無ければ対象の Open な Dependabot PR を `gh pr list --label deps` で探して聞き返してください。

手順:
1. `cd maintenance && uv sync`
2. changelog を可能なら取得（`--fetch-changelog`）。判定を実行:
   ```
   uv run dak-maint triage --package <pkg> --from <from> --to <to> --ci-passed <true|false> --fetch-changelog
   ```
3. 出力の `decision.action`（auto-merge / needs-human-review）と理由を要約して報告。
4. auto-merge 妥当なら `gh pr merge --auto --squash <PR>` を提案（実行前に確認）。

方針: patch/minor かつ CI green かつ SAFE のときだけ auto-merge。major/破壊的/CI赤 は人間レビュー。
