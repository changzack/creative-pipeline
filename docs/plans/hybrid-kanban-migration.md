# Hybrid Migration Plan: LangGraph + Hermes Kanban

**Date:** May 3, 2026  
**Author:** Mira  
**Status:** Draft — awaiting Zack approval  

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                         │
│                  (Orchestration Layer)                          │
│                                                                 │
│  PipelineState (typed) ──→ Graph topology ──→ Checkpoints      │
│                                                                 │
│  Owns: node routing, fan-out/fan-in, state merging,            │
│        interrupt() for human gates, cross-model dispatch,       │
│        in-process nodes (gate, QA, judge)                      │
└────────┬────────────────────────────────────────┬───────────────┘
         │                                        │
         │  Agent work nodes                      │  In-process nodes
         │  (create Kanban tasks)                 │  (run directly)
         ▼                                        ▼
┌─────────────────────────┐        ┌──────────────────────────────┐
│   Hermes Kanban Board   │        │  Direct Python / API calls   │
│   (~/.hermes/kanban.db) │        │                              │
│                         │        │  • approach_gate (Anthropic)  │
│  Profiles:              │        │  • qa_station (Playwright)   │
│  • researcher           │        │  • judge (GPT-4o vision)     │
│  • designer (Claude)    │        │  • spec_compliance (grep)    │
│  • builder-claude       │        │  • deploy (here-now)         │
│                         │        │                              │
│  Dispatcher auto-spawns │        │  No agent overhead.          │
│  workers with identity, │        │  Fast, typed, deterministic. │
│  memory, tool access.   │        │                              │
└─────────────────────────┘        └──────────────────────────────┘
         │                                        │
         │  Results flow back via                  │  Results flow back via
         │  kanban task completion                 │  Python return values
         │  + output files                         │
         ▼                                        ▼
┌─────────────────────────────────────────────────────────────────┐
│              PipelineState (fan-in, merge, route)               │
└─────────────────────────────────────────────────────────────────┘
```

## What Changes

### Nodes that move TO Kanban (agent work)

| Node | Current | After | Profile | Why Kanban? |
|---|---|---|---|---|
| Research | `run_hermes()` + signal files | Kanban task → `researcher` profile | `researcher` | Accumulates research memory across runs. Knows which Refero queries worked. |
| Designer ×3 | `run_hermes()` + signal files | 3 Kanban tasks → `designer` profile | `designer` | Accumulates design taste. Remembers banned aesthetics from experience. |
| Builder (Claude) | `run_hermes()` + signal files | Kanban task → `builder-claude` profile | `builder-claude` | Accumulates build patterns. Remembers what techniques rendered well. |

### Nodes that STAY in LangGraph (orchestration/fast work)

| Node | Why stays? |
|---|---|
| Approach Gate | Single Anthropic API call. No tools needed. In-process is faster. |
| Builder (GPT-5.4) | Direct OpenAI API call. Not a Hermes agent. |
| Builder (Gemini 3.1) | Direct Google API call. Not a Hermes agent. |
| QA Station | Playwright + Python. No LLM agent needed. |
| Judge | GPT-4o vision API. Cross-model by design. |
| Human Gate | `interrupt()` is perfect for this. |
| Deploy | Python script. No agent needed. |
| Iterate | Routes state. Pure orchestration. |

### What gets deleted

- `hermes-run.sh` wrapper script
- `hermes-status.sh` status script
- Signal file system (`.done`, `.running`, `.failed`, `.killed`, `.pid`)
- `/tmp/hermes-jobs/` directory pattern
- PID-based process tracking
- Manual timeout/watchdog logic in `run_hermes()`

---

## Hermes Profiles to Create

### Profile: `researcher`
```bash
hermes -p researcher setup
```
- **Model:** Claude Opus (inherits from main config)
- **Skills:** Refero MCP, design-research
- **Persona:** `personas/RESEARCHER.md` (symlinked or copied to profile SOUL.md)
- **Memory:** Accumulates across runs — which queries found good results, which sites had useful tokens
- **Workspace:** `scratch` (fresh per task, outputs copied to run dir)

### Profile: `designer`
```bash
hermes -p designer setup
```
- **Model:** Claude Opus
- **Skills:** Refero MCP (optional 1-2 searches), creative-technologist references
- **Persona:** `personas/DESIGNER.md`
- **Memory:** Accumulates design preferences, banned aesthetics, successful approach patterns
- **Workspace:** `dir:{run_dir}/concepts/` (writes approach docs directly)

### Profile: `builder-claude`
```bash
hermes -p builder-claude setup
```
- **Model:** Claude Opus
- **Skills:** File editing, code execution
- **Persona:** `personas/BUILDER.md`
- **Memory:** Accumulates build patterns — which CSS techniques render well, which font loading patterns work
- **Workspace:** `dir:{run_dir}/builds/` (writes HTML directly)

---

## Migration Steps

### Phase 1: Setup Kanban Infrastructure (30 min)

1. **Ensure Hermes CLI works with Python 3.11**
   - The `hermes` binary currently uses system Python 3.9
   - v0.12.0+ codebase requires 3.10+ (`Path | None` syntax)
   - Fix: update the shebang or create alias `hermes311`
   - Install remaining deps: `pip3.11 install pyyaml python-dotenv openai anthropic`

2. **Initialize Kanban DB**
   ```bash
   hermes kanban init  # Already done — ~/.hermes/kanban.db exists
   ```

3. **Create profiles**
   ```bash
   hermes -p researcher setup
   hermes -p designer setup
   hermes -p builder-claude setup
   ```
   - Configure each profile's SOUL.md with the corresponding persona
   - Set model to Claude Opus
   - Wire MCP servers (Refero for researcher + designer)

4. **Start gateway with Kanban dispatcher**
   ```bash
   hermes gateway start
   ```
   - Config: `kanban.dispatch_in_gateway: true`
   - Config: `kanban.dispatch_interval_seconds: 30` (faster than default 60)

### Phase 2: Build `kanban_hermes()` Bridge Function (1-2 hours)

Replace `run_hermes()` with a new function that creates Kanban tasks and polls for completion:

```python
def kanban_hermes(
    task_title: str,
    task_body: str, 
    profile: str,
    workspace: str,  # "scratch" or "dir:/path/to/dir"
    run_dir: Path,
    timeout: int = 1800,
    depends_on: list[str] = None,  # parent task IDs
) -> dict:
    """Create a Kanban task and wait for completion.
    
    Returns:
        {"status": "done", "task_id": str, "result": str}
        {"status": "failed", "task_id": str, "error": str}
        {"status": "timeout", "task_id": str}
    """
    import subprocess
    
    # Create task
    cmd = [
        "python3.11", "-m", "hermes_cli.main",
        "kanban", "create", task_title,
        "--assignee", profile,
        "--body", task_body,
        "--workspace", workspace,
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    task = json.loads(result.stdout)
    task_id = task["id"]
    
    # Add dependencies if any
    if depends_on:
        for parent_id in depends_on:
            subprocess.run([
                "python3.11", "-m", "hermes_cli.main",
                "kanban", "link", parent_id, task_id,
            ], capture_output=True, timeout=10)
    
    # Poll for completion
    start = time.time()
    while time.time() - start < timeout:
        show = subprocess.run([
            "python3.11", "-m", "hermes_cli.main",
            "kanban", "show", task_id, "--json",
        ], capture_output=True, text=True, timeout=10)
        
        task_state = json.loads(show.stdout)
        status = task_state.get("status")
        
        if status == "done":
            return {
                "status": "done",
                "task_id": task_id,
                "result": task_state.get("result", ""),
            }
        elif status in ("blocked", "archived"):
            return {
                "status": "failed", 
                "task_id": task_id,
                "error": task_state.get("block_reason", "unknown"),
            }
        
        time.sleep(15)  # Poll every 15s
    
    return {"status": "timeout", "task_id": task_id}
```

### Phase 3: Update Pipeline Nodes (2-3 hours)

#### research_node
```python
# Before:
result = run_hermes(f"{state['name']}-research", task, max_time=600)

# After:
result = kanban_hermes(
    task_title=f"Research: {state['name']}",
    task_body=task,
    profile="researcher",
    workspace=f"dir:{run_dir}",
    run_dir=run_dir,
    timeout=600,
)
```

#### designer_node (×3)
```python
# Before:
result = run_hermes(f"{state['name']}-designer-{designer_id}", task, max_time=600)

# After:
result = kanban_hermes(
    task_title=f"Design concept {designer_id}: {state['name']}",
    task_body=task,
    profile="designer",
    workspace=f"dir:{run_dir}/concepts",
    run_dir=run_dir,
    timeout=600,
)
```

#### builder_node (Claude only — GPT/Gemini stay direct API)
```python
# Before:
result = run_hermes(f"{state['name']}-builder-{idx}", task, max_time=1800, max_turns=50)

# After (only for Claude builder):
if builder_model == "claude-opus":
    result = kanban_hermes(
        task_title=f"Build concept {idx}: {state['name']}",
        task_body=task,
        profile="builder-claude",
        workspace=f"dir:{run_dir}/builds",
        run_dir=run_dir,
        timeout=1800,
    )
else:
    # GPT-5.4, Gemini 3.1 Pro stay direct API
    result = build_direct_api(builder_model, task, build_path, state["name"], ...)
```

### Phase 4: Wire Profile Memory (1 hour)

Each profile's memory accumulates automatically via Hermes' self-improvement loop. But we can seed it:

```bash
# Seed researcher memory
hermes -p researcher memory set "research_preferences" \
  "Use Refero MCP for all research. Never use browser screenshots. \
   Moodboard must span 3+ visual categories. Save to VISUAL-RESEARCH.md."

# Seed designer memory  
hermes -p designer memory set "banned_aesthetics" \
  "BANNED: vintage fight cards, Spotify Wrapped, cream/newsprint, \
   boxing posters, glassmorphism, gradient blobs."

# Seed builder-claude memory
hermes -p builder-claude memory set "build_lessons" \
  "Content fidelity is non-negotiable. Use sample data from brief exactly. \
   3-second test: metaphor visible, designed not template, #1 is hero, texture/depth. \
   Never produce AI slop — add imperfections, organic textures, hand-crafted feeling."
```

### Phase 5: Delete Old Infrastructure (30 min)

1. Remove `run_hermes()` function from pipeline.py
2. Remove `skills/hermes-bridge/scripts/hermes-run.sh`
3. Remove `skills/hermes-bridge/scripts/hermes-status.sh`
4. Remove signal file cleanup code
5. Update `MEMORY.md` with new architecture
6. Archive `skills/hermes-bridge/` (keep for reference)

### Phase 6: Test E2E (V3j run)

Run the full pipeline with Kanban integration. Verify:
- [ ] Researcher profile creates moodboard + VISUAL-RESEARCH.md
- [ ] Designer profile writes approach docs with BUILD CONTRACT
- [ ] Builder-claude profile builds HTML
- [ ] GPT-5.4 and Gemini 3.1 Pro builders still work (direct API, unchanged)
- [ ] Kanban task completion triggers next LangGraph node
- [ ] Profile memory persists after run
- [ ] `hermes kanban list` shows full task history
- [ ] `hermes kanban log <task_id>` shows worker output
- [ ] Crash recovery: kill a worker mid-build, dispatcher reclaims

---

## What We Gain

| Capability | Before (signal files) | After (Kanban) |
|---|---|---|
| **Worker identity** | Anonymous sessions | Named profiles with persistent memory |
| **Crash recovery** | Manual — check PID, restart | Automatic — dispatcher reclaims stale claims |
| **Inter-run learning** | techniques.json (manual) | Profile memory (automatic via self-improvement loop) |
| **Task history** | Log files in /tmp | Durable SQLite rows forever |
| **Worker logs** | /tmp/hermes-jobs/{name}/.log | `hermes kanban log <task_id>` |
| **Attempt history** | None | `hermes kanban runs <task_id>` — every attempt recorded |
| **Human intervention** | interrupt() only at gate | Block/comment/unblock any task at any time |
| **Inter-agent comms** | None | Comment threads on tasks |
| **Monitoring** | `tail -f /tmp/pipeline-runs/*.log` | `hermes kanban watch` live stream |
| **Board overview** | Custom dashboard | `hermes kanban list` + `hermes kanban stats` |

## What We Keep (Unchanged)

- LangGraph graph topology (node ordering, fan-out, conditionals)
- PipelineState TypedDict (typed state flow)
- SQLite checkpointer (pipeline.db for LangGraph state)
- Direct API builders (GPT-5.4, Gemini 3.1 Pro)
- In-process nodes (gate, QA, judge, deploy)
- interrupt() for human taste gate
- Langfuse tracing
- Cost tracking
- Dashboard generator

## Risks

| Risk | Mitigation |
|---|---|
| Python 3.9 → 3.11 compatibility | Hermes uses 3.11; pipeline.py uses 3.9 venv. Bridge calls `python3.11 -m hermes_cli.main` via subprocess — isolated. |
| Dispatcher latency (60s default) | Set to 30s. For time-critical spawns, call `hermes kanban dispatch` to force immediate tick. |
| Profile config drift | Persona files remain in `skills/creative-technologist/personas/`. Profile SOUL.md symlinks to these. Single source of truth. |
| Kanban DB corruption | SQLite WAL mode. Regular backups via `hermes kanban gc`. |
| Polling overhead | `kanban_hermes()` polls every 15s. Low overhead — just reading a SQLite row. Could switch to `hermes kanban tail --json` streaming later. |

## Timeline

| Phase | Effort | Depends On |
|---|---|---|
| 1. Setup infrastructure | 30 min | Hermes 3.11 working (done) |
| 2. Bridge function | 1-2 hours | Phase 1 |
| 3. Update pipeline nodes | 2-3 hours | Phase 2 |
| 4. Wire profile memory | 1 hour | Phase 3 |
| 5. Delete old infra | 30 min | Phase 4 |
| 6. E2E test (V3j) | 1 run (~40 min) | Phase 5 |
| **Total** | **~6-8 hours** | |

## Decisions (Confirmed by Zack, May 3)

1. **Profile granularity:** Single `designer` profile for all 3 designers. Shared memory — all learn banned aesthetics together. Divergence comes from the visual language mandate in the task, not the profile identity.

2. **Dispatcher interval:** 30s default.

3. **Memory seeding:** Pre-seed profiles with accumulated learnings from 8+ runs. No reason to relearn.

4. **Timing:** Start after V3i results are reviewed.

---

*Plan generated May 3, 2026. Ready for review.*
