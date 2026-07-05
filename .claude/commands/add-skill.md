---
description: 新しい DAK スキル(SKILL.md + tools.py)を雛形から作る
---
新しい DAK スキルを作成します。`$ARGUMENTS` にスキル名（snake_case）を取ります。

参考実装: `agent/skills/solana_wallet/`（SKILL.md フロントマター + tools.py の関数群）、
`agent/skills/dependency_maintenance/`（自己保守スキル）。

手順:
1. `agent/skills/<name>/SKILL.md` を作成:
   - フロントマター `name`, `description`, `tools:`（公開する関数名の一覧）
   - 本文にエージェント向けの使い方・制約（原則: 暗黙の副作用を持たせない）
2. `agent/skills/<name>/tools.py` に、文字列を返すツール関数を実装。
   docstring は LLM が読む前提で引数・戻り値を明記。
3. `agent/tests/skills/` に読み込み/動作の単体テストを追加（既存 `test_*` を参考）。
4. 単体テストと、必要なら統合テストで動作確認。

「System ENABLES, Agent DECIDES」を守り、危険操作は Observation を返して判断をエージェントに委ねること。
