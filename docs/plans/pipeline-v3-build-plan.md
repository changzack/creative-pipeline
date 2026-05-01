# Pipeline V3 Build Plan
**Created:** 2026-04-30
**Status:** Planning
**Source:** Claude Deep Research v3 field report + V1/V2 retros

---

## Architecture Summary

| Layer | Tool | Why |
|---|---|---|
| Orchestration | LangGraph (Python, SQLite checkpointer) | Graph-shaped pipeline, fan-out/fan-in, interrupt() for human gate, durable state |
| Worker Runtime | Hermes Agent CLI (existing) + multi-model | Claude Opus + GPT-5 + Gemini 2.5 Pro for diversity |
| Evaluation | Bidirectional pairwise tournament | Research consensus: pairwise >>> direct scoring. Bidirectional controls position bias |
| Calibration | Human-rated artifact set (30-80 items) | Ground truth for taste. The real lever. |
| Memory | Mem0 (local, post-verdict only) | Cross-run learning. Only write after human approval. |
| Observability | Langfuse self-hosted + LangGraph Studio | Traces, cost, latency. Free. |
| Dashboard | Custom HTML app (here-now deployed) | Pipeline state + build previews + human gate UI |
| Cost Control | Token-budget circuit breaker | Hard cap per run, max iteration limit |

---

## Phase 1: Fix the Spine (Days 1-3)
**Goal:** Pipeline state survives crashes. No more cron polling.

- [ ] Install LangGraph + dependencies (`pip install langgraph langgraph-checkpoint-sqlite langchain-anthropic`)
- [ ] Create `pipeline.py` — port existing phases as graph nodes
- [ ] Wrap current Hermes spawns in node functions (don't rewrite agents yet)
- [ ] `Send()` API for parallel fan-out (3 designers, 3 builders)
- [ ] SQLite checkpointer for durable state
- [ ] `interrupt()` for human taste gate (replaces cron hack)
- [ ] Basic CLI to invoke/resume pipeline (`python pipeline.py run/resume`)
- [ ] Install LangGraph Studio desktop app for debugging
- [ ] Test: crash mid-run, resume from checkpoint

**Kills:** Orchestrator amnesia, phase skipping, cron polling, lost state on compaction

**Definition of done:** Can start a pipeline, kill the process mid-build, restart, and it resumes from the correct node.

---

## Phase 2: Fix the Evaluator (Days 3-5)
**Goal:** Scores match Zack's judgment.

- [ ] Implement bidirectional pairwise tournament (code from research report)
- [ ] Screenshot builds via browser automation (Puppeteer or Playwright)
- [ ] Send screenshots + brief + moodboard + approach docs to vision-capable judge
- [ ] Use **cross-model judging** — if builders use Claude, judge with Gemini (or vice versa)
- [ ] Anti-pattern checklist in judge prompt:
  - No gradients/glassmorphism/backdrop-blur/rounded-2xl
  - No default shadcn components
  - No AI-beige color palettes
  - No generic SaaS hero sections
- [ ] Position bias control: randomize A/B ordering, run both directions
- [ ] Output: ranked list with win counts + per-comparison justifications

**Kills:** Score inflation, sycophantic confirmation, reviewer hallucinating 7.0 on bad work

**Definition of done:** Pairwise judge produces a ranking of 3 builds with justifications. No 1-10 scores anywhere.

---

## Phase 3: Build the Calibration Set (Days 5-6)
**Goal:** Ground truth for Zack's taste.

- [ ] Collect all artifacts from V1 and V2 runs (6 HTML builds minimum)
- [ ] Zack rates each: great / acceptable / bad (coarse 3-tier)
- [ ] Add any past Complex prototypes Zack has opinions on
- [ ] Target: 30-50 rated artifacts
- [ ] Run new pairwise judge against clear-case pairs (great vs bad)
- [ ] Measure agreement rate
- [ ] Store as structured JSON: `{ artifact_path, rating, zack_notes, date }`
- [ ] If agreement <80% on clear cases → fix rubric, not model

**Kills:** "The reviewer thinks it's good but I think it's bad" gap

**Definition of done:** Calibration set of 30+ items. Judge agrees with Zack on >80% of great-vs-bad pairs.

---

## Phase 4: Observability + Dashboard (Days 6-8)
**Goal:** Know what things cost. See pipeline state visually. Human gate in browser.

### Langfuse Setup
- [ ] Docker compose for Langfuse self-hosted
- [ ] Wire Anthropic/OpenAI/Gemini SDK calls through Langfuse
- [ ] Verify: traces showing up, cost per call visible
- [ ] Tag traces by pipeline run + phase

### Cost Controls
- [ ] Token-budget circuit breaker class (hard cap per run ~$20)
- [ ] Alert at 80% of budget
- [ ] Max iteration cap on creative loop (default: 3)
- [ ] Model version pinning (no floating aliases)

### Pipeline Dashboard (Custom)
- [ ] Design the dashboard layout:
  ```
  ┌────────────────────────────────────────────────┐
  │  Run: [name]          Phase: [current]  ⏸/$cost│
  ├──────────┬──────────┬──────────────────────────┤
  │ Concept A│ Concept B│ Concept C                │
  │ [screenshot] [screenshot] [screenshot]         │
  │ Model: X │ Model: Y │ Model: Z                 │
  │ Rank: #2 │ Rank: #1 │ Rank: #3                 │
  ├──────────┴──────────┴──────────────────────────┤
  │ Pairwise: B>A ✓  B>C ✓  A>C ⚠️ (tie)          │
  │ Cost: $X.XX │ Time: Xmin │ Iteration: N        │
  ├────────────────────────────────────────────────┤
  │ [✅ Approve] [🔄 Iterate + notes] [❌ Reject]  │
  │ Iteration notes: [text field]                  │
  └────────────────────────────────────────────────┘
  ```
- [ ] Build as static HTML + light API backend
- [ ] Reads from: LangGraph SQLite (state), Langfuse API (cost), build URLs (screenshots)
- [ ] Approve/iterate/reject buttons write back to LangGraph via `Command(resume=...)`
- [ ] Deploy via here-now
- [ ] Human gate = opening this URL in browser

**Kills:** Flying blind on cost, no debugging traces, taste gate buried in Telegram messages

**Definition of done:** Dashboard URL shows current run state + builds + scores. Can approve/reject from browser. Langfuse shows cost per phase.

---

## Phase 5: Break the Monoculture (Days 8-10)
**Goal:** Three builds that actually look different.

- [ ] Wire three model families into builder nodes:
  - Builder A: Claude Opus
  - Builder B: GPT-5 (need OpenAI API key)
  - Builder C: Gemini 2.5 Pro (have API key)
- [ ] Per-branch constraint files with:
  - **Era/reference constraints** (e.g., "Swiss modernist 1960s", "Y2K Frutiger Aero", "Brutalist web 2018")
  - **Anti-pattern exclusion lists** (explicit things NOT to do)
  - **Reference designers/URLs** (curated, not web search)
- [ ] Formalize DESIGN.md per project (replaces per-persona files)
- [ ] Pass moodboard images to vision-capable builders as reference grounding
- [ ] Run a test: same brief, 3 models, verify visible diversity

**Kills:** "Three independent concepts that look the same"

**Definition of done:** 3 builds from 3 different models are visually distinguishable without reading labels.

---

## Phase 6: Cross-Run Learning (Days 10-12)
**Goal:** Pipeline gets smarter each run.

- [ ] Install Mem0 locally (`pip install mem0ai`)
- [ ] Configure: local Qdrant vector store, Anthropic LLM, OpenAI embeddings
- [ ] Write ONLY post-human-verdict learnings:
  - "Rejected glassmorphism on Brand X"
  - "Client loved Swiss grids"
  - "Halftone SVG filter didn't render visibly"
- [ ] Pull relevant learnings into designer/builder system prompts at run start
- [ ] **Never write automated review output to memory** (memory poisoning prevention)
- [ ] Test: run 2 projects. Second project should reference learnings from first.

**Kills:** Agents repeating the same mistakes

**Definition of done:** Second pipeline run pulls learnings from first run's human-approved verdict.

---

## Phase 7: Validate End-to-End (Days 12-14)
**Goal:** Prove the full stack works on real projects.

- [ ] Run 3 real projects through the new pipeline
- [ ] After each human verdict:
  - Spend 10 min annotating failures in Langfuse
  - Add rated artifacts to calibration set
  - Write learnings to Mem0
- [ ] By project 3: ~50 calibration items
- [ ] Measure: judge agreement with Zack, cost per run, time per phase, diversity score
- [ ] Retro: what worked, what needs fixing

**Definition of done:** 3 projects completed end-to-end. Judge agrees with Zack >80% on calibration set. Cost and timing data for all runs.

---

## What NOT to Do (First 2 Weeks)

- ❌ Don't add Temporal or DBOS
- ❌ Don't add Zep or Letta (Mem0 is enough at our scale)
- ❌ Don't fine-tune a custom judge
- ❌ Don't add CrewAI, AutoGen, or MAF
- ❌ Don't try to fully automate the human gate
- ❌ Don't build a fancy React dashboard (static HTML + here-now is fine)

---

## Prerequisites / Blockers

- [ ] **OpenAI API key** — needed for GPT-5 builder (Phase 5) + text-embedding-3-small (Phase 6 Mem0)
- [ ] **Docker** — needed for Langfuse self-hosted (Phase 4)
- [ ] **Python environment** — LangGraph, Mem0, pairwise harness all Python
- [ ] **Zack's time for calibration** — need 30-60 min to rate past artifacts (Phase 3)

---

## Key Metrics to Track

| Metric | Target | Measured from |
|---|---|---|
| Judge-Zack agreement | >80% on clear cases | Calibration set |
| Visual diversity | 3 builds visually distinguishable | Human judgment |
| Cost per run | <$20 | Langfuse |
| Time per run | <30 min total | LangGraph traces |
| Phase completion rate | 100% (no skipped phases) | LangGraph state |
| Iteration count | ≤3 per run | LangGraph state |

---

## Reference Documents

- Deep Research report: `memory/research/2026-04-30-deep-research-v3-NATIVE.pdf`
- V1 retro: `memory/retros/2026-04-30-sharecard-convergence.md`
- Architecture audit: `memory/plans/architecture-audit.md`
- Previous research (v1): `memory/research/2026-04-30-deep-research-output.md`
- Previous research (v2): `memory/research/2026-04-30-deep-research-v2.md`
- Existing pipeline doc: `skills/creative-technologist/CREATIVE-PIPELINE.md`
- Existing personas: `skills/creative-technologist/personas/`

---

## Change Log

| Date | Change |
|---|---|
| 2026-04-30 | Initial plan created from Deep Research v3 findings |
