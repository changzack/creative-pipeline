# Pipeline V3 Build Plan
**Created:** 2026-04-30
**Updated:** 2026-05-01
**Status:** Phases 1-2 complete, Phase 4 partially done
**Source:** Claude Deep Research v3 field report + V1/V2 retros + smoke test forensics

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

## Phase 1: Fix the Spine (Days 1-3) ✅ COMPLETE
**Goal:** Pipeline state survives crashes. No more cron polling.

- [x] Install LangGraph + dependencies
- [x] Create `pipeline.py` — 8-node LangGraph StateGraph (~24KB)
- [x] Wrap Hermes spawns in node functions
- [x] `Send()` API for parallel fan-out (3 designers, 3 builders)
- [x] SQLite checkpointer for durable state
- [x] `interrupt()` for human taste gate
- [x] Basic CLI (`python pipeline.py run/resume/status`)
- [x] Process survival: `nohup` + runner script + `start_new_session=True`
- [x] Smoke test: full pipeline ran overnight (research → designers → gate → builders → judge → human_gate)
- [ ] Install LangGraph Studio desktop app for debugging

**Lessons:**
- OpenClaw exec sessions SIGTERM all child processes — even disowned. Must use nohup with external runner script.
- `start_new_session=True` on Popen is critical for Hermes subprocess survival.
- LangGraph `interrupt()` returns a tuple in stream events, not a dict — need isinstance check.

---

## Phase 2: Fix the Evaluator (Days 3-5) ✅ COMPLETE
**Goal:** Scores match Zack's judgment.

- [x] Implement bidirectional pairwise tournament
- [x] Screenshot builds via Playwright (headless Chromium, 1080×1920)
- [x] Send screenshots to vision-capable judge (GPT-4o)
- [x] Cross-model judging: builders=Claude, judge=GPT-4o
- [x] Anti-pattern checklist in judge prompt
- [x] Position bias control: both directions, only count agreed winners
- [x] Forced preference (no TIE allowed — dramatically reduces cop-outs)
- [x] Output: ranked list with win counts + per-comparison justifications + reasoning
- [x] Results saved to `reviews/pairwise-results.json`

**Lessons:**
- Allowing TIE → judge defaults to diplomatic TIE. Forced preference works much better.
- Vision-based judging (screenshots) is essential — code comparison alone can't catch rendering bugs.

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

## Phase 4: Observability + Dashboard (Days 6-8) 🔄 PARTIAL
**Goal:** Know what things cost. See pipeline state visually. Human gate in browser.

### Langfuse Setup
- [ ] Docker compose for Langfuse self-hosted
- [ ] Wire Anthropic/OpenAI/Gemini SDK calls through Langfuse
- [ ] Verify: traces showing up, cost per call visible
- [ ] Tag traces by pipeline run + phase

### Cost Controls
- [x] Token-budget circuit breaker (hard cap $20/run, alert at 80%)
- [x] Per-call token counting with phase breakdown
- [x] Cost rates for Claude Opus, GPT-4o, Gemini 2.5 Pro
- [x] `save_cost_report()` writes JSON to run directory
- [ ] Max iteration cap on creative loop (default: 3) — in state, not enforced
- [ ] Model version pinning (no floating aliases)

### Pipeline Dashboard (Custom)
- [x] `generate-dashboard.py` — static HTML generator from run directory
- [x] Per-run detail view: embedded screenshots, pairwise results, approach docs, moodboard
- [x] Multi-project index view (`--index`): scans all runs, thumbnail cards, stats footer
- [x] Dark theme, gold/silver/bronze rank badges, responsive
- [x] Deployed to here-now
- [ ] Approve/iterate/reject buttons (currently read-only; decisions via Telegram)

**Kills:** Flying blind on cost, no debugging traces, taste gate buried in Telegram messages

**Definition of done:** ~~Dashboard URL shows current run state + builds + scores. Can approve/reject from browser. Langfuse shows cost per phase.~~ Partial: dashboard shows state + builds + scores. Approve/reject still via Telegram. Langfuse not yet set up.

---

## Phase 4.5: Builder Fidelity (NEW — from smoke test forensics)
**Goal:** Builders produce output that matches their spec, not a generic default.

### Problem Diagnosed (May 1, 2026)
Smoke test forensic analysis revealed: approach docs are genuinely different (different fonts, colors, layout specs) but Builder 1 used Builder 0's fonts AND colors instead of its own spec. The model's aesthetic prior overwhelms spec differences when running the same model 3x.

Three compounding issues:
1. **Spec drift** — builder ignores its own approach doc's concrete specs (fonts, colors) and defaults to a "safe" aesthetic basin
2. **Blind building** — builder writes HTML without ever seeing the rendered result
3. **No compliance verification** — no automated check that the build matches the spec

### Fixes (ordered by implementation priority)

#### A. Automated Spec Compliance Gate (cheap, no LLM needed)
- [ ] After build completes, programmatically extract from the approach doc:
  - Required font families (grep for Google Fonts names)
  - Required hex colors (top 3-5 from palette table)
  - Required CSS techniques (e.g., "halftone", "obi-strip", specific class names)
- [ ] Grep the built HTML for each requirement
- [ ] If compliance < 80% (e.g., wrong fonts, missing colors), **fail the build and re-run** with explicit error: "Your spec says Oswald but you used Bebas Neue. Fix it."
- [ ] Max 2 compliance retries before escalating

#### B. Build → Screenshot → Self-Review Loop
- [ ] After initial build, Playwright screenshots at 1080×1920
- [ ] Send screenshot + approach doc back to the builder: "Here's what your code renders. Compare to your approach doc. Fix any discrepancies."
- [ ] One round of self-review (not a loop — diminishing returns after round 1)
- [ ] Track: what changed between build v1 and v2

#### C. Moodboard injection to builder
- [ ] Pass 2-3 moodboard reference images (base64, compressed) to the builder alongside the approach doc
- [ ] "Here's what the designer was looking at when they wrote this spec. Your output should feel like it belongs in this visual family."
- [ ] Only pass images if builder's model supports vision (Claude, GPT-4o, Gemini all do)

### Key Insight
The problem is NOT prompt quality — the approach docs contain exact hex codes, font names, pixel sizes. The problem is the builder model's prior overwhelming explicit instructions when running the same model 3x. Fix A catches this mechanically. Fix B catches rendering bugs. Fix C grounds the builder in visual context.

**Kills:** "Specs are different but builds look the same", rendering bugs, spec drift

**Definition of done:** Each build uses the fonts and colors from its own approach doc (verified programmatically). At least one round of visual self-review before judge.

---

## Phase 5: Break the Monoculture (Days 8-10)
**Goal:** Three builds that actually look different.

- [ ] Wire three model families into builder nodes:
  - Builder A: Claude Opus (direct API)
  - Builder B: GPT-5 / GPT-4o (OpenAI API — have key)
  - Builder C: Gemini 2.5 Pro (Google API — have key)
- [ ] Each model calls its own API directly (not all through Hermes/Opus)
- [ ] Per-branch constraint files with:
  - **Era/reference constraints** (e.g., "Swiss modernist 1960s", "Y2K Frutiger Aero", "Brutalist web 2018")
  - **Anti-pattern exclusion lists** (explicit things NOT to do)
  - **Reference designers/URLs** (curated, not web search)
- [ ] Formalize DESIGN.md per project (replaces per-persona files)
- [ ] Pass moodboard images to vision-capable builders as reference grounding
- [ ] Run a test: same brief, 3 models, verify visible diversity
- [ ] Combined with Phase 4.5: spec compliance gate catches same-model drift, multi-model prevents aesthetic basin convergence

**Kills:** "Three independent concepts that look the same"

**Definition of done:** 3 builds from 3 different models are visually distinguishable without reading labels. Each build's fonts/colors match its spec (Phase 4.5 gate passes).

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
| 2026-05-01 | Phases 1-2 marked complete. Phase 4 partially done (cost tracking + dashboard). Added Phase 4.5 (Builder Fidelity) from smoke test forensics: spec compliance gate, build→screenshot→self-review loop, moodboard injection. Updated Phase 5 to use direct multi-model API calls instead of all-through-Hermes. |
