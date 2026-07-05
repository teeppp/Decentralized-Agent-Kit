---
description: 統合/ゴールデン/実LLMスモークを実行する
---
DAK のテストを実行します。`$ARGUMENTS` に `unit|integration|golden|smoke` を取れます（既定 integration）。

- unit: 各コンポーネントで `uv run pytest -q`（agent/cli/bff/mcp-server/maintenance）。
- integration / golden: fake-LLM スタックを起動して統合テスト:
  ```
  docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait
  cd tests/integration && uv sync && uv run pytest -q            # golden 指定時は test_golden_replay.py
  docker compose -f docker-compose.yml -f docker-compose.test.yml down -v
  ```
- smoke: `./scripts/smoke_local_llm.sh`（Ollama 必要、`DAK_SMOKE_REAL_LLM=1`）。

失敗時はログを要約し、原因の当たりを付けて報告してください。
