# Context Flow Analysis — Pipeline Architecture Deep Dive
## May 3, 2026

---

## 1. The Two Architectures: Before and After

### Before (V1-V2): CREATIVE-PIPELINE.md Was the Orchestrator

```
Zack (Telegram) → Mira (OpenClaw main session)
                      ↓
              Reads CREATIVE-PIPELINE.md
              Manually decides which phase to run
                      ↓
              Spawns Hermes job per phase
              (hermes-run.sh with task string)
                      ↓
              Polls with cron / signal files
              (.done, .running, .killed)
                      ↓
              Reads results, decides next phase
              (state lives in Mira's context window)
```

**CREATIVE-PIPELINE.md was essential** because Mira was the orchestrator. She read the doc each phase to know what to do next. The doc was the workflow engine.

**Problems:** Mira forgot steps. Context compacted and lost pipeline state. Cron polling was fragile. No parallel execution. No crash recovery.

### After (V3+): pipeline.py Is the Orchestrator

```
Zack (Telegram) → Mira → `python pipeline.py run --brief X --name Y`
                              ↓
                    LangGraph StateGraph (pipeline.py)
                    ┌─────────────────────────────────┐
                    │  PipelineState (TypedDict)       │
                    │  ┌───────────────────────────┐   │
                    │  │ name, brief               │   │
                    │  │ research, moodboard       │   │
                    │  │ approaches[] (fan-in)     │   │
                    │  │ builds[] (fan-in)         │   │
                    │  │ qa_reports[]              │   │
                    │  │ pairwise_results[]        │   │
                    │  │ ranking[]                 │   │
                    │  │ iteration, phase          │   │
                    │  └───────────────────────────┘   │
                    │                                   │
                    │  SQLite checkpointer (pipeline.db)│
                    │  Every node commits state         │
                    └─────────────────────────────────┘
                              ↓
                    Nodes execute in sequence/parallel
                    Each node reads state → does work → returns updates
                    interrupt() pauses for human input
                    Command() routes decisions
```

**pipeline.py replaced CREATIVE-PIPELINE.md as the orchestrator.** The graph topology, node ordering, fan-out logic, and gate conditions are all in Python code, not in a markdown doc that Mira reads.

### So What's CREATIVE-PIPELINE.md For Now?

**It's documentation for humans, not instructions for agents.** The pipeline doesn't read it. No node loads it. It's referenced once — in a comment: `"Replaces: cron polling, signal files, CREATIVE-PIPELINE.md manual execution"`.

It still has value as:
1. **Human reference** — Zack can read it to understand the pipeline
2. **Manual fallback** — if pipeline.py breaks, Mira could fall back to manual orchestration
3. **Onboarding doc** — explains the WHY behind each phase

But it's **not in the execution path**. The actual instructions agents receive come from:
- **Persona files** (`BUILDER.md`, `DESIGNER.md`, `REVIEWER.md`) — loaded by pipeline.py
- **Reference docs** (`recipes.md`, `advanced-techniques.md`, etc.) — loaded by pipeline.py
- **Inline prompt strings in pipeline.py** — the problematic ones from the audit

---

## 2. How Context Actually Flows (Current Architecture)

### The Full Flow

```
                    ┌──────────────────────────────────────────────────┐
                    │              LangGraph PipelineState             │
                    │  (single TypedDict, checkpointed per node)      │
                    └──────────────────────────────────────────────────┘
                                          │
    ┌─────────────────────────────────────┼──────────────────────────────┐
    │                                     │                              │
    ▼                                     ▼                              ▼
┌──────────┐                    ┌───────────────┐              ┌──────────────┐
│ RESEARCH │                    │  DESIGNER ×3  │              │  BUILDER ×3  │
│  (Hermes)│                    │   (Hermes)    │              │ (Mixed APIs) │
└────┬─────┘                    └───────┬───────┘              └──────┬───────┘
     │                                  │                             │
     │ READS:                           │ READS:                      │ READS:
     │ • state["brief"]                 │ • state["brief"]            │ • state["approaches"][idx]
     │ • techniques.json                │ • state["research"]         │   (full approach doc now)
     │ • art-direction-rubric.md        │ • VISUAL-RESEARCH.md        │ • BUILDER.md persona
     │ • creative-patterns.md           │ • DESIGNER.md persona       │ • recipes.md
     │ • banned aesthetics              │ • enhancement-tactics.md    │ • advanced-techniques.md
     │                                  │ • advanced-techniques.md    │ • moodboard images (vision)
     │ WRITES:                          │ • contract template         │ • moodboard image filenames
     │ • moodboard/ images             │ • past learnings            │
     │ • VISUAL-RESEARCH.md            │                              │ WRITES:
     │ • state["research"]             │ WRITES:                      │ • builds/concept-N.html
     │ • state["moodboard"]            │ • concepts/designer-N.md     │ • state["builds"]
     │                                  │ • state["approaches"]       │
     │                                  │                              │
     ▼                                  ▼                              ▼
┌──────────┐                    ┌───────────────┐              ┌──────────────┐
│APPROACH  │                    │   QA STATION  │              │    JUDGE     │
│  GATE    │                    │  (Playwright) │              │  (GPT-4o)   │
│(Claude)  │                    └───────┬───────┘              └──────┬───────┘
└────┬─────┘                            │                             │
     │ READS:                           │ READS:                      │ READS:
     │ • state["approaches"] (FULL now) │ • state["builds"]           │ • state["builds"]
     │ • font/color specs               │ • state["brief"]            │ • screenshots (Playwright)
     │                                  │ • HTML source               │ • state["brief"][:500]
     │ CHECKS:                          │                              │ • REVIEWER.md persona
     │ • Mechanical convergence         │ CHECKS:                      │
     │   (fonts, colors)                │ • Render (non-blank)        │ PRODUCES:
     │ • LLM conceptual convergence     │ • Content fidelity          │ • pairwise_results[]
     │   (metaphor, era, layout)        │ • Dimensions                │ • ranking[]
     │ • Ambition check                 │ • Animation (t0 vs t3)      │
     │                                  │ • Visibility (bounding rects)│
     │                                  │ • Console errors            │
     │                                  │ • Image loading             │
     │                                  │                              │
     │                                  │ VERDICTS:                    │
     │                                  │ • PASS → judge              │
     │                                  │ • FIXABLE → fix round       │
     │                                  │ • BROKEN → skip judge       │
     │                                  │                              │
```

### Context Isolation Model

| Agent Type | Context Source | Can See Other Builds? | Has Memory? | Has Tools? |
|---|---|---|---|---|
| **Hermes (Claude Opus)** | Task string + filesystem + MCP | Only via filesystem (but doesn't look) | SOUL.md + shared skills | Full tool use, Refero MCP |
| **GPT-5.4 (API)** | Single prompt + base64 images | No | None | None |
| **Gemini 3.1 Pro (API)** | Single prompt + multimodal parts | No | None | None |
| **Judge (GPT-4o)** | Screenshots + brief excerpt | Sees exactly 2 builds per comparison | None | None |
| **Approach Gate (Claude Opus)** | Full approach docs (API call) | Sees all 3 approaches | None | None |

### What Each Builder Actually Receives (Current)

```
Builder prompt composition:
├── BUILDER.md persona (6KB)
├── Inline taste calibration block (1KB)          ← SHOULD be in BUILDER.md
├── Inline anti-AI-slop mandate (0.5KB)           ← SHOULD be in BUILDER.md
├── Inline content fidelity block (0.3KB)         ← SHOULD be in BUILDER.md
├── Creative narrative (full — ~25KB now)          ← Was 3KB before today
├── Build contract (full — ~7KB now)               ← Was 3KB before today
├── recipes.md (54KB)                              ← Was 6KB before today
├── advanced-techniques.md (not loaded by builder) 
├── Moodboard image filenames (0.2KB text)
├── Moodboard images (base64 vision — NEW)         ← Only for GPT/Gemini
├── Self-check checklist (0.3KB)
└── Total: ~90-95KB text + images
    GPT-5.4 budget: 372KB ✓
    Gemini 3.1 budget: 3.7MB ✓
    Claude (Hermes): 200K tokens ≈ 800KB ✓
```

---

## 3. Deep Research Recommendations vs Our Implementation

### Recommendation 1: "Sub-agents should have isolated context — no parent context bleed"
**Status: ✅ Correct.**
Each builder gets only its own approach doc. No cross-contamination. Fan-out via `Send()` copies state but each builder only reads `state["approaches"][idx]`.

### Recommendation 2: "Multi-agents win when sub-tasks are independent and read-only; they lose when sub-tasks make implicit decisions that need to compose"
**Status: ✅ Correct.**
Builders are independent (3 parallel, no shared decisions). Gate and judge are sequential (single context, sees everything). Research is sequential. This matches the research pattern exactly.

### Recommendation 3: "The orchestrator-worker pattern — research → parallel-create → critique → human-gate"
**Status: ✅ Correct.**
Our graph: research → designer×3 → gate → builder×3 → QA → judge → human_gate → iterate/deploy. This IS the orchestrator-worker pattern.

### Recommendation 4: "Use vision-capable judge and pass moodboard images as reference + both candidate screenshots"
**Status: ⚠️ Partial.**
Judge gets screenshots of both builds ✅ but does NOT get moodboard images ❌. This means the judge can't evaluate "does this feel like the moodboard?" — only "which is better between these two?"

### Recommendation 5: "Only write memories after human-approved verdicts (prevents memory poisoning)"
**Status: ⚠️ Implemented but unused.**
`record_verdict()` exists and is called only from human_gate_node, but `techniques.json` has 0 entries. The function may not be triggering correctly, or verdicts aren't being passed through.

### Recommendation 6: "Pull learnings as constraints, not suggestions"
**Status: ⚠️ Implemented but empty.**
`get_relevant_learnings()` is injected into research and designer prompts, but since techniques.json is empty, it always returns nothing.

### Recommendation 7: "Pin specific model versions, not floating aliases"
**Status: ❌ Not implemented.**
Using `claude-opus-4-6`, `gpt-5.4`, `gemini-3.1-pro-preview` — all floating.

### Recommendation 8: "Evaluate the rendered artifact, not just the source code"
**Status: ✅ Correct.**
QA station uses Playwright to open builds in a real browser. Judge uses screenshots. Spec compliance checks source but QA checks rendering.

### Recommendation 9: "The reflection step is where the value is — episodic memory of failures makes the system learn across runs"
**Status: ❌ Not implemented.**
No post-verdict reflection step. When Zack says "reject" or "approve", the pipeline doesn't distill WHY into a lesson. It just moves on.

---

## 4. The Proposed Architecture (What We Should Build)

### Change 1: CREATIVE-PIPELINE.md becomes documentation only
It already IS documentation only — pipeline.py doesn't read it. But we should:
- Update it to accurately describe the LangGraph pipeline (not the old manual flow)
- Mark it clearly as "human reference, not agent instructions"
- Remove the "re-read before each phase" directive (agents don't read it)

### Change 2: All agent instructions live in persona files
Move everything from pipeline.py inline strings to the appropriate file:

```
personas/BUILDER.md         ← Anti-AI-slop, taste calibration, content fidelity,
                              creative imperfection, self-check checklist
personas/DESIGNER.md        ← Already mostly good
personas/REVIEWER.md        ← Calibration weights, scoring rubric, taste stats
personas/RESEARCHER.md (new)← Refero workflow, moodboard quality gates, diversity mandate
```

pipeline.py loads these files and includes them in prompts. The files are the source of truth. pipeline.py just orchestrates.

### Change 3: Add post-verdict reflection node

```
Current:  human_gate → deploy / iterate
Proposed: human_gate → reflect → deploy / iterate

reflect_node():
  - Takes human verdict + feedback
  - Distills into techniques.json entries
  - Updates banned aesthetics if rejection
  - Logs to calibration-set.json
```

### Change 4: Add moodboard to judge context

```
Current judge input:  screenshot_A + screenshot_B + brief[:500]
Proposed judge input: screenshot_A + screenshot_B + moodboard_images + brief[:500] + REVIEWER.md
```

### Change 5: Context flow diagram (proposed)

```
DURABLE FILES (persist across runs):
├── personas/BUILDER.md      — loaded by builder_node
├── personas/DESIGNER.md     — loaded by designer_node  
├── personas/REVIEWER.md     — loaded by pairwise_judge_node
├── personas/RESEARCHER.md   — loaded by research_node (NEW)
├── references/*.md          — loaded by various nodes
├── memory/techniques.json   — loaded by research + designer (cross-run learning)
├── memory/calibration-set.json — loaded by judge for anchoring
└── CREATIVE-BRIEF.md        — passed as state["brief"]

EPHEMERAL STATE (per-run, in LangGraph + files):
├── PipelineState (SQLite checkpointer)
│   ├── name, brief
│   ├── research dict
│   ├── moodboard paths
│   ├── approaches[] (fan-in from designers)
│   ├── builds[] (fan-in from builders)
│   ├── qa_reports[]
│   ├── pairwise_results[]
│   └── ranking[]
│
└── Run directory (overnight-runs/{name}/)
    ├── moodboard/*.jpg
    ├── VISUAL-RESEARCH.md
    ├── concepts/designer-N-APPROACH.md
    ├── builds/concept-N.html
    ├── screenshots/concept-N.png
    ├── qa-reports/concept-N-qa.json
    ├── reviews/pairwise-results.json
    └── cost-report.json
```

### The Key Principle

**Files are memory. Prompts are behavior. State is flow.**

- **Persona .md files** = persistent agent behavior/personality/instructions
- **Reference .md files** = persistent knowledge/techniques/patterns  
- **pipeline.py** = orchestration logic (graph shape, node routing, API calls)
- **PipelineState** = ephemeral per-run data flowing through the graph
- **Run directory** = artifacts for human review and cross-run reference
- **techniques.json / calibration-set.json** = cross-run learning

pipeline.py should contain minimal inline instructions — just enough to compose the prompt from file-based sources. The "what to do" lives in files. The "how to orchestrate" lives in Python.

---

## 5. Gap Summary

| Gap | Impact | Fix Effort |
|---|---|---|
| Instructions in pipeline.py strings, not files | 🔴 High — lost on refactor | Small — copy to persona files |
| CREATIVE-PIPELINE.md outdated, not in execution path | 🟡 Medium — misleading | Medium — rewrite as docs |
| techniques.json empty after 8 runs | 🔴 High — no cross-run learning | Small — debug record_verdict |
| No reflection node after human verdict | 🟡 Medium — missed learning opportunity | Medium — new node |
| Judge doesn't see moodboard | 🟡 Medium — can't judge aesthetic fit | Small — add images |
| No model version pinning | 🟡 Medium — silent regressions | Small — use dated IDs |
| No RESEARCHER.md persona | 🟢 Low — research instructions inline | Small — extract to file |

---

*Analysis generated May 3, 2026. Reference: deep research PDF (April 30) + live pipeline.py audit.*
