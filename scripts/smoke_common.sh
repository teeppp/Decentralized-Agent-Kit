# Shared tail for the real-LLM smoke runners (smoke_local_llm.sh,
# smoke_cloud_llm.sh, smoke_llamacpp.sh): boot the overlaid stack, run the
# smoke suite, tear down. Callers keep only their backend-specific preflight.
#
# Usage (after `set -euo pipefail` and cd to the repo root):
#   source scripts/smoke_common.sh
#   run_smoke_stack "${KEEP}" "${COMPOSE[@]}"

run_smoke_stack() {
    local keep="$1"
    shift
    local -a compose=("$@")

    [ -f .env ] || touch .env

    # `up --wait` leaves containers behind when it fails; without this trap a
    # failed boot would strand the overlaid stack on the integration-test
    # ports (8000/8002/...) and break the next plain test run.
    trap '"${compose[@]}" down -v' ERR

    echo "==> Starting the stack..."
    "${compose[@]}" up -d --build --wait

    trap - ERR

    echo "==> Running real-LLM smoke tests..."
    set +e
    (cd tests/integration && uv sync -q && DAK_SMOKE_REAL_LLM=1 uv run pytest test_smoke_real_llm.py -v -p no:cacheprovider)
    local result=$?
    set -e

    if [ "${keep}" != "--keep" ]; then
        echo "==> Tearing down..."
        "${compose[@]}" down -v
    else
        echo "==> Stack left running (BFF: http://localhost:8002)."
    fi

    return "${result}"
}
