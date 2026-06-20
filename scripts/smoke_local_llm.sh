#!/usr/bin/env bash
# Real-LLM smoke verification against a local Ollama model (no API keys).
#
# Runs the full Docker stack with the agents pointed at the HOST's Ollama
# (Metal-accelerated on macOS), then executes the real-LLM smoke tests.
#
# Usage:
#   ./scripts/smoke_local_llm.sh                 # default model (llama3.1:8b)
#   LOCAL_OLLAMA_MODEL=mistral-nemo ./scripts/smoke_local_llm.sh
#   ./scripts/smoke_local_llm.sh --keep          # leave the stack running
#
# Default is llama3.1:8b: it reliably emits structured tool calls under a
# multi-tool prompt and has no "thinking" phase, so turns stay under the 120s
# client timeout. Qwen3.5 degrades to raw-JSON-text tool calls; qwen3:8b's
# <think> blocks can blow the per-turn timeout on modest (16GB) hardware.

set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${LOCAL_OLLAMA_MODEL:-llama3.1:8b}"
export LOCAL_MODEL_NAME="ollama_chat/${MODEL}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.local-llm.yml)
KEEP="${1:-}"

echo "==> Checking host Ollama..."
if ! curl -sf --max-time 3 http://localhost:11434/api/version > /dev/null; then
    echo "Ollama is not running on the host. Start it first (e.g. 'ollama serve' or the menu-bar app)." >&2
    exit 1
fi

if ! ollama list | awk '{print $1}' | grep -qx "${MODEL}"; then
    echo "==> Pulling ${MODEL}..."
    ollama pull "${MODEL}"
fi

echo "==> Warming up ${MODEL} (loads weights into memory)..."
curl -sf http://localhost:11434/api/generate \
    -d "{\"model\": \"${MODEL}\", \"prompt\": \"hi\", \"stream\": false}" > /dev/null

[ -f .env ] || touch .env

echo "==> Starting the stack (model: ${LOCAL_MODEL_NAME})..."
"${COMPOSE[@]}" up -d --build --wait

echo "==> Running real-LLM smoke tests..."
set +e
(cd tests/integration && uv sync -q && DAK_SMOKE_REAL_LLM=1 uv run pytest test_smoke_real_llm.py -v -p no:cacheprovider)
RESULT=$?
set -e

if [ "${KEEP}" != "--keep" ]; then
    echo "==> Tearing down..."
    "${COMPOSE[@]}" down -v
else
    echo "==> Stack left running (BFF: http://localhost:8002)."
fi

exit "${RESULT}"
