# Creative Pipeline

A multi-agent creative pipeline that generates, evaluates, and iterates on visual design prototypes using LLMs and image generation models.

Built for producing high-quality, non-generic creative output — specifically targeting the "AI slop" problem where LLM-generated designs converge on the same safe, polished, soulless aesthetics.

## Architecture

```
research → designer ×3 → approach_gate → asset_gen → builder ×3 → qa → judge → human_gate
               ↑                                                                    │
               └────────────────────── iterate ←────────────────────────────────────┘
```

### Pipeline Phases

| Phase | What | How |
|---|---|---|
| **Research** | Visual research via Refero MCP | Hermes agent with structured queries |
| **Designer ×3** | 3 parallel approach docs with different visual language mandates | Claude Opus via Hermes (3D, data viz, kinetic type) |
| **Approach Gate** | Convergence detection + ambition check | Mechanical font/color comparison + LLM conceptual check |
| **Asset Generation** | Pre-generate textures, product shots, graphics | fal.ai (FLUX, Recraft V3, Nano Banana 2) |
| **Builder ×3** | Build HTML prototypes from approach docs | Multi-model: Claude Opus + GPT-5.4 + Gemini 3.1 Pro |
| **QA Station** | Playwright-based experience testing | Render check, content fidelity, animation, mobile viewport |
| **Judge** | Bidirectional pairwise comparison | GPT-4o vision with moodboard context |
| **Human Gate** | Creative director taste check | `interrupt()` → approve / iterate / reject |

### Key Design Decisions

- **Multi-model builders** — Claude, GPT, and Gemini build in parallel to avoid single-model aesthetic monoculture
- **Bidirectional pairwise judging** — More reliable than 1-10 scoring for subjective creative work
- **Asset generation** — fal.ai generates real textures/product shots/graphics so builds aren't 100% programmatic CSS
- **Persistent personas** — Designer, Builder, Reviewer, Researcher personas accumulate feedback across runs
- **Cross-run learning** — `techniques.json` tracks what worked/failed across all runs
- **Anti-AI-slop calibration** — Taste weights derived from human ratings of 15+ builds

## Tech Stack

- **Orchestration:** [LangGraph](https://github.com/langchain-ai/langgraph) (StateGraph + SQLite checkpointer)
- **Agent execution:** [Hermes Agent](https://github.com/hermes-agent/hermes) (Claude Opus workers)
- **Direct API builders:** OpenAI (GPT-5.4), Google (Gemini 3.1 Pro)
- **Image generation:** [fal.ai](https://fal.ai) (FLUX, Recraft V3, Nano Banana 2)
- **QA:** [Playwright](https://playwright.dev) (headless browser testing)
- **Observability:** [Langfuse](https://langfuse.com) (self-hosted, optional)
- **Dashboard:** Static HTML generator (dark theme, per-run detail views)

## Quick Start

### Prerequisites

```bash
# Python 3.9+
python3 -m venv .venv
source .venv/bin/activate

# Core dependencies
pip install langgraph anthropic openai google-genai playwright fal-client

# Playwright browsers
playwright install chromium

# Hermes Agent (for Claude builders/designers)
# See: https://github.com/hermes-agent/hermes
```

### Configuration

```bash
cp .env.example .env
# Fill in your API keys
```

### Run

```bash
# Start a pipeline run
python pipeline.py run --brief examples/CREATIVE-BRIEF.md --name my-first-run

# Check status
python pipeline.py status --thread my-first-run

# Resume after human gate
python pipeline.py resume --thread my-first-run --decision approve
```

### Detached Run (survives terminal close)

```bash
./run-pipeline.sh examples/CREATIVE-BRIEF.md my-run-name
# Log: /tmp/pipeline-runs/my-run-name.log
```

## Project Structure

```
├── pipeline.py              # Main orchestrator (LangGraph StateGraph)
├── langfuse_tracing.py      # Observability wrapper (graceful degradation)
├── generate-dashboard.py    # Static HTML dashboard generator
├── run-pipeline.sh          # Detached runner script
├── personas/                # Persistent agent personas
│   ├── BUILDER.md           # Builder: code execution, anti-AI-slop mandate
│   ├── DESIGNER.md          # Designer: approach docs, asset manifests
│   ├── RESEARCHER.md        # Researcher: Refero MCP visual research
│   └── REVIEWER.md          # Reviewer: calibrated taste preferences
├── references/              # Knowledge layer (injected into agents)
│   ├── recipes.md           # Proven CSS/JS implementations
│   ├── advanced-techniques.md
│   ├── image-gen-models.md  # fal.ai model routing guide
│   └── ...
├── memory/                  # Cross-run learning
│   ├── techniques.json      # Technique registry (verdicts + learnings)
│   └── calibration-set.json # Human-rated builds (ground truth)
└── examples/
    └── CREATIVE-BRIEF.md    # Example brief (Rerank Sharecard)
```

## Calibration

The pipeline's taste is calibrated from human ratings:

| Weight | Criterion |
|---|---|
| 40% | Creative ambition (novel techniques, visual metaphors) |
| 20% | Anti-AI-slop (does it look like a human designed it?) |
| 15% | Visual depth (texture, layering, 3D) |
| 10% | Typography (intentional, not default) |
| 10% | Visual hierarchy (clear ranking, hero treatment) |
| 5% | Technical execution (clean code, no errors) |

## Cost

Typical run: **$0.80–$1.70** (3 concepts)

| Phase | Typical Cost |
|---|---|
| Research | $0.02 |
| Design (×3) | $0.05 |
| Approach Gate | $0.60 |
| Asset Gen (×3) | $0.90 |
| Build (×3) | $0.20 |
| Judge | $0.08 |
| **Total** | **~$1.70** |

## License

MIT

## Author

Built by [Zack Chang](https://github.com/changzack) with [Mira](https://openclaw.ai) (OpenClaw agent).
