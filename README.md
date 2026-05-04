# Creative Pipeline

A multi-agent creative pipeline that generates, evaluates, and iterates on visual design artifacts using LLMs.

Built with [LangGraph](https://github.com/langchain-ai/langgraph) for orchestration, multiple foundation models for diverse output, and a human-in-the-loop taste gate for quality control.

## What It Does

Given a creative brief, the pipeline:

1. **Research** — Searches design references via [Refero.design](https://refero.design) MCP, builds a visual moodboard with extracted design tokens
2. **Design** — 3 parallel designers (Claude Opus, GPT-5.4, Gemini 3.1 Pro) produce approach documents with build contracts
3. **Approach Gate** — Mechanical + LLM convergence check prevents all 3 designers from producing the same thing
4. **Asset Generation** — [fal.ai](https://fal.ai) generates textures, product shots, and graphics from designer manifests
5. **Build** — Each model builds a self-contained HTML artifact with embedded assets
6. **QA Station** — Playwright-based browser testing: content fidelity, viewport rendering, console errors, animation detection
7. **Pairwise Judge** — Bidirectional comparison with position-bias control (GPT-4o vision)
8. **Human Gate** — Creative director reviews via mobile evaluation app, submits structured feedback
9. **Wiki Ingest** — Feedback routes to technique pages, model profiles, and taste patterns for cross-run learning

## Architecture

```
Brief → Research → Designer ×3 → Approach Gate → Asset Gen → Builder ×3 → QA → Judge → Human Gate
                                                                                          ↓
                                                                              Wiki ← Structured Feedback
                                                                                          ↓
                                                                                    Iterate / Ship
```

**Key design decisions:**
- **Multi-model diversity** — Claude Opus, GPT-5.4, and Gemini 3.1 Pro as parallel builders prevent monoculture output
- **Pairwise > scalar scoring** — More reliable for subjective creative evaluation ([research](https://arxiv.org/abs/2403.16950))
- **File-based memory** — Pipeline Wiki (markdown) over databases. Knowledge compounds across runs without infrastructure
- **`asset://` protocol** — Builders write lightweight refs, post-processor injects base64 data URIs. Self-contained HTML output
- **Constitutional evaluation** — Personas accumulate learnings from human verdicts (inspired by [DSPy GEPA](https://arxiv.org/abs/2507.19457))

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

The human gate uses a mobile-first evaluation app (generated per-run) that captures:

- **Per-concept quick rating** — 🔥 Great / ✅ OK / ❌ Bad
- **5-dimension scores** — Creative Ambition (40%), AI Slop Check (20%), Visual Depth (15%), Typography (10%), Hierarchy (10%)
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

Typical run: **$0.30 - $0.90** depending on iteration rounds.
- Budget cap: `MAX_COST_USD = 20.0` with 80% alert
- Asset generation: $0.003 - $0.08 per image (fal.ai)
- Per-call token tracking with cost report JSON per run

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
