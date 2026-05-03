# Architecture Audit Report — May 3, 2026
## Creative Pipeline V3 vs. Deep Research Reference Architecture

**Auditor:** Mira  
**Requested by:** Zack Chang  
**Scope:** Full pipeline audit against the 9-layer agentic AI reference architecture (sourced from April 30, 2026 deep research) + file-based vs prompt-only instruction audit

---

## Executive Summary

The pipeline has **strong bones** — LangGraph orchestration, pairwise bidirectional judge, multi-model builders, Langfuse tracing, QA station, Refero research — but **critical instructions live only as inline strings in `pipeline.py`**, not in the persistent persona/process files that agents actually read. If we swapped out pipeline.py or spun up agents manually, ~40% of our hard-won lessons would be lost.

**Overall Grade: B- (up from D+ at initial audit on April 30)**

The biggest remaining gaps are: (1) process doc drift from reality, (2) cross-run memory is empty, and (3) the technique registry has zero entries despite 8+ pipeline runs.

---

## Layer-by-Layer Breakdown

### Layer 1: Orchestration — Grade: A-
**Research says:** LangGraph StateGraph with SQLite checkpointer, `interrupt()` for human gates, `Send()` for fan-out.

**What we have:**
- ✅ LangGraph StateGraph with 9 nodes (research → designer → approach_gate → builder → **QA** → judge → human_gate → iterate → deploy)
- ✅ SQLite checkpointer (`pipeline.db`) — survives crashes, resume with `--thread`
- ✅ `interrupt()` for human taste gate
- ✅ `Send()` for parallel designer and builder fan-out
- ✅ `Command()` for routing human decisions (approve/iterate/reject)
- ✅ Detached execution via `run-pipeline.sh` wrapper (survives OpenClaw session resets)
- 🆕 QA station node added today (builder → QA → judge)

**Gap:**
- ⚠️ No model version pinning — we use `claude-opus-4-6`, `gpt-5.4`, `gemini-3.1-pro-preview` (aliases, not dated snapshots). Research explicitly flags this as "top-10 production failure mode."

**Recommendation:** Pin to dated model versions (e.g., `gpt-5.4-2026-03-05`).

---

### Layer 2: Quality Evaluation — Grade: B+
**Research says:** Pairwise bidirectional comparison + calibration set of 50+ human-rated examples. Never use pointwise 1-10 scoring.

**What we have:**
- ✅ Bidirectional pairwise judge (both AB and BA orderings, only count agreement)
- ✅ Round-robin tournament (all pairs compared)
- ✅ Cross-model judging (GPT-4o judges Claude/GPT/Gemini builds — prevents self-preference bias)
- ✅ Vision-based evaluation (screenshots, not source code)
- ✅ Calibration set: 15 human-rated builds (0 great, 6 acceptable, 9 bad)
- 🆕 QA station with automated render/content/animation/visibility checks

**Gaps:**
- ⚠️ Calibration set has 15 entries — research recommends 30-80. Need more rated builds.
- ⚠️ Calibration weights (40% ambition, 20% anti-slop, etc.) exist **only in pipeline.py inline prompt** — not in REVIEWER.md persona file
- ⚠️ No offline calibration suite (research recommends Promptfoo for CI-blocking eval runs against calibration set)
- ⚠️ Judge doesn't receive moodboard images as visual reference (research explicitly recommends this)

**Recommendation:** 
1. Move calibration weights to REVIEWER.md
2. Add moodboard images to judge's vision input (same pattern we just added for builders)
3. Keep building calibration set — every Zack verdict should add to it
4. Consider Promptfoo for offline calibration validation

---

### Layer 3: Observability — Grade: B
**Research says:** Langfuse self-hosted + Promptfoo for offline eval.

**What we have:**
- ✅ Langfuse v3.172.1 self-hosted (Docker Compose, 6 containers)
- ✅ `PipelineTracer` wrapper with span start/end + scores per node
- ✅ Per-run cost tracking (JSON reports with phase breakdown)
- ✅ Budget circuit breaker ($20 cap, 80% alert)
- ✅ Context budget logging (new — shows KB used / KB available per builder)

**Gaps:**
- ⚠️ Langfuse requires Docker Desktop running — no graceful degradation documented in process docs
- ⚠️ No Promptfoo or offline eval suite
- ⚠️ No alerting on anomalous costs (only hard cap)

**Recommendation:** Document Langfuse startup in CREATIVE-PIPELINE.md. Add Promptfoo later.

---

### Layer 4: Cost Management — Grade: B+
**Research says:** 5 instruments: per-run cost meter, circuit breaker, retry limiter, model pinning, OTEL conventions.

**What we have:**
- ✅ Per-run cost meter with phase breakdown (JSON + dashboard)
- ✅ Budget circuit breaker ($20 cap)
- ✅ Max iterations limiter (MAX_ITERATIONS = 3)
- ✅ Hermes turn limits (60 turns per session, 50 per delegation)
- ⚠️ No model version pinning (see Layer 1)
- ⚠️ No OTEL GenAI semantic conventions (using custom Langfuse wrapper instead)

**Actual costs per run:** $0.28-$0.36 — well within budget. Multi-model diversity adds ~20% cost over single-model.

---

### Layer 5: Memory & Cross-Run Learning — Grade: D
**Research says:** Technique registry with human-approved verdicts. Pull learnings as constraints, not suggestions. Only write memories after human verdicts.

**What we have:**
- ✅ `techniques.json` file exists with schema for techniques + verdicts
- ✅ `record_verdict()` and `get_relevant_learnings()` functions in pipeline.py
- ✅ Calibration set (15 ratings)
- ✅ Learnings injected into research + designer prompts (in code)

**Gaps:**
- 🔴 **techniques.json has 0 entries.** Despite 8+ pipeline runs, no techniques or verdicts have been recorded. The functions exist but are never called effectively.
- 🔴 No cross-run learning is actually happening. Each run starts fresh.
- ⚠️ No reflection step after human verdict (research: "the reflection step is where the value is")
- ⚠️ Banned aesthetics list is in CREATIVE-BRIEF.md and DESIGNER.md but not systematically populated from past rejections

**Recommendation:** 
1. After every Zack verdict (approve/reject), automatically call `record_verdict()` with the technique + outcome
2. Build a post-verdict reflection node that distills "what worked / what failed" into techniques.json
3. Populate banned aesthetics from rejection history

---

### Layer 6: Multi-Agent Topology — Grade: A-
**Research says:** Parallel builders for independent creation, single context for sequential decisions. Orchestrator-worker pattern.

**What we have:**
- ✅ Orchestrator-worker pattern (LangGraph orchestrates, Hermes/APIs build)
- ✅ 3 parallel builders with different models (Claude Opus, GPT-5.4, Gemini 3.1 Pro)
- ✅ Each builder gets isolated context (no cross-contamination)
- ✅ Visual language mandates for divergence (3D/Spatial, Data Viz, Kinetic Type)
- ✅ Research phase is single-agent (appropriate for sequential task)
- ✅ Fan-out via `Send()` for parallel phases

**Gap:**
- ⚠️ Designers are single-model (all Claude Opus via Hermes) while builders are multi-model. Research suggests multi-model designers too for approach diversity.

---

### Layer 7: Tool Integration — Grade: B+
**What we have:**
- ✅ Refero MCP for design research (structured API, real screens with tokens)
- ✅ Playwright for screenshots, QA checks, render verification
- ✅ Direct API integration for GPT + Gemini builders
- ✅ Hermes with full tool access for Claude builders
- ✅ here-now for deployment
- 🆕 Vision input for GPT/Gemini builders (moodboard images)

**Gap:**
- ⚠️ Hermes builders can open moodboard files; GPT/Gemini builders now get base64 images. Good parity achieved today.

---

## The Critical Finding: File-Based vs Prompt-Only

### 🔴 Instructions that exist ONLY in pipeline.py inline strings

These are the **most dangerous** gaps. If pipeline.py is refactored, or if agents are spawned outside the pipeline, these instructions are lost:

| Instruction | Where it lives | Where it SHOULD live |
|---|---|---|
| Anti-AI-slop mandate ("YOUR BUILD MUST NOT LOOK LIKE AN AI MADE IT") | `pipeline.py` builder prompt | `personas/BUILDER.md` |
| Taste calibration stats (0 great, 6 acceptable, 9 bad) | `pipeline.py` builder + judge prompts | `personas/BUILDER.md` + `personas/REVIEWER.md` |
| Calibration weights (40% ambition, 20% anti-slop, etc.) | `pipeline.py` judge prompt | `personas/REVIEWER.md` |
| Content fidelity mandate | `pipeline.py` builder + designer prompts | `personas/BUILDER.md` + `personas/DESIGNER.md` (partial — DESIGNER has it, BUILDER doesn't) |
| Creative imperfection instructions (off-grid, organic textures) | `pipeline.py` builder prompt | `personas/BUILDER.md` |
| Moodboard = style only, brief = content | `pipeline.py` builder prompt | `personas/BUILDER.md` (has it) + `personas/DESIGNER.md` (has it) ✅ |
| Self-check checklist (fonts, colors, techniques) | `pipeline.py` builder prompt | `personas/BUILDER.md` |
| Banned aesthetics (fight cards, newsprint, etc.) | `pipeline.py` designer prompt | `personas/DESIGNER.md` (has it) ✅ |

### 🟡 Process changes not reflected in CREATIVE-PIPELINE.md

| Change | In pipeline.py? | In CREATIVE-PIPELINE.md? |
|---|---|---|
| QA Station (builder → QA → judge) | ✅ Yes | ❌ No |
| GPT-5.4 + Gemini 3.1 Pro models | ✅ Yes | ❌ No |
| Dynamic context budgets (no truncation) | ✅ Yes | ❌ No |
| Moodboard vision injection to builders | ✅ Yes | ❌ No |
| Refero MCP for research | ✅ Yes | ✅ Yes |
| Content fidelity checks in QA | ✅ Yes | ❌ No |
| Full creative narrative to builder | ✅ Yes (just changed) | ❌ No |

### ✅ Things properly file-based

| Instruction | File |
|---|---|
| Pipeline flow (phases, ordering) | `CREATIVE-PIPELINE.md` ✅ |
| Divergence seeding (visual language mandates) | `CREATIVE-PIPELINE.md` ✅ |
| Two-level convergence gate | `CREATIVE-PIPELINE.md` ✅ |
| Banned aesthetics | `personas/DESIGNER.md` ✅ |
| Content fidelity (designer) | `personas/DESIGNER.md` ✅ |
| Content fidelity (builder, partial) | `personas/BUILDER.md` ✅ |
| Builder persona (craft principles) | `personas/BUILDER.md` ✅ |
| Reviewer persona (calibrated taste) | `personas/REVIEWER.md` ✅ |
| Deployment gate checklist | `CREATIVE-PIPELINE.md` ✅ |
| Creative brief structure | `CREATIVE-PIPELINE.md` ✅ |
| Refero research workflow | `CREATIVE-PIPELINE.md` ✅ |

---

## Priority Fix List

### P0 — Must fix before next run
1. **Move anti-AI-slop mandate to `BUILDER.md`** — the most impactful instruction isn't in the persona file
2. **Move calibration weights to `REVIEWER.md`** — judge criteria shouldn't be inline strings
3. **Move taste calibration stats to `BUILDER.md` + `REVIEWER.md`** — "0 great, 6 acceptable, 9 bad"
4. **Add QA Station to `CREATIVE-PIPELINE.md`** — new phase undocumented
5. **Update model list in `CREATIVE-PIPELINE.md`** — still references old models

### P1 — This week
6. **Populate `techniques.json`** — retrofit verdicts from V1-V3h runs into the registry
7. **Add post-verdict reflection** — after each human verdict, distill learnings into techniques.json
8. **Add moodboard images to judge vision input** — research explicitly recommends this
9. **Pin model versions** — use dated snapshots, not floating aliases

### P2 — This month
10. **Expand calibration set to 30+** — every Zack verdict should auto-append
11. **Add Promptfoo offline eval** — CI-blocking runs against calibration set
12. **Multi-model designers** — not just multi-model builders

---

## Architecture Scorecard

| Layer | Apr 30 Grade | May 3 Grade | Change | Key Improvement |
|---|---|---|---|---|
| **1. Orchestration** | D | A- | ⬆️⬆️⬆️ | LangGraph replaced cron+signal files |
| **2. Evaluation** | C | B+ | ⬆️⬆️ | Pairwise bidirectional + QA station |
| **3. Observability** | F | B | ⬆️⬆️⬆️ | Langfuse + cost tracking |
| **4. Cost Management** | C- | B+ | ⬆️⬆️ | Circuit breaker + phase tracking |
| **5. Memory** | D+ | D | — | Functions exist but 0 entries recorded |
| **6. Multi-Agent** | B- | A- | ⬆️ | Multi-model builders + fan-out |
| **7. Tools** | B | B+ | ⬆️ | Refero MCP + vision injection |

**Overall: D+ → B-**

The pipeline went from "Mira reads a doc and manually runs Hermes jobs" to a real LangGraph state machine with multi-model builders, automated QA, and observability. The remaining gap is operational discipline: making sure what we learn stays in files, not in pipeline.py strings or conversation context.

---

*Report generated May 3, 2026. Source: deep research PDF (April 30, 2026) + live pipeline audit.*
