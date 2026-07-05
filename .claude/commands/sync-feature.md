---
description: 依存の新機能を調べ、取り込み提案をまとめる
---
指定した依存（`$ARGUMENTS` に package 名。無ければ最近の `deps(` コミットから選ぶ）の
**新機能**（バグ修正ではなく）を調べ、DAK への取り込み提案をまとめます。

手順:
1. WebFetch/WebSearch で対象の release notes を調べ、新機能を列挙。
2. `docs/CHARTER.md` のスコープ・採用基準に照らして取り込み価値を判断。
3. `gh issue list --label feature-sync --state open` で重複確認。
4. 価値があり重複しなければ、Issue ドラフト（タイトル `Adopt <機能> in <dep> v<ver>`、
   本文に対象コンポーネント・導入スケッチ・参照リンク）を提示。ユーザ確認後に
   `gh issue create --label feature-sync` で起票。
