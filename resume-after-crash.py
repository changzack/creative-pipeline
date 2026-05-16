"""Resume a pipeline thread after a mid-graph crash (NOT a human-gate interrupt).
LangGraph picks up from the last successful checkpoint.

Usage: python resume-after-crash.py <thread_id>
"""
import sys
import sqlite3
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pipeline import (
    build_graph, tracer, _finalize_trace_with_rollup,
    RUNS_DIR, DB_PATH,
)
from langgraph.checkpoint.sqlite import SqliteSaver

if len(sys.argv) < 2:
    print("Usage: python resume-after-crash.py <thread_id>")
    sys.exit(1)

thread = sys.argv[1]

graph = build_graph()
conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
checkpointer = SqliteSaver(conn)
app = graph.compile(checkpointer=checkpointer)
config = {"configurable": {"thread_id": thread}}

tracer.init()
resume_trace_id = tracer.start_run(f"{thread}-crash-recover", metadata={"kind": "crash-recover"})
if resume_trace_id:
    try:
        registry_path = RUNS_DIR / thread / "langfuse-trace.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if registry_path.exists():
            existing = json.loads(registry_path.read_text())
        existing.append({
            "trace_id": resume_trace_id,
            "run_name": thread,
            "kind": "crash-recover",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        registry_path.write_text(json.dumps(existing, indent=2))
    except Exception as e:
        print(f"  ⚠️  Failed to update langfuse-trace.json: {e}")

state_before = app.get_state(config)
print(f"\n🔄 Resuming after crash: {thread}")
if state_before:
    print(f"  Last phase: {state_before.values.get('phase', '?')}")
    print(f"  Builds: {len(state_before.values.get('builds', []))}")
    print(f"  Approaches: {len(state_before.values.get('approaches', []))}")
    print(f"  Next: {state_before.next}")

# Stream from None — LangGraph picks up from checkpoint
for event in app.stream(None, config, stream_mode="updates"):
    if isinstance(event, dict):
        for node, update in event.items():
            if isinstance(update, dict):
                phase = update.get("phase", "")
                if phase:
                    print(f"  → {node}: {phase}")
            else:
                print(f"  → {node}: {update}")

try:
    final_state = app.get_state(config)
    final_values = final_state.values if final_state else None
except Exception:
    final_values = None

_finalize_trace_with_rollup(thread, status="paused_or_completed_after_recover", state=final_values)
print(f"\n✅ Recovery complete.")
