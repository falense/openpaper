#!/bin/bash
set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <run-id> [test_flow.py args...]"
    echo ""
    echo "Examples:"
    echo "  $0 baseline --verbose"
    echo "  $0 v2-skill --agent-model claude-sonnet-4-6"
    echo ""
    echo "  # Parallel runs"
    echo "  $0 baseline --verbose &"
    echo "  $0 v2-skill --verbose &"
    echo "  wait"
    exit 1
fi

RUN_ID="$1"
shift

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CACHE_MOUNT="/home/sondre/Repositories/OpenPaper/.openpaper/cache"

mkdir -p "$PROJECT_DIR/output/$RUN_ID"
mkdir -p "$PROJECT_DIR/overrides/$RUN_ID"

echo "[$RUN_ID] Starting test run"

docker compose --profile test run --rm \
    --name "openpaper-test-${RUN_ID}" \
    -v "$PROJECT_DIR/output/$RUN_ID:/output" \
    -v "$PROJECT_DIR/overrides/$RUN_ID:/overrides:ro" \
    test \
    uv run scripts/test_flow.py --run-id "$RUN_ID" --verbose "$@"

echo "[$RUN_ID] Done — output at output/$RUN_ID/"
