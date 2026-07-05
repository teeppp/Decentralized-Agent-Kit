# dak-maintenance

DAK が自分自身を保守するためのツールキット（要件2/3のドッグフード実装）。

- `semver` — Dependabot PR の from/to バージョンから bump レベルを判定（Tier0, LLM不要）
- `changelog` — GitHub Releases / PyPI から changelog を取得
- `risk` — changelog のリスク評価。ヒューリスティック（LLM不要）と LLM の両対応
- `decide` — bump × CI結果 × リスク → `auto-merge` か `needs-human-review` を理由付きで返す
- `llm_client` — **provider 中立**な `complete()`（Gemini/Ollama/OpenAI/… を `MAINT_LLM_*` で実行時選択）
- `search` — Web 検索（**Tavily API**。LLM とは分離。規約遵守のためスクレイピングはしない）
- `watch` / `feature` / `charter` — tech-watch / feature-sync / charter-review の提案パイプライン
- `cli` — `dak-maint {triage,watch,feature-sync,charter-review}`（ワークフローから呼ぶ）

同じロジックは `agent/skills/dependency-maintenance/` の DAK スキルからも利用でき、
DAK 自エージェントが対話的にトリアージを実行できる。

## 使い方

```bash
cd maintenance && uv sync
uv run pytest -q

# 単発トリアージ（LLMなし・ヒューリスティックのみ）
uv run dak-maint triage --package litellm --from 1.51.0 --to 1.52.3 --ci-passed true

# provider 中立の LLM（例: ローカル Ollama。Gemini/OpenAI も同様に BASE_URL/MODEL を変えるだけ）
export MAINT_LLM_BASE_URL="http://localhost:11434/v1"
export MAINT_LLM_MODEL="llama3.1:8b"
export MAINT_LLM_API_KEY="ollama"
uv run dak-maint watch --charter ../docs/CHARTER.md --max-items 2   # 新技術提案 JSON
```

判定は「Tier0(semver+CI) で大半を決め、曖昧な時だけ LLM に委ねる」設計。
`--assessor llm` で triage のリスク評価も LLM 化。reasoning 系（watch/feature-sync/charter-review）は
`MAINT_LLM_*` 未設定なら提案 0 件を返す（失敗しない）。Web 検索は Tavily（`TAVILY_API_KEY`）。
`watch` を実際に候補生成させるには Tavily キーが必要（未設定なら検索 0 件＝提案 0 件）。
