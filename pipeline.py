#!/usr/bin/env python3
"""
Creative Pipeline V3 — LangGraph Orchestrator
Replaces: cron polling, signal files, CREATIVE-PIPELINE.md manual execution

Usage:
  python pipeline.py run --brief "path/to/brief.md" --name "sharecard-v3"
  python pipeline.py resume --thread "sharecard-v3"
  python pipeline.py status --thread "sharecard-v3"
"""

import os
import sys
import json
import sqlite3
import subprocess
import itertools
import time
import argparse
from pathlib import Path
from typing import TypedDict, Annotated, Literal, Optional, List, Dict
from operator import add

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Command, Send

from anthropic import Anthropic
from openai import OpenAI
# import google.generativeai as genai  # will use via langchain

# Observability
from langfuse_tracing import tracer

# ── Config ──────────────────────────────────────────────────────
WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))
PIPELINE_DIR = WORKSPACE / "pipeline"
RUNS_DIR = WORKSPACE / "overnight-runs"
HERMES_BRIDGE = WORKSPACE / "skills/hermes-bridge/scripts/hermes-run.sh"
HERMES_STATUS = WORKSPACE / "skills/hermes-bridge/scripts/hermes-status.sh"
DB_PATH = PIPELINE_DIR / "pipeline.db"

# API clients
anthropic_client = Anthropic()
openai_client = OpenAI()
# genai configured via langchain-google-genai

# Budget
MAX_COST_USD = 20.0
MAX_ITERATIONS = 3

# Cost per 1M tokens (approximate, 2026 pricing)
COST_PER_1M = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
}

# Run-level cost accumulator
_run_costs = {"total_usd": 0.0, "by_phase": {}, "calls": []}

def track_cost(model: str, input_tokens: int, output_tokens: int, phase: str = "unknown"):
    """Track cost of an API call."""
    rates = COST_PER_1M.get(model, {"input": 5.0, "output": 15.0})
    cost = (input_tokens / 1_000_000 * rates["input"]) + (output_tokens / 1_000_000 * rates["output"])
    _run_costs["total_usd"] += cost
    _run_costs["by_phase"][phase] = _run_costs["by_phase"].get(phase, 0.0) + cost
    _run_costs["calls"].append({
        "model": model, "input": input_tokens, "output": output_tokens,
        "cost": round(cost, 4), "phase": phase, "time": time.strftime("%H:%M:%S"),
    })
    if _run_costs["total_usd"] > MAX_COST_USD * 0.8:
        print(f"  ⚠️  Cost alert: ${_run_costs['total_usd']:.2f} / ${MAX_COST_USD:.2f} (80% threshold)")
    if _run_costs["total_usd"] > MAX_COST_USD:
        raise RuntimeError(f"Budget exceeded: ${_run_costs['total_usd']:.2f} > ${MAX_COST_USD:.2f}")
    return cost


def save_cost_report(run_name: str):
    """Save cost breakdown to run directory."""
    report_path = RUNS_DIR / run_name / "cost-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    import json as jm
    _run_costs["total_usd"] = round(_run_costs["total_usd"], 4)
    for k in _run_costs["by_phase"]:
        _run_costs["by_phase"][k] = round(_run_costs["by_phase"][k], 4)
    report_path.write_text(jm.dumps(_run_costs, indent=2))
    print(f"\n💰 Total cost: ${_run_costs['total_usd']:.2f}")
    for phase, cost in sorted(_run_costs["by_phase"].items()):
        print(f"   {phase}: ${cost:.4f}")


# ── State Schema ────────────────────────────────────────────────
class PipelineState(TypedDict):
    # Inputs
    name: str
    brief: str
    
    # Phase outputs
    research: Optional[dict]
    moodboard: list[str]  # paths to reference images
    
    # Fan-in from parallel agents (Annotated[list, add] = auto-concatenate)
    approaches: Annotated[list[dict], add]
    builds: Annotated[list[dict], add]
    
    # Gate results
    gate_result: Optional[dict]
    
    # Evaluation
    pairwise_results: list[dict]
    ranking: list[dict]
    
    # Human gate
    human_decision: Optional[str]  # "approve" | "iterate" | "reject"
    human_feedback: Optional[str]
    
    # Loop control
    iteration: int
    phase: str
    
    # Cost tracking
    cost_usd: float
    phase_costs: dict  # {phase_name: cost}
    
    # Timestamps
    started_at: str
    completed_at: Optional[str]


# ── Cross-Run Learning (Phase 6) ────────────────────────────────
MEMORY_DIR = PIPELINE_DIR / "memory"
TECHNIQUES_FILE = MEMORY_DIR / "techniques.json"

def load_technique_registry() -> dict:
    """Load the technique registry from disk."""
    if TECHNIQUES_FILE.exists():
        return json.loads(TECHNIQUES_FILE.read_text())
    return {"_schema": "pipeline.techniques.v1", "techniques": [], "verdicts": []}


def save_technique_registry(registry: dict):
    """Save the technique registry to disk."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    TECHNIQUES_FILE.write_text(json.dumps(registry, indent=2))


def record_verdict(run_name: str, decision: str, feedback: str,
                   ranking: list, builds: list, approaches: list):
    """Record a human verdict. ONLY called after human decision, never from automated review.
    This is the ONLY write path to the technique registry."""
    registry = load_technique_registry()
    
    verdict = {
        "run": run_name,
        "decision": decision,  # approve / iterate / reject
        "feedback": feedback,
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "ranking": [{"index": r.get("build_index", r.get("index")), "wins": r.get("wins", 0)} for r in ranking[:3]],
    }
    registry["verdicts"].append(verdict)
    
    # Extract technique learnings from the verdict
    for build in builds:
        idx = build.get("index", 0)
        approach_content = ""
        for a in approaches:
            if a.get("designer_id") == build.get("designer_id"):
                approach_content = a.get("content", "")
                break
        
        contract = extract_build_contract(approach_content)
        fonts = extract_fonts_from_contract(contract)
        techniques = extract_techniques_from_contract(contract)
        
        # Was this build in the winner position?
        rank = None
        for r in ranking:
            if r.get("build_index") == idx or r.get("index") == idx:
                rank = r.get("rank", None)
                break
        
        # Record technique outcomes
        for tech in techniques:
            entry = {
                "technique": tech["name"],
                "css": tech.get("css_check", ""),
                "run": run_name,
                "rank": rank,
                "verdict": decision,
                "model": build.get("model", "unknown"),
                "date": time.strftime("%Y-%m-%d"),
            }
            registry["techniques"].append(entry)
    
    # If there's specific feedback, record it as a learning
    if feedback:
        registry.setdefault("learnings", []).append({
            "run": run_name,
            "feedback": feedback,
            "decision": decision,
            "date": time.strftime("%Y-%m-%d"),
        })
    
    save_technique_registry(registry)
    print(f"  📝 Recorded verdict: {decision} ({len(registry['techniques'])} techniques, {len(registry['verdicts'])} verdicts)")


def get_relevant_learnings(brief: str, max_items: int = 10) -> str:
    """Pull relevant learnings from past runs to inject into prompts.
    Simple keyword matching — upgrade to embeddings later if needed."""
    registry = load_technique_registry()
    
    if not registry.get("verdicts") and not registry.get("learnings"):
        return ""
    
    output_parts = []
    
    # Recent verdicts with feedback
    recent_verdicts = registry.get("verdicts", [])[-5:]
    if recent_verdicts:
        output_parts.append("## Learnings from Past Runs")
        for v in recent_verdicts:
            if v.get("feedback"):
                emoji = "✅" if v["decision"] == "approve" else "❌" if v["decision"] == "reject" else "🔄"
                output_parts.append(f"- {emoji} Run `{v['run']}` ({v['decision']}): {v['feedback'][:200]}")
    
    # Technique outcomes — what worked vs didn't
    techniques = registry.get("techniques", [])
    if techniques:
        # Group by technique name
        tech_stats = {}
        for t in techniques:
            name = t["technique"]
            if name not in tech_stats:
                tech_stats[name] = {"approved": 0, "rejected": 0, "total": 0, "best_rank": 99}
            tech_stats[name]["total"] += 1
            if t.get("verdict") == "approve":
                tech_stats[name]["approved"] += 1
            elif t.get("verdict") == "reject":
                tech_stats[name]["rejected"] += 1
            if t.get("rank") and t["rank"] < tech_stats[name]["best_rank"]:
                tech_stats[name]["best_rank"] = t["rank"]
        
        # Surface techniques with clear signal
        winners = [(n, s) for n, s in tech_stats.items() if s["approved"] > 0]
        losers = [(n, s) for n, s in tech_stats.items() if s["rejected"] > 0 and s["approved"] == 0]
        
        if winners:
            output_parts.append("\n## Techniques That Worked")
            for name, stats in winners[:5]:
                output_parts.append(f"- ✅ **{name}** — approved {stats['approved']}x, best rank #{stats['best_rank']}")
        
        if losers:
            output_parts.append("\n## Techniques That Failed")
            for name, stats in losers[:5]:
                output_parts.append(f"- ❌ **{name}** — rejected {stats['rejected']}x, never approved")
    
    # Explicit learnings
    learnings = registry.get("learnings", [])[-5:]
    if learnings:
        output_parts.append("\n## Explicit Feedback")
        for l in learnings:
            output_parts.append(f"- {l['feedback'][:200]}")
    
    return "\n".join(output_parts) if output_parts else ""


# ── Knowledge Layer ─────────────────────────────────────────────
REFERENCES_DIR = WORKSPACE / "skills/creative-technologist/references"

def load_reference(filename: str, max_chars: Optional[int] = None, section: Optional[str] = None) -> str:
    """Load a reference doc from the skills directory.
    Respects context budget with max_chars truncation.
    Can extract a specific section by heading."""
    path = REFERENCES_DIR / filename
    if not path.exists():
        print(f"  ⚠️  Reference missing: {filename}")
        return ""
    content = path.read_text()
    if section:
        if section in content:
            start = content.index(section)
            next_heading = content.find("\n## ", start + len(section))
            content = content[start:next_heading] if next_heading > 0 else content[start:]
        else:
            print(f"  ⚠️  Section '{section}' not found in {filename}")
    if max_chars:
        content = content[:max_chars]
    return content


def extract_build_contract(approach_content: str) -> str:
    """Extract the BUILD CONTRACT section from an approach doc."""
    # Try multiple heading variations
    for marker in ["## BUILD CONTRACT", "## DESIGN CONTRACT", "## Non-Negotiables"]:
        if marker in approach_content:
            return approach_content.split(marker, 1)[1]
    return ""


def extract_fonts_from_contract(contract: str) -> dict:
    """Extract required and forbidden fonts from a build contract."""
    import re
    result = {"required": [], "forbidden": []}
    
    lines = contract.split("\n")
    in_required = False
    in_forbidden = False
    
    for line in lines:
        lower = line.lower().strip()
        if "required font" in lower:
            in_required = True
            in_forbidden = False
            continue
        elif "forbidden font" in lower:
            in_forbidden = True
            in_required = False
            continue
        elif lower.startswith("###"):
            in_required = False
            in_forbidden = False
            continue
        
        # Extract font names from font-family declarations or plain text
        font_matches = re.findall(r"'([^']+)'", line)
        if not font_matches:
            # Try comma-separated list: "Bebas Neue, IBM Plex Mono"
            if in_forbidden and "," in line:
                font_matches = [f.strip() for f in line.split(",") if f.strip() and len(f.strip()) > 2]
            elif in_forbidden and line.strip().startswith("- "):
                name = line.strip().lstrip("- ").strip()
                if name and len(name) > 2 and not name.startswith("#"):
                    font_matches = [name]
        
        if in_required:
            result["required"].extend(font_matches)
        elif in_forbidden:
            result["forbidden"].extend(font_matches)
    
    return result


def extract_colors_from_contract(contract: str) -> dict:
    """Extract required and forbidden colors from a build contract."""
    import re
    result = {"required": [], "forbidden": []}
    
    lines = contract.split("\n")
    in_required = False
    in_forbidden = False
    
    for line in lines:
        lower = line.lower().strip()
        if "required color" in lower:
            in_required = True
            in_forbidden = False
            continue
        elif "must not contain" in lower or "forbidden color" in lower:
            in_forbidden = True
            in_required = False
        elif lower.startswith("###") and "color" not in lower:
            in_required = False
            in_forbidden = False
            continue
        
        # Extract hex colors
        colors = re.findall(r"#[0-9a-fA-F]{6}", line)
        if in_required or (not in_forbidden and "BACKGROUND" in line or "PRIMARY" in line or "ACCENT" in line or "SECONDARY" in line):
            result["required"].extend(colors)
        if in_forbidden or "must not" in lower or "Must NOT" in line:
            result["forbidden"].extend(colors)
    
    return result


def extract_techniques_from_contract(contract: str) -> list:
    """Extract required CSS techniques with their grep-able implementation hints."""
    import re
    techniques = []
    lines = contract.split("\n")
    in_techniques = False
    
    for line in lines:
        lower = line.lower().strip()
        if "required css" in lower or "required technique" in lower:
            in_techniques = True
            continue
        elif lower.startswith("###"):
            in_techniques = False
            continue
        
        if in_techniques and line.strip().startswith("- ") or in_techniques and line.strip().startswith("| "):
            # Extract the CSS property hint (inside backticks or after colon)
            css_hints = re.findall(r"`([^`]+)`", line)
            name = line.strip().lstrip("- |").split(":")[0].split("|")[0].strip()
            if css_hints:
                techniques.append({"name": name, "css_check": css_hints[0]})
            elif name:
                techniques.append({"name": name, "css_check": name})
    
    return techniques


def check_spec_compliance(html_path: Path, contract: str) -> dict:
    """Grep-based spec compliance check. No LLM, no cost, deterministic."""
    if not html_path.exists():
        return {"pass": False, "failures": ["BUILD FILE MISSING"], "checks": 0}
    
    html = html_path.read_text().lower()
    results = {"pass": True, "failures": [], "warnings": [], "checks": 0}
    
    fonts = extract_fonts_from_contract(contract)
    colors = extract_colors_from_contract(contract)
    techniques = extract_techniques_from_contract(contract)
    
    # Check required fonts
    for font in fonts["required"]:
        results["checks"] += 1
        if font.lower() not in html:
            results["failures"].append(f"MISSING REQUIRED FONT: {font}")
            results["pass"] = False
    
    # Check forbidden fonts
    for font in fonts["forbidden"]:
        results["checks"] += 1
        if font.lower() in html:
            results["failures"].append(f"CONTAINS FORBIDDEN FONT: {font}")
            results["pass"] = False
    
    # Check required colors
    for color in colors["required"]:
        results["checks"] += 1
        if color.lower() not in html:
            results["warnings"].append(f"MISSING REQUIRED COLOR: {color}")
            # Colors are warnings not failures — builder might use close variants
    
    # Check forbidden colors
    for color in colors["forbidden"]:
        results["checks"] += 1
        if color.lower() in html:
            results["failures"].append(f"CONTAINS FORBIDDEN COLOR: {color}")
            results["pass"] = False
    
    # Check techniques
    for tech in techniques:
        results["checks"] += 1
        if tech["css_check"].lower() not in html:
            results["warnings"].append(f"MISSING TECHNIQUE: {tech['name']} (looking for: {tech['css_check']})")
    
    return results


# ── Utility Functions ───────────────────────────────────────────

def run_hermes(job_id: str, task_content: str, max_time: int = 1200, max_turns: int = 40) -> dict:
    """Spawn a Hermes agent job (fully detached) and wait for completion."""
    job_dir = Path(f"/tmp/hermes-jobs/{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Write task to file
    task_file = job_dir / ".task.md"
    task_file.write_text(task_content)
    
    # Use hermes-run.sh which handles detachment properly
    # The bridge script uses nohup + subshell + disown
    spawn = subprocess.Popen(
        ["bash", str(HERMES_BRIDGE), "--job-id", job_id,
         "--task-file", str(task_file),
         "--max-time", str(max_time), "--max-turns", str(max_turns), "--quiet"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,  # Fully detach from parent process group
    )
    
    # Don't wait for spawn — it returns immediately after detaching hermes
    try:
        spawn.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass  # Bridge script may still be setting up, that's fine
    
    # Poll for completion via signal files
    deadline = time.time() + max_time + 60
    while time.time() < deadline:
        done_file = Path(f"/tmp/hermes-jobs/{job_id}/.done")
        failed_file = Path(f"/tmp/hermes-jobs/{job_id}/.failed")
        killed_file = Path(f"/tmp/hermes-jobs/{job_id}/.killed")
        
        if done_file.exists():
            return {"status": "done", "job_id": job_id}
        elif failed_file.exists():
            return {"status": "failed", "job_id": job_id}
        elif killed_file.exists():
            return {"status": "killed", "job_id": job_id}
        
        time.sleep(15)
    
    return {"status": "timeout", "job_id": job_id}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Rough cost estimate per model."""
    rates = {
        "claude-opus-4-6": (15.0, 75.0),      # per 1M tokens (in, out)
        "gpt-5": (10.0, 30.0),                  # estimated
        "gemini-2.5-pro": (1.25, 10.0),         # per 1M tokens
    }
    rate = rates.get(model, (10.0, 30.0))
    return (input_tokens * rate[0] + output_tokens * rate[1]) / 1_000_000


# ── Pipeline Nodes ──────────────────────────────────────────────

def research_node(state: PipelineState) -> dict:
    """Phase 0.5: Visual research + moodboard."""
    print(f"[RESEARCH] Starting visual research for: {state['name']}")
    span = tracer.start_span("research", input={"name": state["name"], "brief": state["brief"][:500]})
    
    run_dir = RUNS_DIR / state["name"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "moodboard").mkdir(exist_ok=True)
    (run_dir / "concepts").mkdir(exist_ok=True)
    (run_dir / "builds").mkdir(exist_ok=True)
    (run_dir / "reviews").mkdir(exist_ok=True)
    
    # Load knowledge layer for research quality
    rubric = load_reference("art-direction-rubric.md", max_chars=4000)
    patterns = load_reference("creative-patterns.md", max_chars=3000)
    past_learnings = get_relevant_learnings(state["brief"])
    
    # Build diverse search queries from the brief
    task = f"""You are a design researcher using Refero (a curated library of 130,000+ real product screens).
You have access to Refero MCP tools. USE THEM — do not use browser screenshots.

## YOUR TOOLS
- `mcp_refero_refero_search_screens` — semantic search for UI screens (query + platform "web" or "ios")
- `mcp_refero_refero_get_screen_content` — get the actual image of a screen (returns base64)
- `mcp_refero_refero_get_similar_screens` — find similar designs from a good match
- `mcp_refero_refero_search_flows` — search multi-step user flows

## RESEARCH PROCESS (follow exactly)

### Step 1: Run 4-5 diverse search queries
Read the brief and create 4-5 search queries that cover DIFFERENT visual approaches:
- Query 1: Direct match (e.g., "ranked list share card", "leaderboard social sharing")
- Query 2: Visual technique match (e.g., "3D product showcase card", "isometric data display")
- Query 3: Adjacent pattern (e.g., "stats comparison card dark mode", "sports ranking dashboard")
- Query 4: Layout/composition match (e.g., "vertical list with visual hierarchy", "numbered ranking with images")
- Query 5: Experimental/creative (e.g., "creative data visualization card", "animated infographic")

For each query, use `mcp_refero_refero_search_screens` with platform="web".

### Step 2: Select top 8-10 screens
From ALL search results, pick the 8-10 most relevant and visually diverse screens.
Selection criteria:
- DIVERSE visual languages (don't pick 5 screens that look the same)
- HIGH relevance to the brief's product/format
- INTERESTING techniques (unusual layouts, creative typography, strong visual hierarchy)

### Step 3: Get actual images for top 5
Use `mcp_refero_refero_get_screen_content` to download the base64 image for your top 5 picks.
Save each image to: {run_dir}/moodboard/ as PNG files.

### Step 4: Deep analysis
For each of the 8-10 selected screens, extract:
- **Exact hex colors** (Refero provides these in the metadata)
- **Font families** (Refero provides these)
- **Layout structure** (describe the composition, grid, spacing)
- **UX patterns** (Refero provides pattern labels)
- **Notable techniques** (what makes this design interesting? CSS hints?)
- **Relevance score** (1-10) for how useful this is as a reference

### Step 5: Write VISUAL-RESEARCH.md
Save a structured research document to: {run_dir}/VISUAL-RESEARCH.md

Format for each reference:
```
## Reference N: [Site Name] — [Description]
- **Refero UUID**: [uuid]
- **Relevance**: [score]/10
- **Colors**: [hex values from Refero metadata]
- **Fonts**: [font names from Refero metadata]
- **UX Patterns**: [pattern labels]
- **Layout**: [description of structure]
- **Key Technique**: [what makes this interesting]
- **Inspiration Value**: [how a designer should use this reference]
```

## BANNED REFERENCES (from past run retros)
- NO vintage boxing/fight card posters
- NO Spotify Wrapped or music streaming recaps
- NO cream/newsprint backgrounds with red accents

## DIVERSITY MANDATE
Your final selection must include references from AT LEAST 3 of these visual approaches:
1. 3D/spatial (depth, layers, perspective)
2. Data visualization (charts, treemaps, radial layouts)
3. Kinetic/motion (animation, transformation)
4. Editorial/magazine (grids, asymmetry, bold type)
5. Experimental (generative, creative coding, unusual interactions)

## Brief
{state['brief']}

## Quality Rubric
{rubric if rubric else "(No rubric available — use your best judgment)"}

## Known Creative Patterns
{patterns if patterns else "(No pattern library available)"}

{('## Past Run Learnings (avoid repeating mistakes)' + chr(10) + past_learnings) if past_learnings else ''}
"""
    
    result = run_hermes(f"{state['name']}-research", task, max_time=900)
    
    research_path = run_dir / "VISUAL-RESEARCH.md"
    research_content = research_path.read_text() if research_path.exists() else "Research incomplete"
    
    moodboard_files = list((run_dir / "moodboard").glob("*"))
    
    out = {
        "research": {"content": research_content, "status": result["status"]},
        "moodboard": [str(f) for f in moodboard_files],
        "phase": "research_complete",
        "cost_usd": state.get("cost_usd", 0) + 0.50,  # estimated
    }
    tracer.end_span(span, output={"status": result["status"], "moodboard_count": len(moodboard_files)})
    return out


def fan_out_designers(state: PipelineState) -> list:
    """Fan out to 3 parallel designer nodes with different model families."""
    
    designer_configs = [
        {
            "designer_id": 0,
            "model": "claude-opus",
            "era": "Your concept must use 3D/SPATIAL techniques as its primary visual language. Think: CSS 3D transforms, isometric perspective, parallax depth layers, perspective grids, stacked planes in Z-space. The card should feel like it has PHYSICAL DEPTH — objects at different distances from the viewer. Do NOT make a flat 2D layout. Do NOT default to vintage/retro aesthetics.",
            "anti_patterns": "No flat layouts, no vintage/retro/newspaper aesthetics, no fight card metaphors, no boxing references, no cream/newsprint backgrounds, no gradients, no glassmorphism, no backdrop-blur, no rounded corners > 4px.",
        },
        {
            "designer_id": 1,
            "model": "gpt-5",
            "era": "Your concept must use DATA VISUALIZATION or INFOGRAPHIC techniques as its primary visual language. Think: charts, graphs, radial layouts, node networks, treemaps, bubble plots, connected-dot rankings, heat maps. The ranked list should be presented through a visual system that ENCODES the ranking in the visual structure itself — not just numbered text. Do NOT make a standard list layout. Do NOT default to vintage/retro aesthetics.",
            "anti_patterns": "No numbered lists, no vintage/retro/newspaper aesthetics, no fight card metaphors, no boxing references, no cream/newsprint backgrounds, no centered layouts, no hero sections, no card grids, no Tailwind defaults.",
        },
        {
            "designer_id": 2,
            "model": "gemini",
            "era": "Your concept must use KINETIC TYPOGRAPHY and MOTION as its primary visual language. Think: text that moves, morphs, splits, glitches, or transforms. Rank transitions through typographic animation. Characters that rearrange. Words that shatter and reform. The card should feel ALIVE and MOVING even in a static screenshot. Do NOT make a static list. Do NOT default to vintage/retro aesthetics.",
            "anti_patterns": "No static layouts, no vintage/retro/newspaper aesthetics, no fight card metaphors, no boxing references, no cream/newsprint backgrounds, no soft shadows, no floating elements, no pastel palettes, no generic sans-serif, no template energy.",
        },
    ]
    
    return [Send("designer", {**state, "designer_config": c}) for c in designer_configs]


def designer_node(state: dict) -> dict:
    """Phase 1: Write approach doc. One instance per parallel designer."""
    config = state["designer_config"]
    designer_id = config["designer_id"]
    run_dir = RUNS_DIR / state["name"]
    
    print(f"[DESIGNER {designer_id}] Starting with model: {config['model']}")
    span = tracer.start_span(f"designer-{designer_id}", input={"model": config["model"], "era": config.get("era")})
    
    # Load persistent persona
    persona_path = WORKSPACE / "skills/creative-technologist/personas/DESIGNER.md"
    persona = persona_path.read_text() if persona_path.exists() else ""
    
    # Load knowledge layer — technique menu and output format
    tactics = load_reference("enhancement-tactics.md", max_chars=5000)
    techniques_index = load_reference("advanced-techniques.md", max_chars=4000)
    contract_template = load_reference("design-contract-template.md")
    past_learnings = get_relevant_learnings(state["brief"])
    
    task = f"""{persona}

## Available Techniques (pick from these — they are PROVEN to work in HTML/CSS/JS)
{tactics if tactics else "(No technique menu available — use your expertise)"}

## Advanced Techniques Reference (technique index — reference by name in your contract)
{techniques_index if techniques_index else ""}

{('## Past Run Learnings (what worked and what failed in previous runs)' + chr(10) + past_learnings) if past_learnings else ''}

## CRITICAL TASTE CALIBRATION (from creative director, 2026-05-01)
The creative director rated 15 past builds: **0 great, 6 acceptable, 9 bad.**
The #1 failure mode is "AI slop" — clean, polished, soulless output. Every build that looked like an AI made it was rated BAD.
The acceptable builds all had: creative ambition, novel visual techniques, 3D/depth/layering, and felt like a human designer made them.

**Your job is NOT to make something clean. Your job is to make something INTERESTING.**
**Your concept must match the PRODUCT described in the brief.** The moodboard is for visual style only — if the brief says "ranked list of sneakers", don't design a music streaming recap. Read the brief's sample data (if any) and design around THAT content.
- Push for novel techniques: 3D CSS, WebGL, SVG filters, generative patterns, creative compositing
- A rough but creative concept >>> a polished but generic one
- Think like an experimental graphic designer, not an AI assistant
- The output should look like a junior designer's ambitious portfolio piece, NOT an AI prototype
- If your concept could be described as "dark card with light text and some animation" — START OVER, it's not ambitious enough

## Your Task
Write an approach doc for a creative concept based on this brief. Your approach doc has TWO parts:
1. **Creative Narrative** — your concept, references, and rationale (for humans to read)
2. **Build Contract** — the EXACT specs the builder must follow (for the builder to execute)

The Build Contract is the most important part. It will be extracted and given to the builder as hard requirements. If a value isn't in the Build Contract, the builder won't use it.

## Brief
{state['brief']}

## Visual Research (study before writing)
{state.get('research', {}).get('content', 'No research available')}

## Your Constraints
- Era/Reference Direction: {config['era']}
- Anti-Patterns (DO NOT USE): {config['anti_patterns']}
- You MUST do independent web research for 3-5 additional references

## Independent Research (REQUIRED)
Search the web for 3-5 references that inspire YOUR unique direction.
These should be specific to your concept, not generic design sites.

## REQUIRED OUTPUT FORMAT

Your approach doc MUST end with a section called `## BUILD CONTRACT` that contains ONLY concrete, grep-able specs. No prose, no "feel like", no "inspired by". Just values.

Example format (adapt to your concept):

```
## BUILD CONTRACT

### REQUIRED FONTS (builder will be rejected if these are missing)
- PRIMARY: `font-family: 'Oswald', sans-serif` — weights: 400, 600, 700
- SECONDARY: `font-family: 'Playfair Display', serif` — weights: 700
- MONO: `font-family: 'Roboto Mono', monospace` — weights: 400
- Google Fonts URL: `https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Playfair+Display:wght@700&family=Roboto+Mono:wght@400&display=swap`

### FORBIDDEN FONTS (builder will be rejected if these appear)
- Bebas Neue, IBM Plex Mono, Inter, system-ui defaults

### REQUIRED COLORS (builder will be rejected if these are missing)
- BACKGROUND: `#0F1419`
- PRIMARY_TEXT: `#F5F0E8`
- ACCENT: `#E63B2E`
- SECONDARY: `#1B2A4A`
- Must NOT contain: #F5F0E1, #C4382A, #1A1A1E (these are other concepts' palettes)

### LAYOUT
- Card: 1080×1920px
- #1 item: font-size 64px, occupies top 40% of card
- #1 rank number: font-size 220px, Oswald 700
- #2-3: font-size 28px
- #4-10: font-size 18px
- [specific layout structure with px values]

### REQUIRED CSS TECHNIQUES (builder must implement ALL)
- Risograph overprint: `mix-blend-mode: multiply` on accent layer
- Ink press animation: translateY reveal with 0.6s cubic-bezier(0.16, 1, 0.3, 1)
- Newsprint grain: SVG feTurbulence filter, baseFrequency="0.65"
- [each technique on its own line with the CSS property/value]

### ANIMATION SEQUENCE
- Items #10-4: 200ms each, stagger 100ms
- Items #3-2: 600ms each, hold 200ms between
- Item #1: 1800ms reveal, scale(1.02) → scale(1)
```

The Build Contract must be specific enough that a script can grep your HTML and verify compliance. "Warm tones" is NOT specific enough. `#E63B2E` IS specific enough.

## Output
Save your approach doc to: {run_dir}/concepts/designer-{designer_id}-APPROACH.md

STOP after writing the approach doc. Do NOT build anything.
"""
    
    result = run_hermes(f"{state['name']}-designer-{designer_id}", task, max_time=600)
    
    approach_path = run_dir / f"concepts/designer-{designer_id}-APPROACH.md"
    
    # Retry file read — Hermes may still be writing when .done signal fires
    approach = "Approach not generated"
    for attempt in range(3):
        if approach_path.exists() and approach_path.stat().st_size > 100:
            approach = approach_path.read_text()
            break
        time.sleep(2)
    
    if approach == "Approach not generated":
        print(f"  ⚠️  Designer {designer_id}: approach doc missing or empty!")
    elif "## BUILD CONTRACT" not in approach:
        print(f"  ⚠️  Designer {designer_id}: approach doc missing BUILD CONTRACT section!")
    else:
        print(f"  ✅ Designer {designer_id}: approach doc with BUILD CONTRACT ({len(approach)} bytes)")
    
    tracer.end_span(span, output={
        "status": result["status"],
        "has_contract": "## BUILD CONTRACT" in approach,
        "length": len(approach),
    })
    return {
        "approaches": [{
            "designer_id": designer_id,
            "model": config["model"],
            "content": approach,
            "path": str(approach_path),
            "status": result["status"],
        }],
    }


def approach_gate_node(state: PipelineState) -> dict:
    """Phase 2: Check approaches for convergence, ambition, compliance.
    Uses MECHANICAL extraction for convergence + LLM for ambition check."""
    print(f"[GATE] Reviewing {len(state['approaches'])} approaches")
    span = tracer.start_span("approach_gate", input={"approach_count": len(state["approaches"])})
    
    # ── Step 1: Mechanical convergence detection (no LLM) ──
    contracts = []
    for a in state["approaches"]:
        contract = extract_build_contract(a["content"])
        fonts = extract_fonts_from_contract(contract)
        colors = extract_colors_from_contract(contract)
        contracts.append({
            "designer_id": a["designer_id"],
            "fonts": fonts,
            "colors": colors,
            "contract": contract,
        })
    
    convergence_issues = []
    for i, c1 in enumerate(contracts):
        for j, c2 in enumerate(contracts):
            if i >= j:
                continue
            # Check font overlap
            shared_fonts = set(f.lower() for f in c1["fonts"]["required"]) & set(f.lower() for f in c2["fonts"]["required"])
            if shared_fonts:
                convergence_issues.append(
                    f"Designer {c1['designer_id']} and Designer {c2['designer_id']} share fonts: {shared_fonts}"
                )
            # Check color overlap (primary colors only, first 3)
            c1_colors = set(c.lower() for c in c1["colors"]["required"][:3])
            c2_colors = set(c.lower() for c in c2["colors"]["required"][:3])
            shared_colors = c1_colors & c2_colors
            if shared_colors:
                convergence_issues.append(
                    f"Designer {c1['designer_id']} and Designer {c2['designer_id']} share primary colors: {shared_colors}"
                )
    
    if convergence_issues:
        print(f"  ⚠️  MECHANICAL CONVERGENCE DETECTED:")
        for issue in convergence_issues:
            print(f"     ✗ {issue}")
    else:
        print(f"  ✅ No font/color convergence detected across {len(contracts)} concepts")
    
    # Check for missing build contracts
    missing_contracts = [a["designer_id"] for a in state["approaches"] if not extract_build_contract(a["content"])]
    if missing_contracts:
        print(f"  ⚠️  Missing BUILD CONTRACT in designers: {missing_contracts}")
    
    # ── Step 2: LLM ambition check (still useful for subjective quality) ──
    approaches_text = "\n\n---\n\n".join([
        f"## Designer {a['designer_id']} ({a['model']})\n{a['content'][:2000]}"
        for a in state["approaches"]
    ])
    
    msg = anthropic_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": f"""You are a creative director reviewing 3 approach docs. You must be HARSH and CRITICAL.

## CHECK 1: CONCEPTUAL CONVERGENCE (most important!)
Mechanical font/color checks already passed. But concepts can converge at a HIGHER level.
Compare the core METAPHOR and VISUAL LANGUAGE of each approach:
- Do 2+ approaches use the same conceptual metaphor? (e.g., all doing "vintage fight card", all doing "newspaper", all doing "receipt")
- Do 2+ approaches use the same visual era/aesthetic? (e.g., all doing 1920s vintage, all doing brutalist, all doing vaporwave)
- Do 2+ approaches have essentially the same layout structure? (e.g., all big-item-top + stacked-list-bottom)
If ANY two concepts share a metaphor, aesthetic era, OR layout structure — that's convergence. Flag it.

## CHECK 2: AMBITION
Would a creative director at a top agency be excited by this? Or would they say "I've seen this before"?
- If ANY approach could be described as "standard ranked list with nice typography" — it's not ambitious enough
- Novel visual techniques (3D CSS, SVG filters, generative art, creative compositing) are good signals
- Playing it safe is a FAIL

## CHECK 3: COMPLIANCE
Does each approach address the brief's actual product and content?

## Approaches
{approaches_text}

## Output (JSON):
{{
  "conceptual_convergence": ["designer X and Y both use the same [metaphor/era/layout]: ..."],
  "ambition_flags": ["designer X is too safe because..."],
  "compliance_issues": ["designer X doesn't address..."],
  "all_pass": true/false,
  "notes": "..."
}}

IMPORTANT: If 2+ concepts share the same metaphor/aesthetic, all_pass MUST be false.
"""}]
    )
    
    gate_text = msg.content[0].text
    if msg.usage:
        track_cost("claude-opus-4-6", msg.usage.input_tokens, msg.usage.output_tokens, "approach_gate")
    
    llm_passed = "all_pass\": true" in gate_text.lower() or "\"all_pass\": true" in gate_text
    has_conceptual_convergence = "conceptual_convergence\": [\"" in gate_text or "conceptual_convergence\": [\n" in gate_text
    
    if has_conceptual_convergence and not llm_passed:
        print(f"  ⚠️  CONCEPTUAL CONVERGENCE DETECTED BY LLM — gate FAILED")
        print(f"     LLM reasoning: {gate_text[:500]}")
    
    out = {
        "gate_result": {
            "raw": gate_text,
            "passed": llm_passed and not has_conceptual_convergence,
            "convergence_issues": convergence_issues,
            "missing_contracts": missing_contracts,
        },
        "phase": "gate_complete",
    }
    tracer.end_span(span, output={
        "passed": out["gate_result"]["passed"],
        "convergence_issues": len(convergence_issues),
        "missing_contracts": len(missing_contracts),
    })
    return out


def fan_out_builders(state: PipelineState) -> list:
    """Fan out to 3 parallel builder nodes, each with a different model assignment."""
    model_assignments = ["claude-opus", "gpt-4.1", "gemini-2.5-pro"]
    builders = []
    for i in range(len(state["approaches"])):
        model = model_assignments[i % len(model_assignments)]
        builders.append(Send("builder", {**state, "build_index": i, "builder_model": model}))
    return builders


def build_direct_api(model: str, prompt: str, output_path: Path, run_name: str) -> dict:
    """Build HTML via direct API call (no Hermes). Returns status dict.
    Used for GPT and Gemini builders that don't need tool use."""
    
    print(f"    [direct-api] Calling {model}...")
    
    try:
        if model.startswith("gpt"):
            response = openai_client.chat.completions.create(
                model=model,
                max_tokens=32000,
                messages=[{"role": "user", "content": prompt + "\n\nRespond with ONLY the complete HTML file content. No markdown fences, no explanation. Start with <!DOCTYPE html>."}],
            )
            html = response.choices[0].message.content
            if response.usage:
                track_cost(model, response.usage.prompt_tokens, response.usage.completion_tokens, "builder")
                
        elif model.startswith("gemini"):
            import google.generativeai as genai
            genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))
            gmodel = genai.GenerativeModel("gemini-2.5-pro")
            response = gmodel.generate_content(
                prompt + "\n\nRespond with ONLY the complete HTML file content. No markdown fences, no explanation. Start with <!DOCTYPE html>.",
                generation_config=genai.types.GenerationConfig(max_output_tokens=32000),
            )
            html = response.text
            # Gemini usage tracking
            if hasattr(response, 'usage_metadata'):
                track_cost("gemini-2.5-pro",
                    getattr(response.usage_metadata, 'prompt_token_count', 0),
                    getattr(response.usage_metadata, 'candidates_token_count', 0),
                    "builder")
        else:
            # Default to Hermes
            return {"status": "unsupported_model"}
        
        # Clean response — strip markdown fences if present
        html = html.strip()
        if html.startswith("```html"):
            html = html[7:]
        if html.startswith("```"):
            html = html[3:]
        if html.endswith("```"):
            html = html[:-3]
        html = html.strip()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
        print(f"    [direct-api] Wrote {len(html)} bytes to {output_path.name}")
        return {"status": "done"}
        
    except Exception as e:
        print(f"    [direct-api] Error: {type(e).__name__}: {e}")
        return {"status": "failed", "error": str(e)}


def builder_node(state: dict) -> dict:
    """Phase 3: Build HTML prototype from approach doc."""
    idx = state["build_index"]
    approach = state["approaches"][idx]
    run_dir = RUNS_DIR / state["name"]
    builder_model = state.get("builder_model", "claude-opus")
    
    print(f"[BUILDER {idx}] Building from designer {approach['designer_id']} approach (model: {builder_model})")
    span = tracer.start_span(f"builder-{idx}", input={"model": builder_model, "designer": approach["designer_id"]})
    
    # Load persistent builder persona
    persona_path = WORKSPACE / "skills/creative-technologist/personas/BUILDER.md"
    persona = persona_path.read_text() if persona_path.exists() else ""
    
    concept_name = f"concept-{idx}"
    
    # Extract Build Contract from approach doc
    approach_content = approach['content']
    build_contract = extract_build_contract(approach_content)
    if build_contract:
        creative_narrative = approach_content.split("## BUILD CONTRACT", 1)[0] if "## BUILD CONTRACT" in approach_content else approach_content
    else:
        creative_narrative = approach_content
        build_contract = "(No build contract found — follow the approach doc's specs exactly)"
    
    # Load proven code recipes for implementation guidance
    recipes = load_reference("recipes.md", max_chars=6000)
    
    # 4.5C: Identify moodboard images for builder reference
    moodboard_dir = run_dir / "moodboard"
    moodboard_images = sorted(moodboard_dir.glob("*.png"))[:3] if moodboard_dir.exists() else []
    moodboard_ref = ""
    if moodboard_images:
        moodboard_ref = f"""
## REFERENCE IMAGES (study these — your build should feel like it belongs in this visual family)
The following moodboard images are at: {moodboard_dir}
"""
        for img in moodboard_images:
            moodboard_ref += f"- {img.name}\n"
        moodboard_ref += "\nOpen and study these images before building. They represent the quality bar and aesthetic direction.\n"
    
    task = f"""{persona}

## CRITICAL TASTE CALIBRATION
The creative director rated 15 past builds: **0 great, 6 acceptable, 9 bad.**
Every build that looked like "AI slop" — clean, generic, soulless — was rated BAD.
The acceptable ones had: creative ambition, novel visual techniques, 3D/depth, and felt HUMAN-made.

**YOUR BUILD MUST NOT LOOK LIKE AN AI MADE IT.**
- Add imperfections: slightly off-grid elements, organic textures, hand-crafted feeling
- Push visual techniques hard: SVG filters, blend modes, 3D transforms, generative noise
- Depth and layering matter more than cleanliness
- Think experimental graphic design poster, not tech product card
- If you zoom out and it looks like "dark card + light text + fade-in animation" — you've failed

## CONTENT FIDELITY (non-negotiable)
Your build must contain the ACTUAL content described in the brief — not content inspired by the moodboard.
If the brief says "sneakers" and the moodboard shows music apps, you build SNEAKERS.
The moodboard is for VISUAL STYLE inspiration only. The brief defines WHAT you're building.
If the brief includes sample data, use it exactly. Do not invent different content.

## Your Task
Build a complete, working HTML prototype. You have two inputs:
1. A Creative Narrative (context for understanding the concept)
2. A BUILD CONTRACT (hard requirements you MUST follow exactly)

The Build Contract contains grep-able specs. After you write your HTML, I will programmatically verify:
- Your file contains the REQUIRED FONTS (exact font-family values)
- Your file contains the REQUIRED COLORS (exact hex values)
- Your file does NOT contain any FORBIDDEN fonts or colors
- Each REQUIRED CSS TECHNIQUE is present

If verification fails, your build is rejected and you must redo it.

---

## CREATIVE NARRATIVE (read for context)
{creative_narrative[:3000]}

---

## CODE RECIPES (proven implementations — adapt these, don't reinvent)
{recipes if recipes else "(No recipes available)"}
{moodboard_ref}

---

## ⚠️ BUILD CONTRACT (HARD REQUIREMENTS — YOUR BUILD WILL BE GREP-CHECKED)
{build_contract}

---

## Build Rules
1. IMPLEMENT every technique in the Build Contract — visible on screen, not just in code
2. Use ONLY the fonts listed in REQUIRED FONTS. Using any font from FORBIDDEN FONTS = automatic rejection.
3. Use ONLY the colors listed in REQUIRED COLORS as your primary palette. Using colors from "Must NOT contain" = automatic rejection.
4. Default state = completed static card (all items visible)
5. Add Play/Reset controls
6. Single HTML file, all CSS/JS inline
7. Must render at 1080×1920

## Self-Check Before Saving
Before writing the file, verify:
- [ ] Does my `<link>` tag load the exact Google Fonts URL from the Build Contract?
- [ ] Does my CSS use the exact font-family values from REQUIRED FONTS?
- [ ] Do my primary colors match REQUIRED COLORS hex values?
- [ ] Is each REQUIRED CSS TECHNIQUE implemented and visible?
- [ ] Have I accidentally used any FORBIDDEN font or color?

## Output
Save to: {run_dir}/builds/{concept_name}.html
"""
    
    build_path = run_dir / f"builds/{concept_name}.html"
    
    # Route to appropriate builder based on model
    if builder_model.startswith("gpt") or builder_model.startswith("gemini"):
        # Direct API — model generates HTML directly
        result = build_direct_api(builder_model, task, build_path, state["name"])
    else:
        # Hermes (Claude) — agent with tool use
        result = run_hermes(f"{state['name']}-builder-{idx}", task, max_time=1800, max_turns=50)
    
    # Spec compliance check (grep-based, no LLM cost)
    compliance = {"pass": True, "failures": [], "warnings": [], "checks": 0}
    if build_path.exists() and build_contract and build_contract != "(No build contract found — follow the approach doc's specs exactly)":
        compliance = check_spec_compliance(build_path, build_contract)
        
        if compliance["pass"]:
            print(f"  ✅ Builder {idx}: spec compliance PASSED ({compliance['checks']} checks)")
        else:
            print(f"  ❌ Builder {idx}: spec compliance FAILED")
            for f in compliance["failures"]:
                print(f"     ✗ {f}")
            
            # Retry once with specific error
            if compliance["failures"]:
                fix_prompt = f"""Your build at {build_path} FAILED spec compliance checks:

"""
                for f in compliance["failures"]:
                    fix_prompt += f"- {f}\n"
                fix_prompt += f"""
Fix ONLY these issues in the existing file. Do not rewrite the entire file.
The Build Contract requires:
{build_contract[:3000]}

Save the fixed file to: {build_path}
"""
                print(f"  🔄 Builder {idx}: retrying with compliance fix...")
                fix_result = run_hermes(f"{state['name']}-builder-{idx}-fix", fix_prompt, max_time=600, max_turns=20)
                
                # Re-check compliance
                if build_path.exists():
                    compliance = check_spec_compliance(build_path, build_contract)
                    if compliance["pass"]:
                        print(f"  ✅ Builder {idx}: compliance PASSED on retry")
                    else:
                        print(f"  ⚠️  Builder {idx}: still failing compliance after retry — advancing anyway")
                        for f in compliance["failures"]:
                            print(f"     ✗ {f}")
        
        if compliance["warnings"]:
            for w in compliance["warnings"]:
                print(f"     ⚡ {w}")
    
    # ── 4.5B: Build → Screenshot → Self-Review (one round) ──
    if build_path.exists():
        print(f"  📸 Builder {idx}: screenshotting for self-review...")
        try:
            from playwright.sync_api import sync_playwright
            review_screenshot = run_dir / f"builds/{concept_name}-review.png"
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1080, "height": 1920})
                page.goto(f"file://{build_path.resolve()}", wait_until="networkidle")
                page.wait_for_timeout(2000)
                page.screenshot(path=str(review_screenshot), full_page=False)
                page.close()
                browser.close()
            
            if review_screenshot.exists():
                import base64
                with open(review_screenshot, "rb") as img_f:
                    screenshot_b64 = base64.standard_b64encode(img_f.read()).decode("utf-8")
                
                # Send screenshot to builder for self-review via vision API
                print(f"  🔍 Builder {idx}: self-reviewing against approach doc...")
                review_response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    max_tokens=1000,
                    messages=[
                        {"role": "system", "content": "You are reviewing a build's screenshot against its design spec. List ONLY concrete visual issues — things that are wrong, missing, or broken. Be specific: 'the #1 item text is cut off at the right edge' not 'typography could be improved'. If it looks good, say LOOKS_GOOD."},
                        {"role": "user", "content": [
                            {"type": "text", "text": f"Compare this screenshot to the BUILD CONTRACT below. List visual issues.\n\n## BUILD CONTRACT\n{build_contract[:2000]}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
                        ]}
                    ],
                )
                review_text = review_response.choices[0].message.content
                if review_response.usage:
                    track_cost("gpt-4o", review_response.usage.prompt_tokens, review_response.usage.completion_tokens, "self_review")
                
                if "LOOKS_GOOD" not in review_text.upper():
                    print(f"  🔄 Builder {idx}: visual issues found, sending fix...")
                    # Save review for debugging
                    (run_dir / f"reviews/self-review-{idx}.md").write_text(review_text)
                    
                    fix_prompt = f"""Your build at {build_path} has visual issues identified from a screenshot review:

{review_text}

Fix these visual issues in the existing file. Do not change fonts, colors, or layout structure — only fix rendering bugs and visual problems.

Save the fixed file to: {build_path}
"""
                    run_hermes(f"{state['name']}-builder-{idx}-visual-fix", fix_prompt, max_time=600, max_turns=20)
                    print(f"  ✅ Builder {idx}: visual fix applied")
                else:
                    print(f"  ✅ Builder {idx}: self-review passed — LOOKS_GOOD")
        except Exception as e:
            print(f"  ⚠️  Builder {idx}: self-review skipped ({type(e).__name__}: {e})")
    
    build_out = {
        "builds": [{
            "index": idx,
            "designer_id": approach["designer_id"],
            "model": approach["model"],
            "path": str(build_path),
            "exists": build_path.exists(),
            "size": build_path.stat().st_size if build_path.exists() else 0,
            "status": result["status"],
            "compliance": compliance,
        }],
    }
    tracer.end_span(span, output={
        "status": result["status"],
        "exists": build_path.exists(),
        "size": build_path.stat().st_size if build_path.exists() else 0,
        "compliance": compliance,
    })
    return build_out


def screenshot_builds(builds: list, run_name: str) -> list:
    """Screenshot each build at 1080x1920 using Playwright."""
    from playwright.sync_api import sync_playwright
    
    screenshots = []
    screenshot_dir = RUNS_DIR / run_name / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for b in builds:
            build_path = Path(b["path"])
            if not build_path.exists():
                screenshots.append(None)
                continue
            
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            page.goto(f"file://{build_path.resolve()}", wait_until="networkidle")
            page.wait_for_timeout(2000)  # Let fonts + animations settle
            
            screenshot_path = screenshot_dir / f"concept-{b['index']}.png"
            page.screenshot(path=str(screenshot_path), full_page=False)
            screenshots.append(str(screenshot_path))
            
            print(f"  📸 Screenshot: {screenshot_path.name}")
            page.close()
        
        browser.close()
    
    return screenshots


def encode_image(path: str) -> str:
    """Read image and return base64 string."""
    import base64
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def pairwise_judge_node(state: PipelineState) -> dict:
    """Phase 5: Vision-based bidirectional pairwise tournament."""
    print(f"[JUDGE] Running vision-based pairwise tournament on {len(state['builds'])} builds")
    span = tracer.start_span("judge", input={"build_count": len(state["builds"])})
    
    builds = state["builds"]
    if len(builds) < 2:
        return {"ranking": builds, "phase": "judge_complete"}
    
    # Screenshot all builds
    print(f"[JUDGE] Screenshotting {len(builds)} builds at 1080×1920...")
    screenshots = screenshot_builds(builds, state["name"])
    
    # Load reviewer persona
    persona_path = WORKSPACE / "skills/creative-technologist/personas/REVIEWER.md"
    persona = persona_path.read_text() if persona_path.exists() else ""
    
    # Use OpenAI as judge (cross-model — builders are Claude/Hermes)
    judge_model = "gpt-4o"
    
    judge_system = f"""{persona}

You are a harsh design critic evaluating two prototypes side by side.
You're looking at SCREENSHOTS of the actual rendered output, not code.

## CALIBRATED TASTE (from creative director rating 15 builds — 0 great, 6 acceptable, 9 bad)
The #1 failure mode is "AI slop" — clean, polished, soulless output that looks like an AI made it.
Builds that looked like AI = BAD. Builds with creative ambition + novel techniques = acceptable.
A rough but interesting build >>> a clean but generic one.

Judge on these criteria (in order of importance — creative ambition is 40%):
1. CREATIVE AMBITION (40%) — Does this feel like a human designer made it? Is the concept novel? Are there interesting visual techniques (3D, SVG filters, generative patterns, creative compositing)? Or is it just "dark card + light text"?
2. AI SLOP CHECK (20%) — Does it look like AI generated it? Signs: perfect spacing, generic gradients, glassmorphism, centered-everything, uniform padding, shadcn energy, dark card with white text and nothing else. If yes, it FAILS regardless of other qualities.
3. VISUAL DEPTH (15%) — Texture, grain, layering, material quality. Flat colored divs = bad. Depth and dimension = good.
4. TYPOGRAPHY (10%) — Is the hierarchy intentional? Fonts loaded? Real rhythm vs just size differences?
5. HIERARCHY (10%) — Can you instantly tell what's #1? Legibility of lower items?
6. TECHNICAL EXECUTION (5%) — Renders correctly, animation works. This is LEAST important — a broken but ambitious build beats a working but boring one.

IMPORTANT: Start skeptical. Most AI prototypes are mediocre. A "winner" of a mediocre pair is still mediocre.
If both are bad, say so — but you MUST still pick the less-bad one.

YOU MUST CHOOSE. Respond with EXACTLY one line first: PREFER_A or PREFER_B
TIE is NOT allowed unless the artifacts are pixel-identical. There is always a less-bad option.
Then explain in 3-5 sentences WHY, citing specific visual elements you see in the screenshots."""

    pairs = list(itertools.combinations(range(len(builds)), 2))
    wins = {i: 0 for i in range(len(builds))}
    results = []
    
    for i, j in pairs:
        print(f"  ⚖️  Comparing concept {i} vs concept {j}...")
        
        img_i = encode_image(screenshots[i]) if screenshots[i] else None
        img_j = encode_image(screenshots[j]) if screenshots[j] else None
        
        if not img_i or not img_j:
            results.append({"pair": [i, j], "agreed": False, "winner": None, "error": "missing screenshot"})
            continue
        
        # Forward direction: A=i, B=j
        fwd_messages = [
            {"role": "user", "content": [
                {"type": "text", "text": f"Compare these two share card prototypes.\n\nBrief context: {state['brief'][:500]}\n\nImage 1 is ARTIFACT A. Image 2 is ARTIFACT B."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_i}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_j}"}},
            ]}
        ]
        
        fwd_response = openai_client.chat.completions.create(
            model=judge_model,
            max_tokens=600,
            messages=[{"role": "system", "content": judge_system}] + fwd_messages,
        )
        fwd_text = fwd_response.choices[0].message.content
        if fwd_response.usage:
            track_cost(judge_model, fwd_response.usage.prompt_tokens, fwd_response.usage.completion_tokens, "judge")
        
        # Reverse direction: A=j, B=i (swap images)
        rev_messages = [
            {"role": "user", "content": [
                {"type": "text", "text": f"Compare these two share card prototypes.\n\nBrief context: {state['brief'][:500]}\n\nImage 1 is ARTIFACT A. Image 2 is ARTIFACT B."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_j}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_i}"}},
            ]}
        ]
        
        rev_response = openai_client.chat.completions.create(
            model=judge_model,
            max_tokens=600,
            messages=[{"role": "system", "content": judge_system}] + rev_messages,
        )
        rev_text = rev_response.choices[0].message.content
        if rev_response.usage:
            track_cost(judge_model, rev_response.usage.prompt_tokens, rev_response.usage.completion_tokens, "judge")
        
        # Parse preferences
        fwd_first_line = fwd_text.strip().split("\n")[0].upper()
        rev_first_line = rev_text.strip().split("\n")[0].upper()
        
        fwd_winner = "A" if "PREFER_A" in fwd_first_line else ("B" if "PREFER_B" in fwd_first_line else "TIE")
        rev_winner = "A" if "PREFER_A" in rev_first_line else ("B" if "PREFER_B" in rev_first_line else "TIE")
        
        # Bidirectional agreement:
        # Forward A=i wins AND Reverse B=i wins → i is genuinely preferred
        agreed = False
        winner = None
        if fwd_winner == "A" and rev_winner == "B":
            wins[i] += 1
            agreed = True
            winner = i
        elif fwd_winner == "B" and rev_winner == "A":
            wins[j] += 1
            agreed = True
            winner = j
        
        results.append({
            "pair": [i, j],
            "forward": fwd_winner,
            "reverse": rev_winner,
            "agreed": agreed,
            "winner": winner,
            "fwd_reasoning": fwd_text,
            "rev_reasoning": rev_text,
        })
        
        status = "✓ agreed" if agreed else "⚠ disagreed"
        winner_label = f"→ concept {winner}" if winner is not None else "→ tie"
        print(f"    {status} {winner_label}")
    
    # Rank by wins
    ranking = sorted(wins.items(), key=lambda x: -x[1])
    ranked_builds = [{"rank": rank + 1, "build_index": idx, "wins": w, **builds[idx]} 
                     for rank, (idx, w) in enumerate(ranking)]
    
    # Save detailed results
    results_path = RUNS_DIR / state["name"] / "reviews" / "pairwise-results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    import json as json_mod
    results_path.write_text(json_mod.dumps({"pairs": results, "ranking": [{"rank": r["rank"], "index": r["build_index"], "wins": r["wins"]} for r in ranked_builds]}, indent=2))
    
    print(f"\n[JUDGE] Final ranking:")
    for r in ranked_builds:
        print(f"  #{r['rank']} — Concept {r['build_index']} ({r.get('model', '?')}) — {r['wins']} wins")
    
    judge_out = {
        "pairwise_results": results,
        "ranking": ranked_builds,
        "phase": "judge_complete",
    }
    tracer.end_span(span, output={
        "ranking": [{"rank": r["rank"], "build": r["build_index"], "wins": r["wins"]} for r in ranked_builds],
        "comparison_count": len(results),
    })
    # Score each build in Langfuse
    for r in ranked_builds:
        tracer.score(f"build-{r['build_index']}-rank", float(len(ranked_builds) - r["rank"] + 1),
                     comment=f"Rank #{r['rank']} with {r['wins']} wins")
    return judge_out


def human_gate_node(state: PipelineState) -> Command:
    """Phase 7: Pause for human taste review."""
    print(f"\n{'='*60}")
    print(f"HUMAN GATE — Iteration {state.get('iteration', 0)}")
    print(f"{'='*60}")
    
    # Show ranking
    for r in state.get("ranking", []):
        print(f"  #{r['rank']} — Concept {r['build_index']} ({r.get('model', '?')}) — {r['wins']} wins")
    
    # Show pairwise details
    for pr in state.get("pairwise_results", []):
        agreed = "✓ agreed" if pr["agreed"] else "⚠ disagreed"
        winner = f"→ concept {pr['winner']}" if pr["winner"] is not None else "→ tie"
        print(f"  {pr['pair'][0]} vs {pr['pair'][1]}: {agreed} {winner}")
    
    print(f"\nBuilds at: {RUNS_DIR / state['name'] / 'builds'}")
    print(f"{'='*60}\n")
    
    # Save cost report before pausing
    save_cost_report(state["name"])
    
    # This pauses the pipeline until resumed
    decision = interrupt({
        "action": "taste_gate",
        "ranking": state.get("ranking", []),
        "pairwise_results": state.get("pairwise_results", []),
        "builds_dir": str(RUNS_DIR / state["name"] / "builds"),
        "iteration": state.get("iteration", 0),
        "message": "Review the builds. Respond with: approve / iterate / reject",
    })
    
    human_decision = decision.get("decision", "reject") if isinstance(decision, dict) else str(decision)
    human_feedback = decision.get("feedback", "") if isinstance(decision, dict) else ""
    
    # Langfuse: score the run with human decision
    decision_scores = {"approve": 1.0, "iterate": 0.5, "reject": 0.0}
    tracer.score("human_decision", decision_scores.get(human_decision, 0.0),
                 comment=f"{human_decision}: {human_feedback[:200]}")
    
    # Record verdict to technique registry (cross-run learning)
    record_verdict(
        run_name=state["name"],
        decision=human_decision,
        feedback=human_feedback,
        ranking=state.get("ranking", []),
        builds=state.get("builds", []),
        approaches=state.get("approaches", []),
    )
    
    if human_decision == "approve":
        return Command(goto="deploy", update={
            "human_decision": "approve",
            "human_feedback": human_feedback,
            "phase": "approved",
        })
    elif human_decision == "iterate":
        return Command(goto="iterate", update={
            "human_decision": "iterate",
            "human_feedback": human_feedback,
        })
    else:
        return Command(goto=END, update={
            "human_decision": "reject",
            "human_feedback": human_feedback,
            "phase": "rejected",
        })


def iterate_node(state: PipelineState) -> dict:
    """Phase 6: Increment iteration counter and loop back."""
    iteration = state.get("iteration", 0) + 1
    print(f"[ITERATE] Starting iteration {iteration} (max {MAX_ITERATIONS})")
    
    if iteration >= MAX_ITERATIONS:
        print(f"[ITERATE] Max iterations reached. Proceeding to human gate.")
    
    return {
        "iteration": iteration,
        "phase": f"iteration_{iteration}",
        "approaches": [],  # Reset for new fan-out
        "builds": [],
    }


def deploy_node(state: PipelineState) -> dict:
    """Phase 8: Deploy winning build."""
    print(f"[DEPLOY] Deploying winning build")
    
    run_dir = RUNS_DIR / state["name"]
    
    # Deploy via here-now
    result = subprocess.run(
        ["bash", str(WORKSPACE / ".." / ".agents/skills/here-now/scripts/publish.sh"),
         str(run_dir / "builds"), "--client", "openclaw"],
        capture_output=True, text=True, timeout=60
    )
    
    return {
        "phase": "deployed",
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── Build the Graph ────────────────────────────────────────────

def build_graph():
    graph = StateGraph(PipelineState)
    
    # Add nodes
    graph.add_node("research", research_node)
    graph.add_node("designer", designer_node)
    graph.add_node("approach_gate", approach_gate_node)
    graph.add_node("builder", builder_node)
    graph.add_node("judge", pairwise_judge_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("iterate", iterate_node)
    graph.add_node("deploy", deploy_node)
    
    # Edges
    graph.add_edge(START, "research")
    graph.add_conditional_edges("research", fan_out_designers, ["designer"])
    graph.add_edge("designer", "approach_gate")
    graph.add_conditional_edges("approach_gate", fan_out_builders, ["builder"])
    graph.add_edge("builder", "judge")
    graph.add_edge("judge", "human_gate")
    # human_gate uses Command() to route to deploy/iterate/END
    graph.add_conditional_edges("iterate", fan_out_designers, ["designer"])
    graph.add_edge("deploy", END)
    
    return graph


# ── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Creative Pipeline V3")
    sub = parser.add_subparsers(dest="command")
    
    # Run
    run_parser = sub.add_parser("run", help="Start a new pipeline run")
    run_parser.add_argument("--brief", required=True, help="Path to brief markdown file")
    run_parser.add_argument("--name", required=True, help="Run name (used as thread_id)")
    
    # Resume
    resume_parser = sub.add_parser("resume", help="Resume a paused pipeline")
    resume_parser.add_argument("--thread", required=True, help="Thread ID to resume")
    resume_parser.add_argument("--decision", choices=["approve", "iterate", "reject"], required=True)
    resume_parser.add_argument("--feedback", default="", help="Optional feedback for iteration")
    
    # Status
    status_parser = sub.add_parser("status", help="Check pipeline status")
    status_parser.add_argument("--thread", required=True, help="Thread ID to check")
    
    args = parser.parse_args()
    
    # Build graph with checkpointer
    graph = build_graph()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    app = graph.compile(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": args.thread if hasattr(args, 'thread') else args.name}}
    
    if args.command == "run":
        brief_path = Path(args.brief)
        if not brief_path.exists():
            print(f"Brief not found: {brief_path}")
            sys.exit(1)
        
        brief = brief_path.read_text()
        
        initial_state = {
            "name": args.name,
            "brief": brief,
            "research": None,
            "moodboard": [],
            "approaches": [],
            "builds": [],
            "gate_result": None,
            "pairwise_results": [],
            "ranking": [],
            "human_decision": None,
            "human_feedback": None,
            "iteration": 0,
            "phase": "starting",
            "cost_usd": 0.0,
            "phase_costs": {},
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "completed_at": None,
        }
        
        config["configurable"]["thread_id"] = args.name
        
        # Initialize Langfuse tracing
        tracer.init()
        tracer.start_run(args.name, brief)
        
        print(f"\n🚀 Starting pipeline: {args.name}")
        print(f"Brief: {brief_path}")
        print(f"State stored in: {DB_PATH}\n")
        
        for event in app.stream(initial_state, config, stream_mode="updates"):
            if isinstance(event, dict):
                for node, update in event.items():
                    if isinstance(update, dict):
                        phase = update.get("phase", "")
                        if phase:
                            print(f"  → {node}: {phase}")
                    else:
                        print(f"  → {node}: {update}")
        
        tracer.end_run(status="paused_or_completed", metadata={"run_name": args.name})
        print(f"\n✅ Pipeline paused or completed. Resume with:")
        print(f"  python pipeline.py resume --thread {args.name} --decision approve")
    
    elif args.command == "resume":
        tracer.init()
        tracer.start_run(f"{args.thread}-resume", metadata={"decision": args.decision, "feedback": args.feedback})
        print(f"\n🔄 Resuming pipeline: {args.thread}")
        print(f"Decision: {args.decision}")
        
        resume_value = {"decision": args.decision, "feedback": args.feedback}
        
        for event in app.stream(Command(resume=resume_value), config, stream_mode="updates"):
            for node, update in event.items():
                phase = update.get("phase", "")
                if phase:
                    print(f"  → {node}: {phase}")
    
    elif args.command == "status":
        state = app.get_state(config)
        if state and state.values:
            s = state.values
            print(f"\n📊 Pipeline: {args.thread}")
            print(f"Phase: {s.get('phase', 'unknown')}")
            print(f"Iteration: {s.get('iteration', 0)}")
            print(f"Approaches: {len(s.get('approaches', []))}")
            print(f"Builds: {len(s.get('builds', []))}")
            print(f"Cost: ${s.get('cost_usd', 0):.2f}")
            print(f"Human decision: {s.get('human_decision', 'pending')}")
            
            if state.next:
                print(f"Waiting at: {state.next}")
        else:
            print(f"No state found for thread: {args.thread}")
    
    conn.close()


if __name__ == "__main__":
    main()
