# Creative Pipeline

A multi-agent creative pipeline that generates, evaluates, and iterates on visual design artifacts using LLMs.

Built with [LangGraph](https://github.com/langchain-ai/langgraph) for orchestration, multiple foundation models for diverse output, and a human-in-the-loop taste gate for quality control.

## What It Does

Given a creative brief, the pipeline:

1. **Research** — Searches design references via [Refero.design](https://refero.design) MCP, builds a visual moodboard. Then generates **brief-aware diversification axes** (3 axes tailored to the artifact type, not hardcoded share-card defaults).
2. **Design** — 3 parallel designers (Claude Opus 4.7, GPT-5.5, Gemini Pro Latest) produce approach docs anchored to their assigned axis.
3. **Approach Gate** — Mechanical + LLM convergence check on approach docs.
4. **Asset Generation** — [fal.ai](https://fal.ai) generates textures, product shots, and graphics from designer manifests.
5. **Build (initial)** — Each model builds a self-contained HTML artifact. The unified builder routes by `builder_mode` so the same node handles all build phases.
6. **QA Loop** — Per-concept loop. Folds structural checks + walker-driven playability into one source of truth. Loops with builder (`qa_fix` mode, same original model) up to 20 iterations until the artifact is functionally complete.
7. **Judge Loop** — Per-concept scoring with the REVIEWER persona. Hybrid threshold: weighted total ≥7.0 AND no single dimension <5.0 AND AI Slop not flagged. Below-threshold concepts loop with builder (`judge_polish` mode) using REVIEWER's Priority Fixes as feedback. Up to 20 iterations per concept.
8. **Pairwise Rank** — Once thresholds pass, bidirectional pairwise tournament ranks survivors for the human's eval app. Position-bias controlled.
9. **Human Gate** — Creative director reviews via mobile evaluation app, submits structured feedback.
10. **Wiki Ingest** — Global wiki gets cross-brief lessons. Per-brief learnings auto-route to `<brief>.LEARNINGS.md`.

## Architecture

```
Brief → Research → Designer ×3 → Approach Gate → Asset Gen → Builder ×3 (initial)
                                                                       ↓
                                                              QA Loop (per concept)
                                                              → builder mode=qa_fix
                                                              ↑ ×20 max
                                                                       ↓
                                                            Judge Loop (per concept)
                                                            → builder mode=judge_polish
                                                            ↑ ×20 max
                                                                       ↓
                                                              Pairwise Rank
                                                                       ↓
                                                                Human Gate
                                                                       ↓
                                                              Wiki + LEARNINGS.md
                                                                       ↓
                                                              Iterate / Deploy
```

**Key design decisions:**

- **Frontier-only models** — Claude Opus 4.7, GPT-5.5, gemini-pro-latest (Google's server-side alias that auto-tracks the latest Pro).
- **Per-concept-model continuity** — Concept N is ALWAYS patched by its original builder model across all loop modes. Prevents the convergence failure where a single shared patch model collapses 3 distinct concepts into one.
- **Unified builder with mode dispatch** — One `builder_node` handles initial / qa_fix / judge_polish via `builder_mode` state. Less code duplication, easier to extend.
- **Experience walker** — Playwright-driven walker clicks through every build, captures journey screenshots, detects dead/inert prototypes. The judge sees the journey, not just a splash screen.
- **Threshold-gated quality** — The judge loop pushes builds above an absolute quality threshold (not just relative pairwise wins) before the human ever sees them.
- **REVIEWER-driven scoring** — The judge persona (REVIEWER.md) is the single source of truth for scoring criteria. The judge prompt compiles {{persona}} verbatim into the system prompt.
- **Hybrid threshold** — Weighted total ≥7.0 + no dimension <5.0 + AI Slop not flagged. Catches both "weak overall" and "one fatal flaw" failure modes.
- **Cost circuit breaker** — Hard $20 ceiling per run. If exceeded, both loops break gracefully and proceed to human gate with current state.
- **Streaming for long calls** — All Anthropic calls >21K tokens use streaming (mandatory per SDK for 10min+ requests).
- **Per-brief LEARNINGS** — `<brief>.LEARNINGS.md` siblings keep brief-specific lessons scoped. Global wiki holds only cross-brief taste rules.
- **File-based memory** — Pipeline Wiki (markdown) over databases.
- **`asset://` protocol with contract enforcement** — Builders reference assets by slug from a strict commissioned list. Hallucinated refs get SVG fallbacks + flagged in QA.

## Quick Start

### Prerequisites
- Python 3.9+
- API keys: Anthropic, OpenAI, Google AI
- Optional: fal.ai (asset generation), Langfuse (observability)

### Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install langgraph anthropic openai google-genai playwright fal-client
playwright install chromium

cp .env.example .env
# Edit .env with your API keys
```

### Run
```bash
# Start a pipeline run
python pipeline.py run --brief examples/CREATIVE-BRIEF.md --name my-first-run

# Check status
python pipeline.py status --thread my-first-run

# Resume after human gate review
python pipeline.py resume --thread my-first-run
```

### Evaluate
```bash
# Generate mobile evaluation app
python generate-eval-app.py --run-dir overnight-runs/my-first-run

# Generate dashboard
python generate-dashboard.py --run-dir overnight-runs/my-first-run
```

## Project Structure

```
pipeline.py              # Main orchestrator (~2200 lines, 9 LangGraph nodes)
generate-eval-app.py     # Mobile-first evaluation app generator
generate-dashboard.py    # Run dashboard generator
langfuse_tracing.py      # Optional Langfuse observability wrapper
run-pipeline.sh          # Detached runner (survives terminal closure)

personas/                # Agent persona files (accumulate learnings)
  BUILDER.md             # Build agent — anti-AI-slop mandate, asset integration
  DESIGNER.md            # Design agent — approach docs with build contracts
  RESEARCHER.md          # Research agent — Refero MCP, moodboard curation
  REVIEWER.md            # Judge agent — calibrated taste weights

references/              # Knowledge base (injected into agent prompts)
  advanced-techniques.md # CSS/WebGL/SVG techniques catalog
  recipes.md             # Proven implementation recipes
  creative-patterns.md   # Design patterns that score well
  image-gen-models.md    # fal.ai model routing guide
  ...

wiki/                    # Pipeline Wiki — compounds across runs
  aesthetics/            # What scores well, anti-patterns
  techniques/            # Technique evidence (3D transforms, SVG grain, etc.)
  models/                # Per-model performance profiles
  research/              # Research playbooks
  builds/                # Build patterns (mobile viewport, content fidelity)

memory/                  # Cross-run learning
  calibration-set.json   # Human-rated builds (ground truth)
  techniques.json        # Technique registry

examples/                # Brief templates
docs/                    # Architecture docs, plans, reports
```

## The Pipeline Wiki

Inspired by [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — knowledge compounds with every run:

- **Human verdicts** (structured feedback from eval app) auto-route to wiki pages
- **Technique evidence** accumulates: "3D CSS transforms → proven, highlighted by CD in run X"
- **Model profiles** track strengths/weaknesses with evidence from actual runs
- **Anti-patterns** grow from real failures, not assumptions

The wiki is the pipeline's long-term memory. Raw sources (run artifacts) are immutable; wiki pages are LLM-maintained summaries that get smarter over time.

## Evaluation System

The judge layer uses a 7-dimension weighted scoring rubric driven by the REVIEWER persona:

| Dimension | Weight | What it catches |
|---|---|---|
| Creative Ambition | 40% | Novel concepts and visual techniques (vs "dark card + light text") |
| AI Slop Check | 20% (hard-cap) | Center-itis, gradient blobs, safe spacing, template energy. If flagged → weighted total clamped to ≤4.0 |
| Brief Fit | 20% | Does the build deliver the brief's actual product / sample data / outcome requirements? Wrong product = severe penalty regardless of polish |
| Distinctiveness | 10% | Does this concept feel meaningfully different from siblings in the same run? Same palette + composition + tech = severe penalty |
| Visual Depth | 5% | 3D transforms, texture, layering, material quality |
| Typography | 3% | Genuine hierarchy via weight/size/tracking |
| Hierarchy & Readability | 2% | Information hierarchy visible at a glance |
| Technical Execution | binary | Does it render and run? Auto-fail if not |

**Hybrid passing threshold:**
- Weighted total ≥ 7.0
- AND no single dimension < 5.0
- AND AI Slop not flagged

The judge loop iterates with the builder until each concept either passes the threshold or hits 20 iterations.

The human gate then sees pre-polished builds via a mobile-first evaluation app that captures:
- **Per-concept quick rating** — 🔥 Great / ✅ OK / ❌ Bad
- **Dimension scores** — mirrors the judge rubric
- **Technique tags** — Landed / Standout / Partial / Missed
- **Freeform notes** per concept

Research basis: [DSPy GEPA](https://arxiv.org/abs/2507.19457) (textual feedback > scores), [Agentic Design Review System](https://arxiv.org/abs/2508.10745) (multi-dimension decomposition), RLHF literature (pairwise > scalar).

## Design System Enforcement

Optional `--design-system` flag enforces token compliance:
- Greps built HTML for off-system fonts
- Checks color values against palette (20-unit RGB tolerance)
- Injects design tokens into designer + builder prompts
- QA station flags violations

## Cost

Typical run: **$2 - $10** with the QA + Judge loops active, depending on iteration depth.
- Hard cap: `MAX_COST_USD = 20.0` (cost circuit breaker; both loops abort and proceed to human gate when hit)
- Asset generation: $0.003 - $0.08 per image (fal.ai)
- Per-call token tracking with cost report JSON per run
- Frontier-model output budgets: Opus 4.7 (128K), GPT-5.5 (100K), Gemini Pro Latest (65K) — streaming on all >21K calls

## Key Learnings (from 15+ pipeline runs)

1. **Hierarchy > Ambition** — Strong information hierarchy is table stakes; creative ambition only counts when hierarchy is solid
2. **Multi-model prevents monoculture** — Same model ×3 produces same output ×3, regardless of different prompts
3. **Pairwise comparison beats 1-10 scoring** — Models can't reliably assign absolute scores to creative work
4. **Texture must not touch readable text** — Decorative effects on backgrounds only
5. **Brief drift is the #1 failure mode** — Content fidelity checks in QA catch builders who build the wrong thing
6. **Motion design is a powerful differentiator** — Intentional animation elevates builds more than static visual techniques
7. **Research must be structured** — Browser-scraping design sites fails; API-based tools (Refero MCP) work
8. **100% programmatic output = AI slop** — Mixing generated imagery with code produces design-grade output

## License

MIT
