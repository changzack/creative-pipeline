#!/bin/bash
# Run pipeline.py as a detached process (survives OpenClaw session cleanup)
# Usage: ./run-pipeline.sh run --brief path/to/brief.md --name my-run
#        ./run-pipeline.sh resume --thread my-run --decision approve
#        ./run-pipeline.sh status --thread my-run

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin/activate"
LOG_DIR="/tmp/pipeline-runs"
mkdir -p "$LOG_DIR"

# Extract run name for log file
RUN_NAME="pipeline"
for arg in "$@"; do
    if [[ "$prev" == "--name" || "$prev" == "--thread" ]]; then
        RUN_NAME="$arg"
        break
    fi
    prev="$arg"
done

LOG_FILE="$LOG_DIR/$RUN_NAME.log"

if [[ "$1" == "status" ]]; then
    # Status is quick — run inline
    source "$VENV"
    export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY is required (set in .env or export before running)}"
    export OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY is required (set in .env or export before running)}"
    export GOOGLE_API_KEY="${GOOGLE_API_KEY:?GOOGLE_API_KEY is required (set in .env or export before running)}"
    export FAL_KEY="${FAL_KEY:?FAL_KEY is required (set in .env or export before running)}"
    export LANGFUSE_HOST="http://localhost:3000"
    export LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:?LANGFUSE_PUBLIC_KEY is required (set in .env or export before running)}"
    export LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:?LANGFUSE_SECRET_KEY is required (set in .env or export before running)}"
    cd "$SCRIPT_DIR"
    python3 pipeline.py "$@"
    exit $?
fi

# Run/Resume — fully detach via nohup to survive parent kill
echo "Starting pipeline (fully detached)..."
echo "Log: $LOG_FILE"

# Write a runner script that nohup will execute
RUNNER="/tmp/pipeline-runs/$RUN_NAME.runner.sh"
cat > "$RUNNER" << RUNNER_EOF
#!/bin/bash
source "$VENV"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY is required (set in .env or export before running)}"
export OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY is required (set in .env or export before running)}"
export GOOGLE_API_KEY="${GOOGLE_API_KEY:?GOOGLE_API_KEY is required (set in .env or export before running)}"
export FAL_KEY="${FAL_KEY:?FAL_KEY is required (set in .env or export before running)}"
export LANGFUSE_HOST="http://localhost:3000"
export LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:?LANGFUSE_PUBLIC_KEY is required (set in .env or export before running)}"
export LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:?LANGFUSE_SECRET_KEY is required (set in .env or export before running)}"
export PYTHONUNBUFFERED=1
cd "$SCRIPT_DIR"
python3 pipeline.py $@ >> "$LOG_FILE" 2>&1
echo "PIPELINE_EXIT_CODE=\$?" >> "$LOG_FILE"
echo "done" > "$LOG_DIR/$RUN_NAME.status"
RUNNER_EOF
chmod +x "$RUNNER"

# nohup + redirect + & — fully detached from calling shell
nohup bash "$RUNNER" > /dev/null 2>&1 &
BGPID=$!
echo "$BGPID" > "$LOG_DIR/$RUN_NAME.pid"

# Disown so it survives shell exit
disown $BGPID 2>/dev/null

echo "Pipeline running (PID: $BGPID)"
echo "Monitor: tail -f $LOG_FILE"
echo "Status:  ./run-pipeline.sh status --thread $RUN_NAME"
