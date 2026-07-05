# dak-maintenance

DAK が自分自身を保守するためのツールキット（要件2/3のドッグフード実装）。

- `semver` — Dependabot PR の from/to バージョンから bump レベルを判定（Tier0, LLM不要）
- `changelog` — GitHub Releases / PyPI から changelog を取得
- `risk` — changelog のリスク評価。ヒューリスティック（Tier1）と LLM（Tier1 Ollama / Tier2 Claude）の両対応
- `decide` — bump × CI結果 × リスク → `auto-merge` か `needs-human-review` を理由付きで返す
- `cli` — `dak-maint triage ...`（ワークフローから呼ぶ）

同じロジックは `agent/skills/dependency-maintenance/` の DAK スキルからも利用でき、
DAK 自エージェントが対話的にトリアージを実行できる。

## 使い方

```bash
cd maintenance && uv sync
uv run pytest -q

# 単発トリアージ（LLMなし・ヒューリスティックのみ）
uv run dak-maint triage --package litellm --from 1.51.0 --to 1.52.3 --ci-passed true
```

判定は「Tier0(semver+CI) で大半を決め、曖昧な時だけ上位 Tier に委ねる」設計。
`--changelog-file` を渡すとヒューリスティック評価、`ASSESSOR=llm` + LLM 設定で LLM 評価に切替。
