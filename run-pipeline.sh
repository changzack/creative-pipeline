#!/bin/bash
# run-pipeline.sh — Detached pipeline runner
# Runs pipeline.py in background, survives terminal/session closure.
#
# Required env vars (set in .env or export before running):
#   ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY
# Optional:
#   FAL_KEY (for asset generation), LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

set -euo pipefail

# Load .env if present
if [ -f "$(dirname "$0")/.env" ]; then
    set -a
    source "$(dirname "$0")/.env"
    set +a
fi

# Validate required keys
for key in ANTHROPIC_API_KEY OPENAI_API_KEY GOOGLE_API_KEY; do
    if [ -z "${!key:-}" ]; then
        echo "ERROR: $key is not set. Export it or add to .env"
        exit 1
    fi
done

if [ -z "${FAL_KEY:-}" ]; then
    echo "WARNING: FAL_KEY not set — asset generation will be skipped"
fi

NAME="${1:?Usage: $0 <run-name> [extra-args...]}"
shift
LOGFILE="/tmp/pipeline-runs/${NAME}.log"
mkdir -p /tmp/pipeline-runs

echo "Starting pipeline: $NAME"
echo "Log: $LOGFILE"

nohup python3 pipeline.py run --name "$NAME" "$@" > "$LOGFILE" 2>&1 &
PID=$!
disown $PID

echo "Pipeline running as PID $PID"
echo "Monitor: tail -f $LOGFILE"
