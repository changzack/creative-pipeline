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
    
    run_dir = RUNS_DIR / state["name"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "moodboard").mkdir(exist_ok=True)
    (run_dir / "concepts").mkdir(exist_ok=True)
    (run_dir / "builds").mkdir(exist_ok=True)
    (run_dir / "reviews").mkdir(exist_ok=True)
    
    task = f"""You are a design researcher. Read the creative brief below and conduct visual research.

## Brief
{state['brief']}

## Process
1. Search for 5-8 reference sites/designs relevant to this brief
2. Screenshot each at 1440px viewport
3. Analyze: color palettes, typography, layout, texture, mood
4. Find 3-5 real product images relevant to the brief topic

## Output
Save your research to: {run_dir}/VISUAL-RESEARCH.md
Save reference images to: {run_dir}/moodboard/
"""
    
    result = run_hermes(f"{state['name']}-research", task, max_time=900)
    
    research_path = run_dir / "VISUAL-RESEARCH.md"
    research_content = research_path.read_text() if research_path.exists() else "Research incomplete"
    
    moodboard_files = list((run_dir / "moodboard").glob("*"))
    
    return {
        "research": {"content": research_content, "status": result["status"]},
        "moodboard": [str(f) for f in moodboard_files],
        "phase": "research_complete",
        "cost_usd": state.get("cost_usd", 0) + 0.50,  # estimated
    }


def fan_out_designers(state: PipelineState) -> list:
    """Fan out to 3 parallel designer nodes with different model families."""
    
    designer_configs = [
        {
            "designer_id": 0,
            "model": "claude-opus",
            "era": "Choose your own era/reference. Do NOT default to modern web aesthetics.",
            "anti_patterns": "No gradients, no glassmorphism, no backdrop-blur, no rounded corners > 4px, no shadcn defaults.",
        },
        {
            "designer_id": 1,
            "model": "gpt-5",
            "era": "Choose your own era/reference. Do NOT default to modern web aesthetics.",
            "anti_patterns": "No centered layouts, no hero sections, no card grids, no Tailwind defaults, no AI-beige.",
        },
        {
            "designer_id": 2,
            "model": "gemini",
            "era": "Choose your own era/reference. Do NOT default to modern web aesthetics.",
            "anti_patterns": "No soft shadows, no floating elements, no pastel palettes, no generic sans-serif, no template energy.",
        },
    ]
    
    return [Send("designer", {**state, "designer_config": c}) for c in designer_configs]


def designer_node(state: dict) -> dict:
    """Phase 1: Write approach doc. One instance per parallel designer."""
    config = state["designer_config"]
    designer_id = config["designer_id"]
    run_dir = RUNS_DIR / state["name"]
    
    print(f"[DESIGNER {designer_id}] Starting with model: {config['model']}")
    
    # Load persistent persona
    persona_path = WORKSPACE / "skills/creative-technologist/personas/DESIGNER.md"
    persona = persona_path.read_text() if persona_path.exists() else ""
    
    task = f"""{persona}

## Your Task
Write an approach doc for a creative concept based on this brief.

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

## Output
Save your approach doc to: {run_dir}/concepts/designer-{designer_id}-APPROACH.md

STOP after writing the approach doc. Do NOT build anything.
"""
    
    result = run_hermes(f"{state['name']}-designer-{designer_id}", task, max_time=600)
    
    approach_path = run_dir / f"concepts/designer-{designer_id}-APPROACH.md"
    approach = approach_path.read_text() if approach_path.exists() else "Approach not generated"
    
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
    """Phase 2: Check approaches for convergence, ambition, compliance."""
    print(f"[GATE] Reviewing {len(state['approaches'])} approaches")
    
    approaches_text = "\n\n---\n\n".join([
        f"## Designer {a['designer_id']} ({a['model']})\n{a['content'][:2000]}"
        for a in state["approaches"]
    ])
    
    msg = anthropic_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": f"""You are reviewing 3 creative approach docs for convergence and quality.

## Approaches
{approaches_text}

## Check for:
1. CONVERGENCE: Do any two approaches share the same palette family, primary technique, layout pattern, or interaction model? If yes, which ones and on what axes?
2. AMBITION: Does any approach feel conservative or generic? Would a creative director be excited or bored?
3. COMPLIANCE: Does each approach address the brief's requirements?

## Output (JSON):
{{
  "convergence_found": true/false,
  "convergence_details": "...",
  "ambition_flags": ["designer X is too safe because..."],
  "all_pass": true/false,
  "notes": "..."
}}
"""}]
    )
    
    gate_text = msg.content[0].text
    
    return {
        "gate_result": {"raw": gate_text, "passed": "all_pass\": true" in gate_text.lower() or "\"all_pass\": true" in gate_text},
        "phase": "gate_complete",
    }


def fan_out_builders(state: PipelineState) -> list:
    """Fan out to 3 parallel builder nodes."""
    return [Send("builder", {**state, "build_index": i}) for i in range(len(state["approaches"]))]


def builder_node(state: dict) -> dict:
    """Phase 3: Build HTML prototype from approach doc."""
    idx = state["build_index"]
    approach = state["approaches"][idx]
    run_dir = RUNS_DIR / state["name"]
    
    print(f"[BUILDER {idx}] Building from designer {approach['designer_id']} approach")
    
    # Load persistent builder persona
    persona_path = WORKSPACE / "skills/creative-technologist/personas/BUILDER.md"
    persona = persona_path.read_text() if persona_path.exists() else ""
    
    concept_name = f"concept-{idx}"
    
    task = f"""{persona}

## Your Task
Build a complete, working HTML prototype from this approach doc.

## Approach Doc (YOUR CONTRACT)
{approach['content']}

## Key Rules
1. IMPLEMENT every technique described in the approach doc — visible on screen, not just in code
2. Default state = completed static card (all items visible)
3. Add Play/Reset controls
4. Use real product images from the moodboard directory if available
5. All fonts via Google Fonts CDN
6. Single HTML file, all CSS/JS inline
7. Must render at 1080×1920

## Output
Save to: {run_dir}/builds/{concept_name}.html
"""
    
    result = run_hermes(f"{state['name']}-builder-{idx}", task, max_time=1800, max_turns=50)
    
    build_path = run_dir / f"builds/{concept_name}.html"
    
    return {
        "builds": [{
            "index": idx,
            "designer_id": approach["designer_id"],
            "model": approach["model"],
            "path": str(build_path),
            "exists": build_path.exists(),
            "size": build_path.stat().st_size if build_path.exists() else 0,
            "status": result["status"],
        }],
    }


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

You are a harsh design critic evaluating two share card prototypes side by side.
You're looking at SCREENSHOTS of the actual rendered output, not code.

Judge on these criteria (in order of importance):
1. FIRST IMPRESSION — Does it look like a premium artifact or a generic template? Would you stop scrolling?
2. VISUAL DISTINCTION — Does it have a clear visual identity/metaphor, or could it be any dark-mode card?
3. TYPOGRAPHY — Is the hierarchy intentional? Are fonts loaded and working? Sizes/weights create rhythm?
4. TEXTURE & DEPTH — Is there grain, material quality, layering? Or is it flat colored divs?
5. HIERARCHY — Can you instantly tell what's #1? Are #8-10 still legible?
6. ANTI-PATTERNS — Flag any: generic gradients, glassmorphism, backdrop-blur, rounded-2xl on everything, 
   AI-beige/purple palette, centered-everything, uniform spacing, shadcn-default energy

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
    
    return {
        "pairwise_results": results,
        "ranking": ranked_builds,
        "phase": "judge_complete",
    }


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
        
        print(f"\n✅ Pipeline paused or completed. Resume with:")
        print(f"  python pipeline.py resume --thread {args.name} --decision approve")
    
    elif args.command == "resume":
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
