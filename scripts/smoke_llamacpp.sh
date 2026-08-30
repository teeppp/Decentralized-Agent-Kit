#!/usr/bin/env bash
# Real-LLM smoke verification against a llama.cpp server (no API keys).
#
# Unlike smoke_local_llm.sh (which manages Ollama), this script does NOT start
# llama-server — it only verifies one is reachable, then runs the smoke suite
# against it. Start the server wherever the GPU is first (local Metal build,
# Colab VM behind an SSH forward, or a LAN GPU box behind ssh -L); recipes in
# docs/guides/local_llm_llamacpp.md.
#
# Usage:
#   ./scripts/smoke_llamacpp.sh                    # expects llama-server at :18080
#   LLAMACPP_PORT=8080 ./scripts/smoke_llamacpp.sh
#   ./scripts/smoke_llamacpp.sh --keep             # leave the stack running

set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${LLAMACPP_PORT:-18080}"
export LLAMACPP_API_BASE="${LLAMACPP_API_BASE:-http://host.docker.internal:${PORT}/v1}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.llamacpp.yml)
KEEP="${1:-}"

echo "==> Checking llama-server on localhost:${PORT}..."
if ! curl -sf --max-time 3 "http://localhost:${PORT}/health" > /dev/null; then
    cat >&2 <<EOF
No llama-server reachable at http://localhost:${PORT}.

Start one first (see docs/guides/local_llm_llamacpp.md), e.g.:
  * This machine (Metal/CUDA):
      llama-server -hf bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M \\
                   --port ${PORT} --jinja -c 8192
  * Colab GPU VM (google-colab-cli): ssh -N colab-llm   # LocalForward ${PORT}
  * LAN GPU server: ssh -N -L ${PORT}:localhost:8080 <gpu-host>
EOF
    exit 1
fi

echo "==> Warming up (loads weights / verifies completion path)..."
curl -sf --max-time 120 "http://localhost:${PORT}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model": "llamacpp", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4}' > /dev/null \
    || { echo "llama-server answered /health but not /v1/chat/completions." >&2; exit 1; }

[ -f .env ] || touch .env

echo "==> Starting the stack (endpoint: ${LLAMACPP_API_BASE})..."
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
