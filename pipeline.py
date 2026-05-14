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


def _merge_dict(left: Optional[dict], right: Optional[dict]) -> dict:
    """LangGraph reducer for Dict-valued state fields.

    Empty-right (``{}``) signals a reset (matches the existing list-reset
    convention used for ``approaches``/``builds``). Otherwise we shallow-merge
    right into left, with right overriding on key conflicts.
    """
    if right is None:
        return left or {}
    if not right:
        return {}
    merged = dict(left or {})
    merged.update(right)
    return merged


def _last_wins(left, right):
    """LangGraph reducer for scalar fields written by parallel fan-outs.

    All parallel Sends in a given fan-out write the SAME value (e.g. all
    builders write builder_mode="initial" together, or all write "qa_fix"
    together), so any of the writes is equivalent. We just take the latest
    non-None value, falling back to left.
    """
    if right is None:
        return left
    return right

from anthropic import Anthropic
from openai import OpenAI
# import google.generativeai as genai  # will use via langchain

# Observability
from langfuse_tracing import tracer, prompts, estimate_tokens

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

# Playability mode (legacy; folded into QA loop in qa-judge-loops refactor).
# Retained because `_builder_playability_run` still uses these helpers for the
# qa_fix loop body. See wiki/builds/qa-judge-loops-2026-05-13.md.
MAX_PLAYABILITY_ITERATIONS = 3       # Legacy default (now superseded by MAX_QA_ITERATIONS)
PLAYABILITY_MIN_ROUNDS = 5           # Default "reach round N/N" completion threshold
PLAYABILITY_CODE_MAX_CHARS = 90000   # Max code context shipped to patch model per attempt
PLAYABILITY_PATCH_MIN_BYTES = 500    # Reject patches shorter than this (likely garbage)

# ── QA Loop + Judge Polish Loop (2026-05-13 refactor) ──────────
# Both loops are per-concept, per-original-model. See plan:
# ~/.openclaw/workspace/memory/plans/qa-judge-loop-refactor.md
MAX_QA_ITERATIONS = 20               # Max qa_fix patches per concept before giving up
MAX_JUDGE_ITERATIONS = 20            # Max judge_polish patches per concept before giving up

# Hybrid threshold the judge loop checks per build.
# - weighted_total must clear `weighted_total`
# - every individual dimension must clear `min_dimension`
# - if `ai_slop_hardcap` is True, ai_slop_flagged auto-fails
JUDGE_DEFAULT_THRESHOLD = {
    "weighted_total": 7.0,
    "min_dimension": 5.0,
    "ai_slop_hardcap": True,
}

# ── Pinned Model Versions ──────────────────────────────────────
# Use dated snapshots where available to prevent silent behavior changes.
# Update these explicitly after testing new versions.
# Last updated: 2026-05-13 — frontier-only policy (Zack: "highest models on everything")
#
# Per-model max OUTPUT token ceilings (sync API). "Push harder" tier — max what
# each provider supports natively. Updating these alone bumps every call site.
MAX_OUTPUT_TOKENS = {
    "claude-opus-4-7": 128000,    # Opus 4.7 supports 128K output (sync); 300K via batch
    "claude-opus-4-6": 64000,     # legacy; older Opus caps lower
    "gpt-5.5":         100000,    # GPT-5.5 max output
    "gpt-5.4":         32000,     # legacy
    "gemini-3.1-pro":  65536,     # Gemini 3.1 Pro hard ceiling
    "gemini-3.1-pro-preview": 65536,
    "gemini-pro-latest": 65536,   # Google's auto-latest alias
}

# Smaller budgets for short structured replies (gates, judges) where we want
# the model to be concise, not to write a novel.
MAX_OUTPUT_TOKENS_VERDICT = {
    "claude-opus-4-7": 16000,
    "gpt-5.5":         16000,
    "gemini-3.1-pro":  16000,
    "gemini-pro-latest": 16000,
}

def max_output_for(model_id: str, kind: str = "generation") -> int:
    """Return the appropriate max-output budget for a given resolved model id.

    kind="generation" — large outputs (builders, asset gen, fix scripts)
    kind="verdict"    — short structured replies (approach gate, judge)
    """
    table = MAX_OUTPUT_TOKENS_VERDICT if kind == "verdict" else MAX_OUTPUT_TOKENS
    if model_id in table:
        return table[model_id]
    # Lenient fallback by family prefix
    for key, val in table.items():
        if model_id.startswith(key.split("-")[0]):
            return val
    # Safe default
    return 32000 if kind == "generation" else 8000

PINNED_MODELS = {
    # Builders / generators — frontier tier
    "claude-opus": "claude-opus-4-7",              # Anthropic: latest Opus (Apr 2026)
    "claude-opus-4-6": "claude-opus-4-7",          # legacy alias → redirected to 4-7
    "gpt-5": "gpt-5.5",                           # OpenAI: GPT-5.5 (Apr 24 2026 GA)
    "gpt-5.4": "gpt-5.5",                          # legacy alias → redirected to 5.5
    "gpt-5.5": "gpt-5.5",
    # Gemini aliases all resolve to Google's `gemini-pro-latest` — their
    # server-side alias that auto-tracks the latest Pro. Zero pipeline changes
    # when Google ships a new Pro version. Verified 2026-05-13: resolves to
    # gemini-3.1-pro-preview today, will auto-upgrade going forward.
    "gemini": "gemini-pro-latest",                         # bare alias
    "gemini-pro-latest": "gemini-pro-latest",              # canonical (self)
    "gemini-3.1-pro-preview": "gemini-pro-latest",         # explicit → latest
    "gemini-3.1-pro": "gemini-pro-latest",                 # legacy alias → latest
    # Judge (vision pairwise) — frontier vision-capable
    "gpt-4o": "gpt-5.5",                          # legacy alias → upgraded to GPT-5.5 (vision-native)
    "gpt-5.5-vision": "gpt-5.5",
    "judge": "gpt-5.5",                            # canonical judge alias
    # Self-review / vision (legacy aliases → frontier)
    "gpt-4o-vision": "gpt-5.5",
}

def resolve_model(alias: str) -> str:
    """Resolve a model alias to its pinned version."""
    return PINNED_MODELS.get(alias, alias)

# Cost per 1M tokens (approximate, 2026 pricing)
COST_PER_1M = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-5.4": {"input": 2.50, "output": 10.0},
    "gpt-5.5": {"input": 3.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-3.1-pro-preview": {"input": 2.0, "output": 12.0},
    "gemini-3.1-pro": {"input": 2.0, "output": 12.0},
    "gemini-pro-latest": {"input": 2.0, "output": 12.0},
}

# Run-level cost accumulator
_run_costs = {"total_usd": 0.0, "by_phase": {}, "calls": []}

def track_cost(model: str, input_tokens: int, output_tokens: int, phase: str = "unknown", override_cost: Optional[float] = None):
    """Track cost of an API call. Use override_cost for flat-rate services (e.g., fal.ai)."""
    if override_cost is not None:
        cost = override_cost
    else:
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
        # Soft circuit-break: the loops check `_cost_circuit_broken()` at the
        # top of each iteration and stop spending. We log loudly but don't
        # raise — raising would unwind the whole graph instead of letting the
        # pipeline gracefully degrade to human_gate with what it has.
        if not _run_costs.get("_breaker_logged"):
            print(f"  ⛔ BUDGET EXCEEDED: ${_run_costs['total_usd']:.2f} > ${MAX_COST_USD:.2f} — cost circuit broken. Loops will stop spending.")
            _run_costs["_breaker_logged"] = True
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
    brief_path: Optional[str]  # Bug B: path-on-disk of the brief, used by
                               # get_wiki_context() to load <brief>.LEARNINGS.md
                               # and by wiki_ingest to write per-brief learnings
    
    # Phase outputs
    research: Optional[dict]
    moodboard: list[str]  # paths to reference images
    diversification_axes: Optional[list]  # Bug A: per-run designer-axis configs
                                          # (replaces hardcoded share-card-shaped eras)
    
    # Fan-in from parallel agents (Annotated[list, add] = auto-concatenate)
    approaches: Annotated[list[dict], add]
    builds: Annotated[list[dict], add]
    
    # Gate results
    gate_result: Optional[dict]
    
    # QA — legacy field, retained for back-compat with old runs / eval app readers.
    # The new QA loop writes per-concept reports into `qa_reports_by_concept`.
    qa_reports: list[dict]

    # Playability mode (legacy; folded into QA loop)
    playability_signals: Annotated[Dict[int, dict], _merge_dict]    # per-build final completion telemetry
    playability_iterations: Annotated[Dict[int, int], _merge_dict]  # per-build iteration count used
    playability_status: Annotated[Dict[int, str], _merge_dict]      # "complete" | "partial" | "skipped" | "failed"
    playability_patches: Annotated[Dict[int, list], _merge_dict]    # per-build patch metadata (per-iteration entries)
    playability_max_iter: Optional[int]                              # override for MAX_PLAYABILITY_ITERATIONS

    # QA Loop (replaces qa_station + playability_loop)
    qa_iterations: Annotated[Dict[int, int], _merge_dict]            # per concept
    qa_status: Annotated[Dict[int, str], _merge_dict]                # "pass" | "failed_max" | "cost_circuit" | "pending"
    qa_reports_by_concept: Annotated[Dict[int, dict], _merge_dict]   # latest QA report per concept
    qa_max_iter: Optional[int]                                       # override for MAX_QA_ITERATIONS

    # Judge Polish Loop (replaces pairwise_judge_node's win-counting role)
    judge_scores: Annotated[Dict[int, dict], _merge_dict]            # latest per-build score JSON
    judge_polish_iterations: Annotated[Dict[int, int], _merge_dict]  # per concept
    judge_status: Annotated[Dict[int, str], _merge_dict]             # "above_bar" | "below_bar" | "failed_max" | "cost_circuit"
    judge_max_iter: Optional[int]                                    # override for MAX_JUDGE_ITERATIONS
    judge_threshold: Optional[dict]                                  # override for JUDGE_DEFAULT_THRESHOLD

    # Cost circuit breaker — set when MAX_COST_USD is exceeded mid-loop.
    cost_circuit_broken: Optional[bool]

    # Builder dispatch mode — controls which path builder_node runs. Set per-Send
    # by fan-out functions. New modes: "qa_fix", "judge_polish".
    # Legacy mode "playability" still routed for back-compat (synonym for qa_fix).
    # Annotated with _last_wins reducer so parallel builder Sends merge cleanly.
    builder_mode: Annotated[Optional[str], _last_wins]               # "initial" | "qa_fix" | "judge_polish" | "playability" (legacy)

    # Evaluation
    pairwise_results: list[dict]
    ranking: list[dict]
    
    # Human gate
    human_decision: Optional[str]  # "approve" | "iterate" | "reject"
    human_feedback: Optional[str]
    
    # Loop control
    iteration: int
    phase: str
    
    # Assets
    asset_manifest: Optional[dict]  # designer_id -> list of generated assets
    asset_base_url: Optional[str]   # here.now base URL for hosted assets
    
    # Design system constraint
    design_system: Optional[str]    # loaded design system tokens (markdown)
    
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


# ── Wiki Ingest (Compounding Knowledge Base) ────────────────────

WIKI_DIR = WORKSPACE / "pipeline/wiki"

def wiki_ingest(state: dict, decision: str, feedback: str):
    """Ingest run results into the pipeline wiki after human verdict.
    
    Updates: run summary, technique evidence, aesthetic patterns, model performance, log.
    Non-fatal: pipeline continues even if wiki write fails.
    """
    import re
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    
    run_name = state["name"]
    ranking = state.get("ranking", [])
    approaches = state.get("approaches", [])
    builds = state.get("builds", [])
    cost = state.get("cost_usd", 0)
    iteration = state.get("iteration", 0)
    design_system = "SMPLX" if state.get("design_system") else "none"
    
    # 1. Write run summary page
    runs_dir = WIKI_DIR / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    
    summary_lines = [f"# Run: {run_name}", ""]
    summary_lines.append(f"- **Date:** {time.strftime('%Y-%m-%d %H:%M')}")
    summary_lines.append(f"- **Verdict:** {decision}")
    summary_lines.append(f"- **Iteration:** {iteration}")
    summary_lines.append(f"- **Cost:** ${cost:.2f}")
    summary_lines.append(f"- **Design System:** {design_system}")
    summary_lines.append("")
    
    if feedback:
        summary_lines.append(f"## Human Feedback")
        summary_lines.append(f"> {feedback}")
        summary_lines.append("")
    
    summary_lines.append("## Concepts")
    for r in ranking:
        model = r.get("model", "unknown")
        wins = r.get("wins", 0)
        size = r.get("size", 0)
        rank = r.get("rank", "?")
        idx = r.get("index", r.get("build_index", "?"))
        compliance = r.get("compliance", {})
        warnings = compliance.get("warnings", [])
        
        summary_lines.append(f"### #{rank} — Concept {idx} ({model})")
        summary_lines.append(f"- Wins: {wins}, Size: {size//1024}KB")
        if warnings:
            summary_lines.append(f"- Warnings: {', '.join(w[:60] for w in warnings[:3])}")
        summary_lines.append("")
    
    # Pairwise results
    pairwise = state.get("pairwise_results", [])
    if pairwise:
        summary_lines.append("## Pairwise Results")
        for pr in pairwise:
            agreed = "agreed" if pr.get("agreed") else "disagreed"
            winner = f"concept {pr['winner']}" if pr.get("winner") is not None else "tie"
            summary_lines.append(f"- {pr['pair'][0]} vs {pr['pair'][1]}: {agreed} → {winner}")
        summary_lines.append("")
    
    run_summary_path = runs_dir / f"{run_name}.md"
    run_summary_path.write_text("\n".join(summary_lines))
    
    # 2. Update log
    log_path = WIKI_DIR / "log.md"
    log_entry = f"\n## [{time.strftime('%Y-%m-%d')}] ingest | {run_name}\n"
    log_entry += f"Verdict: {decision}. Cost: ${cost:.2f}. "
    if ranking:
        winner = ranking[0]
        log_entry += f"Winner: Concept {winner.get('build_index', '?')} ({winner.get('model', '?')}, {winner.get('wins', 0)} wins). "
    if feedback:
        log_entry += f'Feedback: "{feedback[:100]}"'
    log_entry += "\n"
    
    if log_path.exists():
        with open(log_path, "a") as f:
            f.write(log_entry)
    
    # 3. Update model pages with performance data
    for r in ranking:
        model = r.get("model", "unknown")
        model_name = {
            "claude-opus": "claude-opus",
            "gpt-5": "gpt-5.4",
            "gpt-5.4": "gpt-5.4",
            "gemini": "gemini-pro-latest",
            "gemini-3.1-pro-preview": "gemini-pro-latest",
            "gemini-pro-latest": "gemini-pro-latest",
        }.get(model, model)
        
        model_page = WIKI_DIR / f"models/{model_name}.md"
        if model_page.exists():
            content = model_page.read_text()
            # Append to performance history table
            rank = r.get("rank", "?")
            wins = r.get("wins", 0)
            idx = r.get("index", r.get("build_index", "?"))
            new_row = f"| {run_name} | Builder {idx} | #{rank} ({wins} wins) | {decision} | auto-ingested |"
            
            if "## Performance History" in content:
                content = content.rstrip() + f"\n{new_row}\n"
                model_page.write_text(content)
    
    # 4. Update anti-patterns if rejected
    if decision == "reject" and feedback:
        ap_path = WIKI_DIR / "aesthetics/anti-patterns.md"
        if ap_path.exists():
            content = ap_path.read_text()
            new_entry = f"\n### {run_name} (auto-ingested)\n"
            new_entry += f"- **Evidence:** Run {run_name}, verdict: reject\n"
            new_entry += f"- **CD feedback:** > \"{feedback[:200]}\"\n"
            new_entry += f"- **Date:** {time.strftime('%Y-%m-%d')}\n"
            content = content.rstrip() + "\n" + new_entry
            ap_path.write_text(content)
    
    # 5. Update what-scores-well if approved
    if decision == "approve" and ranking:
        ws_path = WIKI_DIR / "aesthetics/what-scores-well.md"
        if ws_path.exists():
            content = ws_path.read_text()
            winner = ranking[0]
            new_entry = f"\n### {run_name} — Concept {winner.get('build_index', '?')} ({winner.get('model', '?')})\n"
            new_entry += f"- **Verdict:** approved\n"
            new_entry += f"- **Wins:** {winner.get('wins', 0)} pairwise wins\n"
            if feedback:
                new_entry += f"- **CD feedback:** > \"{feedback[:200]}\"\n"
            new_entry += f"- **Date:** {time.strftime('%Y-%m-%d')}\n"
            content = content.rstrip() + "\n" + new_entry
            ws_path.write_text(content)
    
    # 6. Update index with new run page
    index_path = WIKI_DIR / "index.md"
    if index_path.exists():
        content = index_path.read_text()
        if run_name not in content:
            # Add under Run Summaries section
            if "## Run Summaries" in content:
                content = content.replace(
                    "## Run Summaries",
                    f"## Run Summaries\n- [{run_name}](runs/{run_name}.md) — {decision}"
                )
            index_path.write_text(content)
    
    print(f"  📚 Wiki ingested: runs/{run_name}.md + log + model pages" + 
          (" + anti-patterns" if decision == "reject" else "") +
          (" + what-scores-well" if decision == "approve" else ""))


def _brief_path_from_state(state) -> Optional[Path]:
    """Return the brief file Path from pipeline state, or None.

    Bug B helper: ``state['brief_path']`` is stored as a string (LangGraph state
    is JSON-serialized through the SQLite checkpointer). Older runs may not
    have this key at all — callers must tolerate ``None``.
    """
    if not isinstance(state, dict):
        return None
    bp = state.get("brief_path")
    if not bp:
        return None
    try:
        return Path(bp)
    except Exception:
        return None


def get_wiki_context(brief_path=None, max_chars: int = 4000) -> str:
    """Load taste context for pipeline agents: global rules + brief-scoped learnings.

    Bug B fix (2026-05-13): the previous implementation auto-injected 8K chars
    of share-card-era lessons into every prompt, regardless of brief. That
    contaminated game/onboarding/etc briefs with irrelevant guidance. The new
    two-tier model:

      Tier 1 (always): ``wiki/global-taste-rules.md`` — ≤1.5K chars of
        universal taste rules (no AI slop, real craft, hierarchy, etc).
      Tier 2 (per-brief): ``<brief>.LEARNINGS.md`` next to the brief file.
        Accumulates feedback specific to THIS brief across runs. Capped at
        ~5K chars (oldest entries dropped by the writer).

    The old ``aesthetics/what-scores-well.md`` and ``anti-patterns.md`` files
    stay on disk as human-browseable reference material but are no longer
    auto-loaded into agent prompts.

    Args:
        brief_path: Path to the brief markdown file. The sibling
            ``<brief>.LEARNINGS.md`` (same stem, ``.LEARNINGS.md`` suffix) is
            loaded if it exists. Strings are tolerated for backwards-compat
            with callers that have not been migrated yet — in that case only
            the global tier is loaded.
        max_chars: Hard cap on returned context size. Default 4K (down from 8K).
    """
    context_parts = []

    # Tier 1: global taste rules (always loaded, small).
    global_rules = WIKI_DIR / "global-taste-rules.md"
    if global_rules.exists():
        context_parts.append(global_rules.read_text())

    # Tier 2: brief-scoped learnings. Only loaded when caller passed a real Path.
    if isinstance(brief_path, Path):
        learnings_path = brief_path.with_name(brief_path.stem + ".LEARNINGS.md")
        if learnings_path.exists():
            context_parts.append(
                f"## Brief-Specific Learnings (from prior runs of this brief)\n\n"
                + learnings_path.read_text()
            )

    combined = "\n\n---\n\n".join(context_parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n[... wiki context truncated ...]"
    return combined


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


# ── Asset Reference Validation (Bug C) ─────────────────────────
# After the builder writes HTML, scan for asset:// references and compare them
# against the designer's asset manifest. Missing refs are silent failures
# (broken images, ERR_UNKNOWN_URL_SCHEME). This validator surfaces them so the
# build-time post-process can either fall back to CSS placeholders or surface
# the mismatch in the QA report. See memory/plans/three-pipeline-bugs.md (Bug C).

_ASSET_URL_RE = None  # lazy-compiled regex (avoids unconditional `re` import here)

def _decode_asset_slug(slug: str) -> str:
    """Decode percent-encoded characters in an asset URL slug.

    Designers commission assets like ``shoe-photo-—-air-jordan`` (with literal
    em-dashes / quotes). When those appear in HTML attributes they often arrive
    percent-encoded (``%22`` for ``\"``, etc.). We compare on the decoded form.
    """
    try:
        from urllib.parse import unquote
        return unquote(slug)
    except Exception:
        return slug


def validate_asset_references(html_path: Path, manifest_path: Path) -> dict:
    """Cross-check ``asset://`` references in HTML against the asset manifest.

    Returns a dict with three lists:
      - ``matched``: refs that resolve to a manifest entry (post-processor will substitute)
      - ``missing``: refs the builder wrote that have NO matching manifest entry
                     (these become broken ``asset://`` URLs in the shipped HTML)
      - ``extra_in_manifest``: assets the designer commissioned but the builder
                               never referenced (wasted spend, not necessarily a bug)

    Slugs are compared after stripping common image extensions and
    percent-decoding so ``asset://shoe-photo-%E2%80%94-bred.jpg`` matches
    ``shoe-photo-—-bred`` in the manifest.
    """
    global _ASSET_URL_RE
    import re as _re
    if _ASSET_URL_RE is None:
        # Match asset://<slug>. Stop at quotes, whitespace, parens, or `)`.
        _ASSET_URL_RE = _re.compile(r"asset://([^\"'\s)<>]+)")

    result = {"matched": [], "missing": [], "extra_in_manifest": []}

    if not html_path.exists():
        return result
    html_text = html_path.read_text()

    raw_refs = _ASSET_URL_RE.findall(html_text)
    # Normalize: strip image extension + percent-decode.
    seen = set()
    normalized_refs = []
    for raw in raw_refs:
        slug = _decode_asset_slug(raw)
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            if slug.lower().endswith(ext):
                slug = slug[: -len(ext)]
                break
        if slug in seen:
            continue
        seen.add(slug)
        normalized_refs.append(slug)

    manifest_names = set()
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            for a in manifest:
                name = a.get("name")
                if name:
                    manifest_names.add(_decode_asset_slug(name))
        except Exception:
            pass

    for ref in normalized_refs:
        if ref in manifest_names:
            result["matched"].append(ref)
        else:
            result["missing"].append(ref)

    referenced = set(normalized_refs)
    for name in manifest_names:
        if name not in referenced:
            result["extra_in_manifest"].append(name)

    return result


def apply_missing_asset_fallbacks(html_path: Path, missing_refs: list[str]) -> int:
    """Replace unresolved ``asset://...`` URLs with inline data-URI placeholders.

    Generates a tiny SVG with the asset name overlayed on a striped background
    so the user can SEE what was missing rather than ship a broken image. Each
    missing ref is also logged for the QA report. Returns the number of
    substitutions performed.
    """
    if not missing_refs or not html_path.exists():
        return 0
    import re as _re
    from urllib.parse import quote
    import base64 as _b64

    html_text = html_path.read_text()
    total = 0
    for ref in missing_refs:
        label = ref.replace("-", " ")[:48]
        svg = (
            f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 600' "
            f"preserveAspectRatio='xMidYMid slice'>"
            f"<defs><pattern id='p' width='40' height='40' patternUnits='userSpaceOnUse'>"
            f"<rect width='40' height='40' fill='#1a1a1a'/>"
            f"<path d='M0 40L40 0' stroke='#ff3366' stroke-width='2' opacity='0.5'/>"
            f"</pattern></defs>"
            f"<rect width='800' height='600' fill='url(#p)'/>"
            f"<text x='400' y='290' fill='#ff3366' font-family='monospace' font-size='28' "
            f"text-anchor='middle' font-weight='bold'>MISSING ASSET</text>"
            f"<text x='400' y='330' fill='#ffffff' font-family='monospace' font-size='20' "
            f"text-anchor='middle'>{label}</text>"
            f"</svg>"
        )
        encoded = _b64.b64encode(svg.encode("utf-8")).decode("ascii")
        data_uri = f"data:image/svg+xml;base64,{encoded}"
        # Build a regex that matches asset://<ref> plus an optional extension,
        # with the slug optionally percent-encoded in the HTML.
        for variant in {ref, quote(ref), quote(ref, safe="")}:
            pat = _re.compile(rf"asset://{_re.escape(variant)}(?:\.(?:jpg|jpeg|png|webp|gif))?")
            new_text, n = pat.subn(data_uri, html_text)
            if n:
                total += n
                html_text = new_text
    if total:
        html_path.write_text(html_text)
    return total


# ── Context Budget ──────────────────────────────────────────────
# Model context windows (in tokens). We use ~4 chars/token as rough estimate.
# Reserve 35K tokens for output, use the rest for input.
MODEL_CONTEXT_WINDOWS = {
    "claude-opus": 200000,
    "gpt-5.4": 128000,
    "gpt-4.1": 128000,
    "gpt-4o": 128000,
    "gpt-5": 128000,
    "gemini-2.5-pro": 1000000,
    "gemini-3.1-pro-preview": 1000000,
}
OUTPUT_RESERVE_TOKENS = 35000  # reserve for generation
CHARS_PER_TOKEN = 4  # conservative estimate

def get_context_budget(model: str) -> int:
    """Return available input budget in characters for a given model."""
    window = MODEL_CONTEXT_WINDOWS.get(model, 128000)
    available_tokens = window - OUTPUT_RESERVE_TOKENS
    return available_tokens * CHARS_PER_TOKEN

def smart_truncate(text: str, budget: int, label: str = "") -> str:
    """Truncate text to budget chars. If truncated, log it."""
    if len(text) <= budget:
        return text
    truncated = text[:budget]
    # Try to break at a paragraph boundary
    last_para = truncated.rfind("\n\n")
    if last_para > budget * 0.8:
        truncated = truncated[:last_para]
    if label:
        print(f"  ⚠️  {label}: truncated from {len(text)} to {len(truncated)} chars ({len(truncated)*100//len(text)}%)")
    return truncated


# ── Knowledge Layer ─────────────────────────────────────────────
REFERENCES_DIR = WORKSPACE / "skills/creative-technologist/references"

def load_reference(filename: str, max_chars: Optional[int] = None, section: Optional[str] = None) -> str:
    """Load a reference doc from the skills directory.
    Optional max_chars for explicit budget control; defaults to full file."""
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


def check_design_system_compliance(html_path: Path, design_system: str) -> dict:
    """Check built HTML against a design system's token constraints.
    
    Parses the design system markdown to extract:
    - Allowed fonts (font-family values)
    - Allowed color palette (hex values)
    Then scans the HTML for violations.
    """
    import re
    if not html_path.exists():
        return {"pass": True, "violations": [], "checks": 0}
    
    html = html_path.read_text()
    violations = []
    checks = 0
    
    # Extract allowed fonts from design system
    allowed_fonts = set()
    for line in design_system.split("\n"):
        if "family/primary" in line.lower() or "font family" in line.lower():
            # Extract font name from backticks or after pipe
            fonts = re.findall(r'`([^`]+)`', line)
            for f in fonts:
                if f.lower() not in ("value", "token", "family/primary"):
                    allowed_fonts.add(f.lower())
    
    # Extract allowed colors from design system
    allowed_colors = set()
    for match in re.findall(r'#[0-9a-fA-F]{6}', design_system):
        allowed_colors.add(match.lower())
    # Always allow pure black/white and near variants
    allowed_colors.update({"#000000", "#ffffff"})
    
    # Check fonts used in HTML
    if allowed_fonts:
        fonts_in_html = set()
        for match in re.findall(r'font-family:\s*["\']?([^"\';\},]+)', html, re.IGNORECASE):
            for part in match.split(","):
                fname = part.strip().strip("'\"").lower()
                if fname and fname not in ("sans-serif", "serif", "monospace", "inherit", "system-ui"):
                    fonts_in_html.add(fname)
        
        checks += len(fonts_in_html)
        for font in fonts_in_html:
            if not any(af in font or font in af for af in allowed_fonts):
                violations.append(f"OFF-SYSTEM FONT: '{font}' (allowed: {', '.join(allowed_fonts)})")
    
    # Check colors used in HTML
    colors_in_html = set(c.lower() for c in re.findall(r'#[0-9a-fA-F]{6}', html))
    checks += len(colors_in_html)
    
    off_palette = []
    for color in colors_in_html:
        if color not in allowed_colors:
            # Check if it's "close enough" (within 20 per channel)
            try:
                r1, g1, b1 = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                close = False
                for ac in allowed_colors:
                    r2, g2, b2 = int(ac[1:3], 16), int(ac[3:5], 16), int(ac[5:7], 16)
                    if abs(r1-r2) <= 20 and abs(g1-g2) <= 20 and abs(b1-b2) <= 20:
                        close = True
                        break
                if not close:
                    off_palette.append(color)
            except ValueError:
                off_palette.append(color)
    
    if off_palette:
        violations.append(f"OFF-PALETTE COLORS ({len(off_palette)}): {', '.join(sorted(off_palette)[:8])}{'...' if len(off_palette) > 8 else ''}")
    
    return {
        "pass": len(violations) == 0,
        "violations": violations,
        "checks": checks,
        "fonts_found": list(fonts_in_html) if allowed_fonts else [],
        "off_palette_count": len(off_palette),
    }


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
        "claude-opus-4-7": (15.0, 75.0),
        "gpt-5": (3.0, 15.0),                  # GPT-5.5 pricing
        "gpt-5.4": (2.50, 10.0),
        "gpt-5.5": (3.0, 15.0),
        "gemini-2.5-pro": (1.25, 10.0),         # per 1M tokens
        "gemini-3.1-pro-preview": (2.0, 12.0),
        "gemini-3.1-pro": (2.0, 12.0),
        "gemini-pro-latest": (2.0, 12.0),
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
    
    # Load persona + knowledge layer
    persona_path = WORKSPACE / "skills/creative-technologist/personas/RESEARCHER.md"
    persona = persona_path.read_text() if persona_path.exists() else ""
    rubric = load_reference("art-direction-rubric.md")
    patterns = load_reference("creative-patterns.md")
    wiki_context = get_wiki_context(_brief_path_from_state(state))
    past_learnings = get_relevant_learnings(state["brief"])  # legacy, will phase out
    
    # Build diverse search queries from the brief
    task = f"""{persona}

You are a design researcher using Refero (a curated library of 130,000+ real product screens).
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

{('## Pipeline Wiki — Compiled Knowledge (what works, what fails, taste model)' + chr(10) + wiki_context) if wiki_context else ''}

{('## Past Run Learnings (legacy)' + chr(10) + past_learnings) if past_learnings else ''}
"""
    
    result = run_hermes(f"{state['name']}-research", task, max_time=900)
    
    research_path = run_dir / "VISUAL-RESEARCH.md"
    research_content = research_path.read_text() if research_path.exists() else "Research incomplete"
    
    moodboard_files = list((run_dir / "moodboard").glob("*"))

    # Bug A: generate per-brief diversification axes BEFORE fan-out so
    # designers get artifact-appropriate eras (not share-card-shaped ones).
    # The call needs the research output above, hence running here.
    axes_input_state = {
        **state,
        "research": {"content": research_content, "status": result["status"]},
    }
    diversification_axes = generate_diversification_axes(axes_input_state)

    out = {
        "research": {"content": research_content, "status": result["status"]},
        "moodboard": [str(f) for f in moodboard_files],
        "diversification_axes": diversification_axes,
        "phase": "research_complete",
        "cost_usd": state.get("cost_usd", 0) + 0.50,  # estimated
    }
    tracer.end_span(span, output={
        "status": result["status"],
        "moodboard_count": len(moodboard_files),
        "diversification_axes": [c.get("axis_name", "?") for c in diversification_axes],
    })
    return out


# Bug A: legacy share-card-shaped designer configs. Kept as a final-fallback if
# the diversification LLM call fails. The pipeline normally replaces these
# wholesale via ``generate_diversification_axes()`` at the end of research_node.
_DESIGNER_MODEL_ROTATION = ["claude-opus", "gpt-5", "gemini"]

_LEGACY_DESIGNER_CONFIGS = [
    {
        "designer_id": 0,
        "model": "claude-opus",
        "axis_name": "3D/Spatial",
        "era": "Your concept must use 3D/SPATIAL techniques as its primary visual language. Think: CSS 3D transforms, isometric perspective, parallax depth layers, perspective grids, stacked planes in Z-space. The piece should feel like it has PHYSICAL DEPTH — objects at different distances from the viewer. Do NOT make a flat 2D layout.",
        "anti_patterns": "No flat layouts, no gradients, no glassmorphism, no backdrop-blur, no rounded corners > 4px.",
    },
    {
        "designer_id": 1,
        "model": "gpt-5",
        "axis_name": "Data Visualization",
        "era": "Your concept must use DATA VISUALIZATION or INFOGRAPHIC techniques as its primary visual language. Think: charts, graphs, radial layouts, node networks, treemaps, bubble plots, heat maps. Information must be ENCODED into the visual structure itself.",
        "anti_patterns": "No centered layouts, no hero sections, no card grids, no Tailwind defaults.",
    },
    {
        "designer_id": 2,
        "model": "gemini",
        "axis_name": "Kinetic Typography",
        "era": "Your concept must use KINETIC TYPOGRAPHY and MOTION as its primary visual language. Think: text that moves, morphs, splits, glitches, or transforms. The piece should feel ALIVE and MOVING even in a static screenshot.",
        "anti_patterns": "No static layouts, no soft shadows, no floating elements, no pastel palettes, no generic sans-serif, no template energy.",
    },
]


def generate_diversification_axes(state: PipelineState) -> list:
    """Bug A: ask Claude Opus to propose 3 diversification axes for THIS brief.

    The hardcoded ``_LEGACY_DESIGNER_CONFIGS`` assume the artifact is a static
    share card ("the CARD should feel ALIVE"). For non-card briefs (a game, a
    flow, a poster) the wording is semantically wrong and corrupts
    diversification. Instead, generate axes per-brief.

    Output shape: a list of 3 dicts, each with the same keys as
    ``_LEGACY_DESIGNER_CONFIGS`` (``designer_id``, ``model``, ``axis_name``,
    ``era``, ``anti_patterns``). Falls back to the legacy configs on error.

    Side effect: writes ``{run_dir}/diversification-axes.json`` for the QA
    review and human gate.
    """
    run_dir = RUNS_DIR / state["name"]
    brief_text = state.get("brief", "")
    research = state.get("research", {}) or {}
    research_content = (research.get("content") or "")[:8000]

    axes_prompt = f"""You are the creative director for a parallel-designer pipeline. THREE designers
are about to attack the same brief in parallel, each with a different model.
Your job is to assign each designer a DIVERSIFICATION AXIS — a different
primary visual language so the three outputs feel genuinely different rather
than three variations of the same idea.

## The brief

{brief_text[:6000]}

## Visual research (moodboard distilled into a doc)

{research_content if research_content else '(no research available — work from the brief alone)'}

## Your task

Propose 3 diversification axes for 3 parallel designers. EACH axis must:
- Be a different primary visual language or rendering approach
- Apply NATURALLY to THIS artifact type. Read the brief carefully — is this a
  static card? An interactive game? A multi-screen flow? A poster? An
  onboarding flow? A dashboard? Your axes must fit the artifact.
- Use language that does NOT assume any specific artifact format. Do NOT say
  "the card should feel" or "the ranked list" — the artifact might not be a
  card or list at all. Use generic words like "the piece," "the experience,"
  "the composition," etc.
- Push designers toward genuinely different creative directions, not minor
  variations of one idea.

## Anti-patterns to AVOID
- Don't propose axes that all assume the artifact is a card or a list
- Don't propose 3 axes that collapse to "3D vs 2D vs animated"
- Don't reference moodboard CONTENT ("like the Nike screen"), only visual
  TECHNIQUES
- Don't use share-card-era language ("the card should feel\u2026")
- Don't propose the SAME axis three times with different wording

## Output format

Return ONLY a JSON array of 3 objects (no prose before or after). Each object
has exactly these keys:
- `axis_name`: short label (2-4 words), e.g. "Cinematic Compositing"
- `era`: 2-4 sentence prompt fragment that will be dropped into the designer
  prompt. Tells them what primary visual language to use and what feel to
  pursue. Generic to artifact type.
- `anti_patterns`: comma-separated list of things to avoid in this axis
  specifically.

Example shape (DO NOT use these literal axes, generate fresh ones for the
brief above):

```json
[
  {{"axis_name": "…", "era": "…", "anti_patterns": "…"}},
  {{"axis_name": "…", "era": "…", "anti_patterns": "…"}},
  {{"axis_name": "…", "era": "…", "anti_patterns": "…"}}
]
```

Generate the 3 axes now."""

    model = resolve_model("claude-opus")
    max_tokens = max_output_for(model, kind="verdict")

    raw_text = ""
    try:
        with tracer.generation(
            name="diversification_axes",
            model=model,
            input=axes_prompt,
            model_parameters={"max_tokens": max_tokens},
            metadata={"phase": "diversification", "run": state["name"]},
        ) as gen:
            msg = anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": axes_prompt}],
            )
            raw_text = msg.content[0].text if msg.content else ""
            gen.set_output(raw_text)
            if msg.usage:
                gen.set_usage(
                    input_tokens=msg.usage.input_tokens,
                    output_tokens=msg.usage.output_tokens,
                )
                track_cost(
                    model,
                    msg.usage.input_tokens,
                    msg.usage.output_tokens,
                    "diversification",
                )
    except Exception as e:
        print(f"  ⚠️  diversification axes LLM call failed: {e} — falling back to legacy configs")
        return list(_LEGACY_DESIGNER_CONFIGS)

    # Parse JSON out of the response. Tolerate code fences and prose around it.
    parsed = None
    import re as _re
    fenced = _re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw_text, _re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        # First [...] block.
        m = _re.search(r"\[\s*\{.*\}\s*\]", raw_text, _re.DOTALL)
        candidate = m.group(0) if m else None
    if candidate:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as e:
            print(f"  ⚠️  diversification axes JSON parse failed: {e}")

    if not isinstance(parsed, list) or len(parsed) < 3:
        print(f"  ⚠️  diversification axes call returned invalid shape — falling back to legacy configs")
        return list(_LEGACY_DESIGNER_CONFIGS)

    # Coerce into designer_configs shape. Take exactly 3.
    designer_configs = []
    for i, item in enumerate(parsed[:3]):
        if not isinstance(item, dict):
            continue
        designer_configs.append({
            "designer_id": i,
            "model": _DESIGNER_MODEL_ROTATION[i % len(_DESIGNER_MODEL_ROTATION)],
            "axis_name": str(item.get("axis_name", f"axis-{i}"))[:80],
            "era": str(item.get("era", "")).strip(),
            "anti_patterns": str(item.get("anti_patterns", "")).strip(),
        })

    if len(designer_configs) < 3:
        print(f"  ⚠️  diversification axes call missing required fields — falling back to legacy configs")
        return list(_LEGACY_DESIGNER_CONFIGS)

    # Persist for the run summary / human review.
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "diversification-axes.json").write_text(
            json.dumps(designer_configs, indent=2)
        )
        print(f"  🧭 Diversification axes (per-brief): " +
              ", ".join(c["axis_name"] for c in designer_configs))
    except Exception as e:
        print(f"  ⚠️  could not persist diversification-axes.json: {e}")

    return designer_configs


def fan_out_designers(state: PipelineState) -> list:
    """Fan out to 3 parallel designer nodes with different model families.

    Bug A: designer eras are now generated PER-BRIEF by
    ``generate_diversification_axes()`` (called from ``research_node``) and
    passed through ``state['diversification_axes']``. Falls back to the
    hardcoded legacy configs only if the per-brief generator failed.
    """
    designer_configs = state.get("diversification_axes")
    if not designer_configs or not isinstance(designer_configs, list) or len(designer_configs) < 3:
        print("  ⚠️  no per-brief diversification axes in state — using legacy configs")
        designer_configs = list(_LEGACY_DESIGNER_CONFIGS)

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
    tactics = load_reference("enhancement-tactics.md")
    techniques_index = load_reference("advanced-techniques.md")
    contract_template = load_reference("design-contract-template.md")
    wiki_context = get_wiki_context(_brief_path_from_state(state))
    
    task = f"""{persona}

## Available Techniques (pick from these — they are PROVEN to work in HTML/CSS/JS)
{tactics if tactics else "(No technique menu available — use your expertise)"}

## Advanced Techniques Reference (technique index — reference by name in your contract)
{techniques_index if techniques_index else ""}

{('## Pipeline Wiki — Compiled Knowledge (what works, what fails, taste model)' + chr(10) + wiki_context) if wiki_context else ''}

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

{"## DESIGN SYSTEM CONSTRAINT" + chr(10) + "You MUST use ONLY the fonts, colors, and spacing from this design system. Creative expression happens WITHIN the system, not by breaking it. Non-compliant builds will be rejected by automated checking." + chr(10) + state.get('design_system', '') + chr(10) if state.get('design_system') else ""}## Your Constraints
- Era/Reference Direction: {config['era']}
- Anti-Patterns (DO NOT USE): {config['anti_patterns']}
- Do NOT do browser web research. The Visual Research above is your complete reference set.
- If you have Refero MCP tools, you MAY do 1-2 targeted searches via `mcp_refero_refero_search_screens` — but no more. Spend your budget on DESIGNING, not researching.

## REQUIRED OUTPUT FORMAT

Your approach doc MUST include TWO key sections:
1. `## ASSET MANIFEST` — visual assets to be generated (images, textures, graphics)
2. `## BUILD CONTRACT` — concrete, grep-able specs for the builder

### Asset Manifest

The ASSET MANIFEST lists visual assets that will be GENERATED as real images before the build phase.
Think like an art director commissioning photography/design work. These become real images the builder embeds.

```
## ASSET MANIFEST

### Background Texture
- type: texture
- description: "Dark concrete surface with subtle grain, almost black (#0a0a0a) with micro-noise and hairline cracks"
- dimensions: 1080x1920
- model_hint: flux-schnell

### Hero Product Shot
- type: product
- description: "Air Jordan 1 Chicago, side profile view, floating on transparent dark background, dramatic studio lighting from above left, slight drop shadow"
- dimensions: 540x540
- model_hint: flux-2-pro

### Rank Badge
- type: graphic
- description: "Gold metallic #1 badge, circular embossed design, premium luxury feel, dark background"
- dimensions: 200x200
- model_hint: recraft-v3

### Distress Overlay
- type: decoration
- description: "Subtle diagonal scratch marks and dust particles, white marks on dark background, grunge texture"
- dimensions: 1080x1920
- model_hint: flux-schnell
```

Asset types: texture, product, graphic, decoration, atmosphere, illustration
Model hints: flux-schnell (fast/cheap textures), flux-2-pro (photorealistic), recraft-v3 (text/graphics), nano-banana-2 (creative illustrations)

**What to request as assets (DO):**
- Background textures (concrete, paper, fabric, noise, abstract)
- Product photography (styled hero shots of ranked items)
- Graphic elements (badges, stamps, dividers, rank indicators)
- Atmospheric effects (smoke, light leaks, bokeh, grain overlays)

**What NOT to request (the builder handles these in code):**
- UI controls (buttons, inputs)
- Animations (GSAP/CSS)
- Layout structure (HTML/CSS)
- Text content (rendered by the browser)

### Build Contract

Your approach doc MUST also end with a section called `## BUILD CONTRACT` that contains ONLY concrete, grep-able specs. No prose, no "feel like", no "inspired by". Just values.

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
    
    # Decompose prompt size by component for bloat analysis
    designer_prompt_components = {
        "persona_chars": len(persona),
        "tactics_chars": len(tactics) if tactics else 0,
        "techniques_chars": len(techniques_index) if techniques_index else 0,
        "wiki_chars": len(wiki_context) if wiki_context else 0,
        "brief_chars": len(state.get("brief", "")),
        "research_chars": len((state.get("research", {}) or {}).get("content", "") or ""),
        "design_system_chars": len(state.get("design_system", "") or ""),
        "total_chars": len(task),
    }
    with tracer.generation(
        name=f"designer_{designer_id}_hermes",
        model=f"hermes:{config['model']}",
        input=task,
        model_parameters={"max_time": 600},
        metadata={"phase": "designer", "designer_id": designer_id,
                   "intended_model": config["model"],
                   "era": config.get("era"),
                   "prompt_components": designer_prompt_components},
    ) as gen:
        result = run_hermes(f"{state['name']}-designer-{designer_id}", task, max_time=600)

        approach_path = run_dir / f"concepts/designer-{designer_id}-APPROACH.md"

        # Retry file read — Hermes may still be writing when .done signal fires
        approach = "Approach not generated"
        for attempt in range(3):
            if approach_path.exists() and approach_path.stat().st_size > 100:
                approach = approach_path.read_text()
                break
            time.sleep(2)

        gen.set_output(approach)
        gen.set_usage(
            input_tokens=estimate_tokens(task),
            output_tokens=estimate_tokens(approach),
            estimated=True,
        )
        gen.add_metadata(hermes_status=result.get("status"))
        if result.get("status") != "done":
            gen.set_error(f"hermes status: {result.get('status')}")
    
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
        f"## Designer {a['designer_id']} ({a['model']})\n{a['content']}"
        for a in state["approaches"]
    ])
    
    gate_prompt_obj = prompts.get("approach_gate")
    gate_prompt_text = gate_prompt_obj.compile(approaches_text=approaches_text)
    gate_model = resolve_model("claude-opus")
    gate_max_tokens = max_output_for(gate_model, kind="verdict")

    with tracer.generation(
        name="approach_gate_llm",
        model=gate_model,
        input=gate_prompt_text,
        prompt_obj=gate_prompt_obj,
        model_parameters={"max_tokens": gate_max_tokens},
        metadata={"phase": "approach_gate", "approach_count": len(state["approaches"])},
    ) as gen:
        msg = anthropic_client.messages.create(
            model=gate_model,
            max_tokens=gate_max_tokens,
            messages=[{"role": "user", "content": gate_prompt_text}],
        )
        gate_text = msg.content[0].text
        gen.set_output(gate_text)
        if msg.usage:
            gen.set_usage(input_tokens=msg.usage.input_tokens,
                          output_tokens=msg.usage.output_tokens)
            track_cost(gate_model, msg.usage.input_tokens, msg.usage.output_tokens, "approach_gate")
    
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


# ── Asset Generation ────────────────────────────────────────────

# fal.ai model routing
ASSET_MODEL_MAP = {
    "texture": "fal-ai/flux/schnell",
    "product": "fal-ai/flux-2-pro",
    "graphic": "fal-ai/recraft-v3",
    "decoration": "fal-ai/flux/schnell",
    "atmosphere": "fal-ai/flux-2-pro",
    "illustration": "fal-ai/nano-banana-2",
}

ASSET_MODEL_HINTS = {
    "flux-schnell": "fal-ai/flux/schnell",
    "flux-2-pro": "fal-ai/flux-2-pro",
    "recraft-v3": "fal-ai/recraft-v3",
    "nano-banana-2": "fal-ai/nano-banana-2",
    "ideogram-v3": "fal-ai/ideogram-v3",
    "flux-pro-ultra": "fal-ai/flux-pro/v1.1-ultra",
}

ASSET_GEN_COSTS = {
    "fal-ai/flux/schnell": 0.003,
    "fal-ai/flux-2-pro": 0.03,
    "fal-ai/recraft-v3": 0.06,
    "fal-ai/nano-banana-2": 0.08,
    "fal-ai/ideogram-v3": 0.06,
    "fal-ai/flux-pro/v1.1-ultra": 0.06,
}


def extract_asset_manifest(approach_content: str) -> list:
    """Parse ASSET MANIFEST section from approach doc.
    Returns list of dicts: {name, type, description, width, height, model_hint}"""
    if "## ASSET MANIFEST" not in approach_content:
        return []
    
    manifest_text = approach_content.split("## ASSET MANIFEST", 1)[1]
    # Stop at next ## heading
    for marker in ["## BUILD CONTRACT", "## ANIMATION", "## LAYOUT", "## REQUIRED"]:
        if marker in manifest_text:
            manifest_text = manifest_text.split(marker, 1)[0]
    
    assets = []
    current = None
    for line in manifest_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("### "):
            if current:
                assets.append(current)
            name = line[4:].strip().lower().replace(" ", "-").replace("/", "-")
            current = {"name": name, "type": "texture", "description": "", "width": 1080, "height": 1080}
        elif current and line.startswith("- type:"):
            current["type"] = line.split(":", 1)[1].strip().lower()
        elif current and line.startswith("- description:"):
            desc = line.split(":", 1)[1].strip().strip('"\'')
            current["description"] = desc
        elif current and line.startswith("- dimensions:"):
            dims = line.split(":", 1)[1].strip()
            if "x" in dims.lower():
                parts = dims.lower().split("x")
                try:
                    current["width"] = int(parts[0].strip())
                    current["height"] = int(parts[1].strip())
                except ValueError:
                    pass
        elif current and line.startswith("- model_hint:"):
            hint = line.split(":", 1)[1].strip().split("(")[0].strip()
            current["model_hint"] = hint
        elif current and line.startswith("- ") and not any(line.startswith(f"- {k}:") for k in ["type", "description", "dimensions", "model_hint"]):
            # Additional description lines
            if current["description"]:
                current["description"] += " " + line[2:].strip()
    
    if current:
        assets.append(current)
    
    return assets


def route_asset_model(asset: dict) -> str:
    """Route asset to best fal.ai model based on type and optional hint."""
    if asset.get("model_hint"):
        mapped = ASSET_MODEL_HINTS.get(asset["model_hint"])
        if mapped:
            return mapped
    return ASSET_MODEL_MAP.get(asset.get("type", "texture"), "fal-ai/flux/schnell")


def generate_asset(asset: dict, fal_key: str) -> dict:
    """Generate a single asset via fal.ai. Returns {url, path, name, model, cost}."""
    import fal_client
    os.environ["FAL_KEY"] = fal_key
    
    model = route_asset_model(asset)
    prompt = asset["description"]
    
    # Enhance prompt based on type
    if asset["type"] == "texture":
        prompt += ", seamless, high quality, 8k texture"
    elif asset["type"] == "product":
        prompt += ", studio photography, clean background, dramatic lighting, high detail"
    elif asset["type"] == "graphic":
        prompt += ", clean design, transparent background, high contrast"
    elif asset["type"] == "atmosphere":
        prompt += ", cinematic, atmospheric, moody lighting"
    
    try:
        result = fal_client.subscribe(
            model,
            arguments={
                "prompt": prompt,
                "image_size": {
                    "width": asset.get("width", 1080),
                    "height": asset.get("height", 1080),
                },
                "num_images": 1,
            },
        )
        
        img_url = result["images"][0]["url"]
        cost = ASSET_GEN_COSTS.get(model, 0.05)
        track_cost(model, 0, 0, "asset_gen", override_cost=cost)
        
        return {
            "url": img_url,
            "name": asset["name"],
            "type": asset.get("type", "texture"),
            "model": model,
            "cost": cost,
            "width": asset.get("width", 1080),
            "height": asset.get("height", 1080),
            "prompt": prompt[:200],
        }
    except Exception as e:
        print(f"    [asset-gen] Error generating {asset['name']}: {e}")
        return None


def asset_gen_node(state: PipelineState) -> dict:
    """Phase 3.5: Generate visual assets from designers' asset manifests via fal.ai."""
    print(f"[ASSET GEN] Processing {len(state['approaches'])} approaches")
    span = tracer.start_span("asset_gen", input={"approach_count": len(state["approaches"])})
    
    fal_key = os.environ.get("FAL_KEY", "")
    if not fal_key:
        print("  [asset-gen] ⚠️  FAL_KEY not set — skipping asset generation")
        return {"asset_manifest": {}, "asset_base_url": ""}
    run_dir = RUNS_DIR / state["name"]
    assets_dir = run_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    all_assets = {}  # designer_id -> list of generated assets
    total_generated = 0
    
    for approach in state["approaches"]:
        if approach.get("status") not in ("done", "approved", None):
            continue
        
        designer_id = approach["designer_id"]
        manifest = extract_asset_manifest(approach["content"])
        
        if not manifest:
            print(f"  [asset-gen] Designer {designer_id}: no asset manifest — skipping")
            all_assets[designer_id] = []
            continue
        
        print(f"  [asset-gen] Designer {designer_id}: {len(manifest)} assets to generate")
        concept_dir = assets_dir / f"concept-{designer_id}"
        concept_dir.mkdir(parents=True, exist_ok=True)
        
        generated = []
        for asset in manifest[:8]:  # max 8 assets per concept
            print(f"    [asset-gen] Generating: {asset['name']} ({asset['type']}) via {route_asset_model(asset)}")
            
            result = generate_asset(asset, fal_key)
            if not result:
                continue
            
            # Download image to local file
            try:
                import urllib.request
                ext = "jpg"  # fal.ai typically returns JPEG
                local_path = concept_dir / f"{asset['name']}.{ext}"
                urllib.request.urlretrieve(result["url"], str(local_path))
                result["local_path"] = str(local_path)
                result["size_kb"] = local_path.stat().st_size // 1024
                print(f"    [asset-gen] ✅ {asset['name']}: {result['size_kb']}KB ({result['model']})")
                generated.append(result)
                total_generated += 1
            except Exception as dl_e:
                print(f"    [asset-gen] Download error for {asset['name']}: {dl_e}")
                # Still include URL-only reference
                result["local_path"] = None
                generated.append(result)
                total_generated += 1
        
        all_assets[designer_id] = generated
        
        # Save manifest for this concept
        manifest_path = concept_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(generated, f, indent=2)
    
    # Write a consolidated asset reference file per concept (builder reads this)
    for approach in state["approaches"]:
        did = approach["designer_id"]
        assets = all_assets.get(did, [])
        
        if assets:
            ref_path = assets_dir / f"concept-{did}" / "ASSETS.md"
            asset_block = "# Generated Assets\n\n"
            asset_block += "These are REAL images saved locally. Read each file and embed as base64 data URIs in your HTML.\n"
            asset_block += "This makes the HTML fully self-contained — no external image dependencies.\n\n"
            for a in assets:
                local = a.get("local_path", "")
                asset_block += f"## {a['name']} ({a['type']}, {a['width']}×{a['height']})\n"
                asset_block += f"- Local path: `{local}`\n"
                asset_block += f"- Read this file, base64-encode it, and embed as:\n"
                asset_block += f"  `<img src=\"data:image/jpeg;base64,{{BASE64_DATA}}\" />`\n"
                asset_block += f"  or `background-image: url('data:image/jpeg;base64,{{BASE64_DATA}}');`\n"
                asset_block += f"- Description: {a.get('prompt', '')[:150]}\n"
                asset_block += f"- Size: {a.get('size_kb', '?')}KB\n\n"
            
            ref_path.write_text(asset_block)
            
            manifest_path = assets_dir / f"concept-{did}" / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(assets, f, indent=2)
    
    print(f"  [asset-gen] Total: {total_generated} assets generated across {len(state['approaches'])} concepts")
    
    tracer.end_span(span, output={"total_generated": total_generated, "by_concept": {str(k): len(v) for k, v in all_assets.items()}})
    
    return {"asset_manifest": all_assets, "asset_base_url": ""}


def fan_out_builders(state: PipelineState) -> list:
    """Fan out to 3 parallel builder nodes, each with a different model assignment.

    Always sets builder_mode="initial" so the unified builder_node runs the
    initial-build path. The companion playability fan-out (fan_out_playability_mode)
    sets builder_mode="playability" instead.
    """
    model_assignments = ["claude-opus", "gpt-5", "gemini-pro-latest"]  # frontier-only; gemini-pro-latest auto-tracks Google's latest Pro
    builders = []
    for i in range(len(state["approaches"])):
        model = model_assignments[i % len(model_assignments)]
        builders.append(Send("builder", {
            **state,
            "build_index": i,
            "builder_model": model,
            "builder_mode": "initial",
        }))
    return builders


def build_direct_api(model: str, prompt: str, output_path: Path, run_name: str, moodboard_images: Optional[list] = None) -> dict:
    """Build HTML via direct API call (no Hermes). Returns status dict.
    Used for GPT and Gemini builders that don't need tool use.
    moodboard_images: optional list of image file paths to send as vision input."""
    
    print(f"    [direct-api] Calling {model}...")
    
    # Encode moodboard images for vision-capable models
    image_parts = []
    if moodboard_images:
        import base64
        for img_path in moodboard_images[:3]:  # max 3 to keep reasonable
            try:
                with open(img_path, "rb") as f:
                    img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
                ext = str(img_path).rsplit(".", 1)[-1].lower()
                mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
                image_parts.append({"b64": img_b64, "mime": mime, "name": Path(img_path).name})
                print(f"    [direct-api] Attached moodboard image: {Path(img_path).name}")
            except Exception as e:
                print(f"    [direct-api] Failed to encode {img_path}: {e}")
    
    suffix = "\n\nRespond with ONLY the complete HTML file content. No markdown fences, no explanation. Start with <!DOCTYPE html>."
    
    try:
        if model.startswith("gpt"):
            # Build multimodal message with images if available
            if image_parts:
                content_parts = []
                content_parts.append({"type": "text", "text": "## MOODBOARD REFERENCE IMAGES\nStudy these — your build should feel like it belongs in this visual family:\n"})
                for img in image_parts:
                    content_parts.append({"type": "text", "text": f"**{img['name']}:**"})
                    content_parts.append({"type": "image_url", "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}})
                content_parts.append({"type": "text", "text": prompt + suffix})
                messages = [{"role": "user", "content": content_parts}]
            else:
                messages = [{"role": "user", "content": prompt + suffix}]
            
            resolved_model = resolve_model(model)
            response = openai_client.chat.completions.create(
                model=resolved_model,
                max_completion_tokens=max_output_for(resolved_model),
                messages=messages,
            )
            html = response.choices[0].message.content
            if response.usage:
                track_cost(model, response.usage.prompt_tokens, response.usage.completion_tokens, "builder")
                
        elif model.startswith("gemini"):
            from google import genai as google_genai
            gemini_client = google_genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
            gemini_model_id = resolve_model("gemini-3.1-pro-preview")
            
            # Build multimodal content for Gemini
            if image_parts:
                from google.genai import types as genai_types
                parts = []
                parts.append(genai_types.Part.from_text(text="## MOODBOARD REFERENCE IMAGES\nStudy these — your build should feel like it belongs in this visual family:\n"))
                for img in image_parts:
                    parts.append(genai_types.Part.from_text(text=f"**{img['name']}:**"))
                    parts.append(genai_types.Part.from_bytes(data=base64.standard_b64decode(img["b64"]), mime_type=img["mime"]))
                parts.append(genai_types.Part.from_text(text=prompt + suffix))
                contents = parts
            else:
                contents = prompt + suffix
            
            response = gemini_client.models.generate_content(
                model=gemini_model_id,
                contents=contents,
                config={"max_output_tokens": max_output_for(gemini_model_id)},
            )
            html = response.text
            # Gemini usage tracking
            if hasattr(response, 'usage_metadata'):
                track_cost(gemini_model_id,
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
        print(f"    [direct-api] Error (attempt 1): {type(e).__name__}: {e}")
        # Retry up to 2 more times with backoff
        for attempt in range(2, 4):
            wait = 10 * (attempt - 1)
            print(f"    [direct-api] Retrying in {wait}s (attempt {attempt}/3)...")
            time.sleep(wait)
            try:
                if model.startswith("gpt"):
                    response = openai_client.chat.completions.create(
                        model=model,
                        max_completion_tokens=max_output_for(model),
                        messages=[{"role": "user", "content": prompt + "\n\nRespond with ONLY the complete HTML file content. No markdown fences, no explanation. Start with <!DOCTYPE html>."}],
                    )
                    html = response.choices[0].message.content
                    if response.usage:
                        track_cost(model, response.usage.prompt_tokens, response.usage.completion_tokens, "builder")
                elif model.startswith("gemini"):
                    from google import genai as google_genai
                    gemini_client = google_genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
                    resolved_gemini = resolve_model("gemini-3.1-pro-preview")
                    response = gemini_client.models.generate_content(
                        model=resolved_gemini,
                        contents=prompt + "\n\nRespond with ONLY the complete HTML file content. No markdown fences, no explanation. Start with <!DOCTYPE html>.",
                        config={"max_output_tokens": max_output_for(resolved_gemini)},
                    )
                    html = response.text
                    if hasattr(response, 'usage_metadata'):
                        track_cost("gemini-3.1-pro-preview",
                            getattr(response.usage_metadata, 'prompt_token_count', 0),
                            getattr(response.usage_metadata, 'candidates_token_count', 0),
                            "builder")
                else:
                    break
                
                html = html.strip()
                if html.startswith("```html"): html = html[7:]
                if html.startswith("```"): html = html[3:]
                if html.endswith("```"): html = html[:-3]
                html = html.strip()
                
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(html)
                print(f"    [direct-api] Wrote {len(html)} bytes on retry {attempt}")
                return {"status": "done"}
            except Exception as retry_e:
                print(f"    [direct-api] Retry {attempt} failed: {type(retry_e).__name__}: {retry_e}")
        
        return {"status": "failed", "error": str(e)}


def builder_node(state: dict) -> dict:
    """Phase 3 (unified): Build HTML prototype OR continue an existing build.

    Branches on state["builder_mode"]:
      - "initial"      (default): write a fresh prototype from the approach doc.
      - "qa_fix"       : run the QA-fix patch loop (one iteration). Uses the
                         walker-driven playability+QA helper as the patch
                         driver, plus surfaces the latest QA report's issues
                         to the patch prompt. Mirrors the legacy playability
                         mode but with broader scope.
      - "judge_polish" : run the judge-polish patch loop (one iteration).
                         Patch is driven by the latest score's priority_fixes.
      - "playability"  : legacy alias for qa_fix (kept for back-compat).
    """
    mode = state.get("builder_mode") or "initial"
    if mode in ("qa_fix", "playability"):
        return _builder_qa_fix_run(state)
    if mode == "judge_polish":
        return _builder_judge_polish_run(state)

    idx = state["build_index"]
    approach = state["approaches"][idx]
    run_dir = RUNS_DIR / state["name"]
    builder_model = state.get("builder_model", "claude-opus")
    
    print(f"[BUILDER {idx}] Building from designer {approach['designer_id']} approach (model: {builder_model})")
    span = tracer.start_span(f"builder-{idx}", input={"model": builder_model, "designer": approach["designer_id"], "mode": "initial"})
    
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
    recipes = load_reference("recipes.md")
    
    # Load wiki context for builder (what scores well, anti-patterns, technique evidence)
    wiki_context = get_wiki_context(_brief_path_from_state(state), max_chars=4000)  # Shorter for builder — it's supplementary
    
    # 4.5C: Identify moodboard images for builder reference
    moodboard_dir = run_dir / "moodboard"
    all_moodboard = []
    if moodboard_dir.exists():
        for ext in ["*.png", "*.jpg", "*.jpeg"]:
            all_moodboard.extend(moodboard_dir.glob(ext))
    all_moodboard = sorted(all_moodboard)[:5]  # up to 5 reference images
    
    moodboard_ref = ""
    if all_moodboard:
        moodboard_ref = f"""
## REFERENCE IMAGES (study these — your build should feel like it belongs in this visual family)
The following moodboard images are at: {moodboard_dir}
"""
        for img in all_moodboard:
            moodboard_ref += f"- {img.name}\n"
        moodboard_ref += "\nOpen and study these images before building. They represent the quality bar and aesthetic direction.\n"
    
    # Load generated assets for this concept
    assets_ref = ""
    asset_images_for_vision = []
    assets_dir = run_dir / "assets" / f"concept-{approach['designer_id']}"
    assets_md = assets_dir / "ASSETS.md"
    if assets_md.exists():
        # Builder gets asset names + placeholder markers
        # Post-processing replaces markers with base64 data URIs (avoids context bloat)
        asset_ref_block = ""
        manifest_path = assets_dir / "manifest.json"
        if manifest_path.exists():
            asset_list = json.loads(manifest_path.read_text())
            for a in asset_list:
                name = a["name"]
                asset_ref_block += f"\n### {name} ({a.get('type','')}, {a.get('width','')}×{a.get('height','')})\n"
                asset_ref_block += f"- Description: {a.get('prompt', '')[:150]}\n"
                asset_ref_block += f"- Use in HTML: `<img src=\"asset://{name}\" />` or `background-image: url('asset://{name}');`\n"
                asset_ref_block += f"- The `asset://` prefix will be automatically replaced with the real image data after build.\n"
        
        # Bug C: emit the exact list of available asset slugs and a hard rule.
        # The builder must not invent asset:// URLs that aren't commissioned.
        _available_slug_list = "\n".join(f"- asset://{a['name']}" for a in asset_list) if manifest_path.exists() and asset_list else "(no assets commissioned)"

        assets_ref = f"""
## 🎨 GENERATED VISUAL ASSETS (CRITICAL — USE THESE)

You have pre-generated visual assets. Reference them using the `asset://` prefix shown below.
After you write the HTML, a post-processor will replace every `asset://name` with the actual
base64-encoded image data, making the HTML fully self-contained.

Do NOT use CSS gradients, colored divs, or placeholder boxes where an asset exists.
Do NOT try to base64-encode images yourself — just use `asset://name` references.

{asset_ref_block if asset_ref_block else assets_md.read_text()}

### ⚠️ ASSET-REFERENCE CONTRACT (HARD RULE — BUILD WILL BE VALIDATED)

Your designer has commissioned EXACTLY the following asset slugs. The `asset://`
post-processor can ONLY substitute these. Any other `asset://` URL you write
will end up as a broken image (ERR_UNKNOWN_URL_SCHEME) in the shipped HTML.

**Available asset slugs (use ONLY these):**
{_available_slug_list}

**Rules:**
1. NEVER write `asset://something-not-in-the-list-above`. Do not invent slugs.
2. If you need an image the designer didn't commission, draw it inline with
   CSS/SVG, OR use a styled placeholder div — NEVER write a made-up `asset://`.
3. If a missing asset would meaningfully improve the build, add a line to a
   sibling file `NEEDED_ASSETS.md` describing what you wanted; the human gate
   will see it. DO NOT block the build on this.
4. After you write the HTML, the pipeline will scan for `asset://` references
   and any slug not in the list above is flagged as MISSING in the QA report.

**IMPORTANT:** These assets are the design foundation. Your HTML is the frame — the assets carry the
visual weight. A build that ignores these assets and uses CSS-only visuals will be rejected.
"""
        # Collect asset images for vision input
        for ext in ["*.jpg", "*.jpeg", "*.png"]:
            asset_images_for_vision.extend(sorted(assets_dir.glob(ext))[:5])
    
    task = f"""{persona}

## Your Task
Build a complete, working HTML prototype. You have two inputs:
1. A Creative Narrative (context for understanding the concept)
2. A BUILD CONTRACT (hard requirements you MUST follow exactly)
3. GENERATED ASSETS — pre-made images to embed (backgrounds, product shots, graphics)

The Build Contract contains grep-able specs. After you write your HTML, I will programmatically verify:
- Your file contains the REQUIRED FONTS (exact font-family values)
- Your file contains the REQUIRED COLORS (exact hex values)
- Your file does NOT contain any FORBIDDEN fonts or colors
- Each REQUIRED CSS TECHNIQUE is present
- Generated assets are referenced in the HTML (img src or background-image URLs)

If verification fails, your build is rejected and you must redo it.

---

## CREATIVE NARRATIVE (read for context — this is the designer's full vision)
{creative_narrative}

---

## CODE RECIPES (proven implementations — adapt these, don't reinvent)
{recipes if recipes else "(No recipes available)"}
{moodboard_ref}
{assets_ref}

---

## ⚠️ BUILD CONTRACT (HARD REQUIREMENTS — YOUR BUILD WILL BE GREP-CHECKED)
{build_contract}

---

{"## ⛔ DESIGN SYSTEM ENFORCEMENT (automated checking — violations = rejection)" + chr(10) + "Your build will be scanned for design system compliance. ONLY the following fonts and colors are allowed:" + chr(10) + state.get('design_system', '') + chr(10) + "Any font-family not in this system = REJECTION. Any hex color not in this palette (or within tolerance) = REJECTION." + chr(10) if state.get('design_system') else ""}{('## 📚 CREATIVE DIRECTOR FEEDBACK — What Works & What Fails (from past runs)' + chr(10) + wiki_context + chr(10)) if wiki_context else ''}## Build Rules
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
    
    # Context budget check
    task_size = len(task)
    budget = get_context_budget(builder_model)
    usage_pct = task_size * 100 // budget
    print(f"  📊 Builder {idx} context: {task_size//1024}KB / {budget//1024}KB ({usage_pct}% of {builder_model} window)")
    if task_size > budget * 0.85:
        print(f"  ⚠️  Builder {idx}: context at {usage_pct}% — may impact output quality")
    
    # Combine moodboard + generated assets for vision input
    all_vision_images = list(all_moodboard) + asset_images_for_vision[:3]
    
    # Decompose builder prompt size by component (for bloat analysis later)
    builder_prompt_components = {
        "persona_chars": len(persona),
        "creative_narrative_chars": len(creative_narrative) if creative_narrative else 0,
        "recipes_chars": len(recipes) if recipes else 0,
        "moodboard_ref_chars": len(moodboard_ref) if moodboard_ref else 0,
        "assets_ref_chars": len(assets_ref) if assets_ref else 0,
        "build_contract_chars": len(build_contract) if build_contract else 0,
        "wiki_chars": len(wiki_context) if wiki_context else 0,
        "design_system_chars": len(state.get("design_system", "") or ""),
        "total_chars": task_size,
        "budget_chars": budget,
        "budget_usage_pct": usage_pct,
    }
    builder_gen_metadata = {
        "phase": "builder", "build_index": idx,
        "intended_model": builder_model,
        "designer_id": approach["designer_id"],
        "vision_image_count": len(all_vision_images),
        "prompt_components": builder_prompt_components,
    }

    # Route to appropriate builder based on model
    if builder_model.startswith("gpt") or builder_model.startswith("gemini"):
        # Direct API — model generates HTML directly, with moodboard + asset vision
        with tracer.generation(
            name=f"builder_{idx}_{builder_model}",
            model=builder_model,
            input=task,
            model_parameters={"max_time": 1800},
            metadata={**builder_gen_metadata, "runtime": "direct_api"},
        ) as gen:
            result = build_direct_api(builder_model, task, build_path, state["name"], moodboard_images=all_vision_images)
            built_html = build_path.read_text()[:5000] if build_path.exists() else ""
            gen.set_output(built_html)
            gen.set_usage(
                input_tokens=estimate_tokens(task),
                output_tokens=estimate_tokens(build_path.read_text() if build_path.exists() else ""),
                estimated=True,
            )
            gen.add_metadata(build_status=result.get("status"),
                             output_html_chars=build_path.stat().st_size if build_path.exists() else 0)
            if result.get("status") not in ("done", "completed", "success"):
                gen.set_error(f"build status: {result.get('status')}")
    else:
        # Hermes (Claude) — agent with tool use
        with tracer.generation(
            name=f"builder_{idx}_hermes",
            model=f"hermes:{builder_model}",
            input=task,
            model_parameters={"max_time": 1800, "max_turns": 50},
            metadata={**builder_gen_metadata, "runtime": "hermes"},
        ) as gen:
            result = run_hermes(f"{state['name']}-builder-{idx}", task, max_time=1800, max_turns=50)
            built_html = build_path.read_text()[:5000] if build_path.exists() else ""
            gen.set_output(built_html)
            gen.set_usage(
                input_tokens=estimate_tokens(task),
                output_tokens=estimate_tokens(build_path.read_text() if build_path.exists() else ""),
                estimated=True,
            )
            gen.add_metadata(hermes_status=result.get("status"),
                             output_html_chars=build_path.stat().st_size if build_path.exists() else 0)
            if result.get("status") != "done":
                gen.set_error(f"hermes status: {result.get('status')}")
    
    # Post-process: replace asset:// references with base64 data URIs
    if build_path.exists() and assets_dir.exists():
        import base64 as b64mod
        html_content = build_path.read_text()
        manifest_path = assets_dir / "manifest.json"
        if manifest_path.exists() and "asset://" in html_content:
            asset_list = json.loads(manifest_path.read_text())
            replacements = 0
            for a in asset_list:
                name = a["name"]
                lp = a.get("local_path")
                if lp and Path(lp).exists():
                    raw = Path(lp).read_bytes()
                    ext = str(lp).rsplit(".", 1)[-1].lower()
                    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
                    encoded = b64mod.b64encode(raw).decode("utf-8")
                    data_uri = f"data:{mime};base64,{encoded}"
                    # Replace all variants: asset://name, asset://name.jpg, etc.
                    for pattern in [f"asset://{name}", f"asset://{name}.jpg", f"asset://{name}.jpeg", f"asset://{name}.png"]:
                        if pattern in html_content:
                            html_content = html_content.replace(pattern, data_uri)
                            replacements += 1
            if replacements > 0:
                build_path.write_text(html_content)
                print(f"  [asset-inject] Replaced {replacements} asset:// references with base64 data URIs ({len(html_content)//1024}KB)")

    # Bug C: validate any remaining asset:// references against the manifest.
    # After base64 substitution, any surviving asset:// URL is a hallucinated
    # reference (builder invented a slug). Surface in QA + fall back to SVG
    # placeholders so the build doesn't ship with ERR_UNKNOWN_URL_SCHEME.
    asset_validation = {"matched": [], "missing": [], "extra_in_manifest": []}
    if build_path.exists() and assets_dir.exists():
        manifest_path = assets_dir / "manifest.json"
        if manifest_path.exists():
            asset_validation = validate_asset_references(build_path, manifest_path)
            missing = asset_validation.get("missing", [])
            if missing:
                print(f"  ⚠️  Builder {idx}: {len(missing)} unresolved asset:// refs (builder invented these):")
                for m in missing:
                    print(f"     ✗ asset://{m}")
                substituted = apply_missing_asset_fallbacks(build_path, missing)
                if substituted:
                    print(f"  [asset-fallback] Substituted {substituted} missing asset:// refs with SVG placeholders")
                # Surface for human gate / QA reports.
                needed_path = run_dir / "builds" / f"concept-{idx}-NEEDED_ASSETS.md"
                try:
                    lines = [
                        f"# Concept {idx} — Missing assets the builder referenced",
                        f"",
                        f"Builder model: {builder_model}",
                        f"Designer manifest: {manifest_path}",
                        f"",
                        "These asset:// references appeared in the HTML but were NOT in the",
                        "designer's manifest. They've been replaced with SVG placeholders.",
                        "",
                    ] + [f"- asset://{m}" for m in missing]
                    needed_path.write_text("\n".join(lines))
                except Exception as e:
                    print(f"     (failed to write NEEDED_ASSETS.md: {e})")
            extra = asset_validation.get("extra_in_manifest", [])
            if extra:
                print(f"  ℹ️  Builder {idx}: {len(extra)} commissioned assets unused by builder (wasted spend):")
                for e in extra[:5]:
                    print(f"     · {e}")

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
{build_contract}

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
    
    # NOTE: Self-review is now handled by qa_station_node (after all builds complete)
    
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
            "asset_validation": asset_validation,
        }],
        "builder_mode": "initial",  # routing signal for route_after_builder
    }
    tracer.end_span(span, output={
        "status": result["status"],
        "exists": build_path.exists(),
        "size": build_path.stat().st_size if build_path.exists() else 0,
        "compliance": compliance,
    })
    return build_out


def qa_station_node(state: PipelineState) -> dict:
    """QA Station: tests each build's rendered experience + content fidelity.
    
    Produces a structured QA Report per build. Routes:
    - PASS: advance to judge
    - FIXABLE: send fix instructions to builder (up to 2 attempts)
    - BROKEN: flag for human, skip from judge
    """
    builds = state["builds"]
    run_dir = RUNS_DIR / state["name"]
    qa_dir = run_dir / "qa-reports"
    qa_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = run_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[QA] Running QA station on {len(builds)} builds")
    span = tracer.start_span("qa_station", input={"build_count": len(builds)})
    
    # Extract sample data items from brief for content verification
    sample_items = _extract_sample_items(state["brief"])
    
    qa_reports = []
    
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception as e:
        print(f"  ⚠️  QA: Playwright failed to start ({e}) — falling back to source-only checks")
        browser = None
        pw = None
    
    for b in builds:
        build_path = Path(b["path"])
        idx = b["index"]
        concept_name = f"concept-{idx}"
        
        report = {
            "build": concept_name,
            "model": b.get("model", "unknown"),
            "source_checks": {},
            "experience_checks": {},
            "verdict": "BROKEN",
            "issues": [],
            "fix_attempts": 0,
        }
        
        if not build_path.exists() or build_path.stat().st_size < 500:
            report["issues"].append(f"Build file missing or empty ({build_path.stat().st_size if build_path.exists() else 0} bytes)")
            qa_reports.append(report)
            print(f"  ❌ {concept_name}: BROKEN — file missing/empty")
            continue
        
        html_content = build_path.read_text(errors="ignore")
        
        # ── SOURCE CHECKS (static, no browser) ──
        
        # Content verification: check sample data items
        items_found = []
        items_missing = []
        for item in sample_items:
            if item.lower() in html_content.lower():
                items_found.append(item)
            else:
                items_missing.append(item)
        
        report["source_checks"]["content"] = {
            "items_found": len(items_found),
            "items_expected": len(sample_items),
            "missing": items_missing,
            "pass": len(items_found) >= len(sample_items) * 0.7,  # 70% threshold
        }
        
        # Dimension check: look for 1080/1920 in CSS
        has_width = "1080" in html_content
        has_height = "1920" in html_content
        report["source_checks"]["dimensions"] = {
            "width_ref": has_width,
            "height_ref": has_height,
            "pass": has_width and has_height,
        }
        
        # Spec compliance (reuse existing)
        build_contract = b.get("compliance", {})
        report["source_checks"]["spec_compliance"] = build_contract
        
        if not report["source_checks"]["content"]["pass"]:
            report["issues"].append(f"Content fidelity: only {len(items_found)}/{len(sample_items)} sample items found. Missing: {', '.join(items_missing[:3])}")
        
        # ── EXPERIENCE CHECKS (browser) ──
        
        if browser:
            try:
                page = browser.new_page(viewport={"width": 1080, "height": 1920})
                
                # Collect console errors
                console_errors = []
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.on("pageerror", lambda err: console_errors.append(str(err)))
                
                page.goto(f"file://{build_path.resolve()}", wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(1000)
                
                # Screenshot at t=1s
                ss_t0 = screenshot_dir / f"{concept_name}.png"
                page.screenshot(path=str(ss_t0), full_page=False)
                
                # Screenshot at t=4s (to check animation)
                page.wait_for_timeout(3000)
                ss_t3 = screenshot_dir / f"{concept_name}-t3.png"
                page.screenshot(path=str(ss_t3), full_page=False)
                
                # Render check: pixel variance (non-blank)
                render_ok = _check_render(str(ss_t0))
                report["experience_checks"]["render"] = {
                    "pass": render_ok,
                    "screenshot": str(ss_t0),
                }
                if not render_ok:
                    report["issues"].append("Render check FAILED — page appears blank or near-blank")
                
                # Animation check: compare t=0 vs t=3
                anim_diff = _compare_screenshots(str(ss_t0), str(ss_t3))
                report["experience_checks"]["animation"] = {
                    "diff_percent": anim_diff,
                    "has_animation": anim_diff > 2.0,  # >2% pixel difference = something moved
                }
                
                # Visibility check: are all items visible in viewport?
                visibility = page.evaluate("""() => {
                    const items = [];
                    // Look for ranked items by common patterns
                    const selectors = ['[class*="item"]', '[class*="rank"]', '[class*="entry"]', 'li', '[class*="row"]'];
                    let found = [];
                    for (const sel of selectors) {
                        const els = document.querySelectorAll(sel);
                        if (els.length >= 5) {
                            found = Array.from(els);
                            break;
                        }
                    }
                    for (const el of found.slice(0, 15)) {
                        const rect = el.getBoundingClientRect();
                        items.push({
                            tag: el.tagName,
                            class: el.className.toString().slice(0, 40),
                            visible: rect.width > 0 && rect.height > 0,
                            in_viewport: rect.top < 1920 && rect.bottom > 0 && rect.left < 1080 && rect.right > 0,
                            top: Math.round(rect.top),
                            bottom: Math.round(rect.bottom),
                        });
                    }
                    return { total: found.length, items: items };
                }""")
                
                visible_count = sum(1 for i in visibility.get("items", []) if i.get("in_viewport"))
                overflow_items = [i for i in visibility.get("items", []) if i.get("visible") and not i.get("in_viewport")]
                
                report["experience_checks"]["visibility"] = {
                    "total_elements": visibility.get("total", 0),
                    "in_viewport": visible_count,
                    "overflow": len(overflow_items),
                    "pass": visible_count >= 8,  # at least 8 of ~10 items visible
                }
                if overflow_items:
                    report["issues"].append(f"Overflow: {len(overflow_items)} items outside 1080×1920 viewport")
                
                # Mobile viewport check (390×844 simulates iPhone)
                try:
                    mobile_page = browser.new_page(viewport={"width": 390, "height": 844})
                    mobile_page.goto(f"file://{build_path}", wait_until="networkidle")
                    mobile_page.wait_for_timeout(2000)
                    
                    mobile_check = mobile_page.evaluate("""() => {
                        const body = document.documentElement;
                        const items = [];
                        const selectors = ['[class*="item"]', '[class*="rank"]', '[class*="entry"]', 'li', '[class*="row"]'];
                        let found = [];
                        for (const sel of selectors) {
                            const els = document.querySelectorAll(sel);
                            if (els.length >= 5) { found = Array.from(els); break; }
                        }
                        let inView = 0;
                        for (const el of found.slice(0, 15)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                const visible = rect.top < body.clientHeight && rect.bottom > 0 && rect.left < body.clientWidth && rect.right > 0;
                                if (visible) inView++;
                            }
                        }
                        return {
                            scrollWidth: body.scrollWidth,
                            scrollHeight: body.scrollHeight,
                            clientWidth: body.clientWidth,
                            clientHeight: body.clientHeight,
                            itemsInView: inView,
                            totalItems: found.length,
                            needsScroll: body.scrollHeight > body.clientHeight * 1.5,
                        };
                    }""")
                    
                    mobile_ok = mobile_check.get("itemsInView", 0) >= 5 or not mobile_check.get("needsScroll", False)
                    report["experience_checks"]["mobile_viewport"] = {
                        "viewport": "390x844",
                        "items_visible": mobile_check.get("itemsInView", 0),
                        "needs_scroll": mobile_check.get("needsScroll", False),
                        "scroll_height": mobile_check.get("scrollHeight", 0),
                        "pass": mobile_ok,
                    }
                    if not mobile_ok:
                        report["issues"].append(f"Mobile viewport: only {mobile_check.get('itemsInView', 0)} items visible (scroll height {mobile_check.get('scrollHeight', 0)}px on 844px viewport)")
                    
                    mobile_page.close()
                except Exception as mob_e:
                    print(f"    [qa] Mobile check error: {mob_e}")
                
                # Console errors
                report["experience_checks"]["console_errors"] = {
                    "count": len(console_errors),
                    "errors": console_errors[:5],
                    "pass": len(console_errors) == 0,
                }
                if console_errors:
                    report["issues"].append(f"Console errors: {len(console_errors)} — {console_errors[0][:80]}")
                
                # Image loading check
                images_status = page.evaluate("""() => {
                    const imgs = document.querySelectorAll('img');
                    let loaded = 0, broken = 0;
                    imgs.forEach(img => {
                        if (img.complete && img.naturalWidth > 0) loaded++;
                        else broken++;
                    });
                    return { total: imgs.length, loaded, broken };
                }""")
                report["experience_checks"]["images"] = images_status
                if images_status.get("broken", 0) > 0:
                    report["issues"].append(f"Broken images: {images_status['broken']}/{images_status['total']}")
                
                page.close()
                
            except Exception as e:
                report["issues"].append(f"Browser QA failed: {type(e).__name__}: {str(e)[:100]}")
                report["experience_checks"]["error"] = str(e)
                print(f"  ⚠️  {concept_name}: browser QA error — {e}")
        
        # ── DESIGN SYSTEM COMPLIANCE CHECK ──
        if state.get("design_system"):
            ds_result = check_design_system_compliance(build_path, state["design_system"])
            report["source_checks"]["design_system"] = ds_result
            if not ds_result["pass"]:
                for v in ds_result["violations"]:
                    report["issues"].append(f"Design system violation: {v}")
                print(f"     ⚠️  Design system: {len(ds_result['violations'])} violations")
        
        # ── VERDICT ──
        critical_failures = [i for i in report["issues"] if "BROKEN" in i or "blank" in i.lower() or "missing/empty" in i.lower()]
        fixable_issues = [i for i in report["issues"] if i not in critical_failures]
        
        if critical_failures:
            report["verdict"] = "BROKEN"
        elif fixable_issues:
            report["verdict"] = "FIXABLE"
        else:
            report["verdict"] = "PASS"
        
        # Save QA report
        report_path = qa_dir / f"{concept_name}-qa.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"  {'✅' if report['verdict'] == 'PASS' else '🔧' if report['verdict'] == 'FIXABLE' else '❌'} {concept_name}: {report['verdict']} ({len(report['issues'])} issues)")
        for issue in report["issues"]:
            print(f"     → {issue}")
        
        qa_reports.append(report)
    
    # ── FIX ROUND for FIXABLE builds (up to 2 attempts) ──
    for i, report in enumerate(qa_reports):
        if report["verdict"] != "FIXABLE" or report["fix_attempts"] >= 2:
            continue
        
        build = builds[i]
        build_path = Path(build["path"])
        fix_instructions = "\n".join(f"- {issue}" for issue in report["issues"])
        
        fix_prompt = f"""Your build at {build_path} has QA issues that need fixing:

{fix_instructions}

Fix these issues in the existing file. Be surgical — fix only what's broken.
Save the fixed file to: {build_path}
"""
        print(f"  🔄 {report['build']}: sending QA fix round ({report['fix_attempts'] + 1}/2)...")
        
        build_model = build.get("model", "")
        if build_model.startswith("gpt") or build_model.startswith("gemini"):
            # Direct API fix
            try:
                html_content = build_path.read_text()
                html_size = len(html_content)
                
                # CRITICAL: If HTML contains base64 assets (>100KB), extract them before fixing
                # and re-inject after. Sending 400KB+ of base64 to a fix model causes it to
                # rewrite from scratch, losing all assets. (V4b regression: 436KB → 30KB)
                preserved_assets = {}
                code_html = html_content
                if html_size > 100000 and "data:image/" in html_content:
                    import re as re_mod
                    # Replace base64 data URIs with placeholders
                    def _preserve_asset(match):
                        key = f"__PRESERVED_ASSET_{len(preserved_assets)}__"
                        preserved_assets[key] = match.group(0)
                        return key
                    code_html = re_mod.sub(
                        r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+',
                        _preserve_asset,
                        html_content
                    )
                    print(f"    [qa-fix] Preserved {len(preserved_assets)} base64 assets ({html_size//1024}KB → {len(code_html)//1024}KB)")
                
                fix_system = "You are fixing HTML/CSS/JS issues in a build. Output ONLY the complete fixed HTML file, no explanation. Do NOT remove or modify any image src attributes, data URIs, or asset references — only fix the specific issues listed."
                fix_user = f"{fix_prompt}\n\nCurrent HTML:\n```html\n{code_html[:60000]}\n```"
                
                qa_fix_input = f"[SYSTEM]\n{fix_system}\n\n[USER]\n{fix_user}"
                if build_model.startswith("gemini"):
                    # Use Google genai SDK for Gemini (NOT OpenAI client — causes 404)
                    from google import genai as google_genai
                    from google.genai import types as genai_types
                    gemini_client = google_genai.Client()
                    gemini_model_id = PINNED_MODELS.get("gemini-3.1-pro-preview", "gemini-3.1-pro-preview")
                    gemini_max = max_output_for(gemini_model_id)
                    with tracer.generation(
                        name=f"qa_fix_{i}_gemini",
                        model=gemini_model_id,
                        input=qa_fix_input,
                        model_parameters={"max_output_tokens": gemini_max},
                        metadata={"phase": "qa_fix", "build_index": i,
                                   "build_model": build_model,
                                   "preserved_assets": len(preserved_assets)},
                    ) as gen:
                        gemini_response = gemini_client.models.generate_content(
                            model=gemini_model_id,
                            contents=[genai_types.Part.from_text(text=f"{fix_system}\n\n{fix_user}")],
                            config=genai_types.GenerateContentConfig(max_output_tokens=gemini_max),
                        )
                        fixed_html = ""
                        for part in gemini_response.candidates[0].content.parts:
                            if hasattr(part, 'text') and part.text:
                                fixed_html += part.text
                        gen.set_output(fixed_html[:5000])
                        # Gemini SDK doesn't always expose usage; estimate from chars
                        gen.set_usage(
                            input_tokens=estimate_tokens(qa_fix_input),
                            output_tokens=estimate_tokens(fixed_html),
                            estimated=True,
                        )
                else:
                    # OpenAI API for GPT models
                    gpt_model_id = PINNED_MODELS.get("gpt-5.4", "gpt-5.4")
                    gpt_max = max_output_for(gpt_model_id)
                    with tracer.generation(
                        name=f"qa_fix_{i}_gpt",
                        model=gpt_model_id,
                        input=qa_fix_input,
                        model_parameters={"max_completion_tokens": gpt_max},
                        metadata={"phase": "qa_fix", "build_index": i,
                                   "build_model": build_model,
                                   "preserved_assets": len(preserved_assets)},
                    ) as gen:
                        fix_response = openai_client.chat.completions.create(
                            model=gpt_model_id,
                            max_completion_tokens=gpt_max,
                            messages=[
                                {"role": "system", "content": fix_system},
                                {"role": "user", "content": fix_user},
                            ],
                        )
                        fixed_html = fix_response.choices[0].message.content
                        gen.set_output(fixed_html[:5000])
                        if fix_response.usage:
                            gen.set_usage(
                                input_tokens=fix_response.usage.prompt_tokens,
                                output_tokens=fix_response.usage.completion_tokens,
                            )
                
                # Extract HTML from markdown code block if present
                if "```html" in fixed_html:
                    fixed_html = fixed_html.split("```html")[1].split("```")[0]
                elif "```" in fixed_html:
                    fixed_html = fixed_html.split("```")[1].split("```")[0]
                
                # Re-inject preserved base64 assets
                if preserved_assets:
                    for key, asset_data in preserved_assets.items():
                        if key in fixed_html:
                            fixed_html = fixed_html.replace(key, asset_data)
                        else:
                            # Fix model dropped the placeholder — asset lost
                            print(f"    ⚠️  [qa-fix] Asset placeholder {key[:30]}... not found in fixed HTML — asset may be lost")
                    
                    fixed_size = len(fixed_html)
                    if fixed_size < html_size * 0.5:
                        # Fix model gutted the file — reject the fix, keep original
                        print(f"    ❌ [qa-fix] Fix reduced file from {html_size//1024}KB to {fixed_size//1024}KB (>50% loss) — keeping original")
                        fixed_html = html_content  # Restore original
                    else:
                        print(f"    [qa-fix] Re-injected {len(preserved_assets)} assets ({fixed_size//1024}KB)")
                
                build_path.write_text(fixed_html)
            except Exception as e:
                print(f"  ⚠️  Fix failed for {report['build']}: {e}")
        else:
            run_hermes(f"{state['name']}-qa-fix-{i}", fix_prompt, max_time=600, max_turns=20)
        
        report["fix_attempts"] += 1
        
        # Re-run experience checks on fixed build
        if browser:
            try:
                page = browser.new_page(viewport={"width": 1080, "height": 1920})
                page.goto(f"file://{build_path.resolve()}", wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(2000)
                ss_fixed = screenshot_dir / f"{report['build']}-fixed.png"
                page.screenshot(path=str(ss_fixed), full_page=False)
                
                render_ok = _check_render(str(ss_fixed))
                if render_ok:
                    report["verdict"] = "PASS"
                    report["issues"] = [f"(fixed) {i}" for i in report["issues"]]
                    print(f"  ✅ {report['build']}: PASS after fix")
                else:
                    print(f"  ⚠️  {report['build']}: still failing after fix")
                
                page.close()
            except Exception as e:
                print(f"  ⚠️  Re-check failed: {e}")
    
    # Clean up browser
    if browser:
        browser.close()
    if pw:
        pw.stop()
    
    # Summary
    passed = sum(1 for r in qa_reports if r["verdict"] == "PASS")
    fixable = sum(1 for r in qa_reports if r["verdict"] == "FIXABLE")
    broken = sum(1 for r in qa_reports if r["verdict"] == "BROKEN")
    print(f"[QA] Results: {passed} PASS, {fixable} FIXABLE, {broken} BROKEN")
    
    # Save summary report
    summary = {
        "total": len(qa_reports),
        "passed": passed,
        "fixable": fixable, 
        "broken": broken,
        "reports": qa_reports,
    }
    with open(qa_dir / "qa-summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    
    tracer.end_span(span, output={"passed": passed, "fixable": fixable, "broken": broken})
    
    return {
        "qa_reports": qa_reports,
        "phase": "qa_complete",
    }


def _extract_sample_items(brief: str) -> list:
    """Extract sample data items from the brief's ## Sample Data section."""
    items = []
    in_sample = False
    for line in brief.split("\n"):
        if "## Sample Data" in line or "## sample data" in line.lower():
            in_sample = True
            continue
        if in_sample:
            if line.startswith("## "):
                break
            # Look for numbered items like "1. Air Jordan 1 Retro High OG"
            if line.strip() and (line.strip()[0].isdigit() or line.strip().startswith("-")):
                # Extract the item name (strip number and punctuation prefix)
                item = line.strip().lstrip("0123456789.-) ").strip()
                if item and len(item) > 3:
                    items.append(item)
    return items


def _check_render(screenshot_path: str) -> bool:
    """Check if a screenshot is non-blank by measuring pixel variance."""
    try:
        # Use sips to get image info (macOS) or PIL
        import struct
        with open(screenshot_path, "rb") as f:
            data = f.read()
        # Simple check: file size > 50KB usually means real content
        # Blank PNGs at 1080x1920 compress to ~5-15KB
        return len(data) > 50000
    except Exception:
        return False


def _compare_screenshots(path1: str, path2: str) -> float:
    """Compare two screenshots and return % difference (0-100)."""
    try:
        with open(path1, "rb") as f1, open(path2, "rb") as f2:
            data1, data2 = f1.read(), f2.read()
        if len(data1) == 0 or len(data2) == 0:
            return 0.0
        # Quick byte-level comparison
        min_len = min(len(data1), len(data2))
        diff_bytes = sum(1 for i in range(0, min_len, 100) if data1[i] != data2[i])
        total_samples = min_len // 100
        return (diff_bytes / max(total_samples, 1)) * 100
    except Exception:
        return 0.0


def screenshot_builds(builds: list, run_name: str) -> list:
    """Screenshot each build at 1080x1920 using Playwright. Returns list of single paths (initial state).

    Kept for backward compatibility. Prefer walk_builds() for journey-aware capture.
    """
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


# ──────────────────────────────────────────────────────────────────────────
# Experience Walker: generic, brief-agnostic interactive QA + journey capture
# ──────────────────────────────────────────────────────────────────────────

WALKER_MAX_STEPS = 25            # Hard ceiling on clicks per build
WALKER_MAX_SCREENSHOTS = 8       # Cap on screenshots passed to judge per build
WALKER_STABILIZE_MS = 1800       # Settle time after each click (covers most CSS transitions and dialogue typing)
WALKER_INITIAL_SETTLE_MS = 2500  # Settle time after page load (fonts/anim/intro)


def _walker_discover_interactive_js() -> str:
    """JS that returns a JSON-able list of currently visible, clickable elements.

    Heuristics: native <button>/<a>, role=button/link/menuitem, [onclick],
    cursor:pointer on visible elements. Each entry includes a stable-ish selector
    candidate (tag, id, classes, position-in-DOM), label text, and bounding box.
    """
    return r"""
    (() => {
      const isVisible = (el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) return false;
        const s = getComputedStyle(el);
        if (s.visibility === 'hidden' || s.display === 'none' || parseFloat(s.opacity) < 0.05) return false;
        if (r.bottom < 0 || r.top > window.innerHeight) return false;
        return true;
      };
      const isClickable = (el) => {
        const tag = el.tagName.toLowerCase();
        if (['button','a','input','select','summary','label'].includes(tag)) return true;
        const role = (el.getAttribute('role') || '').toLowerCase();
        if (['button','link','menuitem','tab','option','switch','checkbox','radio'].includes(role)) return true;
        if (el.hasAttribute('onclick')) return true;
        if (el.hasAttribute('data-action') || el.hasAttribute('data-click') || el.hasAttribute('data-route')) return true;
        const cs = getComputedStyle(el);
        if (cs.cursor === 'pointer') return true;
        return false;
      };
      const labelFor = (el) => {
        const aria = el.getAttribute('aria-label');
        if (aria) return aria.trim().slice(0, 80);
        const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
        if (text) return text.slice(0, 80);
        const alt = el.getAttribute('alt') || el.getAttribute('title');
        if (alt) return alt.trim().slice(0, 80);
        return el.tagName.toLowerCase();
      };
      const selectorFor = (el) => {
        if (el.id) return '#' + CSS.escape(el.id);
        // build a path-ish selector
        const parts = [];
        let node = el;
        while (node && node.nodeType === 1 && parts.length < 6) {
          let part = node.tagName.toLowerCase();
          if (node.classList.length) {
            const cls = Array.from(node.classList).slice(0, 2).map(c => '.' + CSS.escape(c)).join('');
            part += cls;
          }
          const parent = node.parentElement;
          if (parent) {
            const sibs = Array.from(parent.children).filter(c => c.tagName === node.tagName);
            if (sibs.length > 1) {
              part += `:nth-of-type(${sibs.indexOf(node) + 1})`;
            }
          }
          parts.unshift(part);
          node = node.parentElement;
        }
        return parts.join(' > ');
      };
      const all = Array.from(document.querySelectorAll('*'));
      const seen = new Set();
      const out = [];
      for (const el of all) {
        if (!isVisible(el) || !isClickable(el)) continue;
        // skip children when parent is already clickable (avoid double-counting)
        let parent = el.parentElement;
        let parentClickable = false;
        while (parent) {
          if (isClickable(parent) && isVisible(parent)) { parentClickable = true; break; }
          parent = parent.parentElement;
        }
        if (parentClickable) continue;
        const sel = selectorFor(el);
        if (seen.has(sel)) continue;
        seen.add(sel);
        const r = el.getBoundingClientRect();
        out.push({
          selector: sel,
          label: labelFor(el),
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute('role') || '',
          x: Math.round(r.left + r.width / 2),
          y: Math.round(r.top + r.height / 2),
          area: Math.round(r.width * r.height),
        });
      }
      // sort by area descending (favor large CTAs first)
      out.sort((a, b) => b.area - a.area);
      return out.slice(0, 40);
    })()
    """


def _walker_state_hash(page) -> str:
    """Hash the visible DOM + visible text to detect 'did clicking change something'."""
    import hashlib
    snap = page.evaluate(r"""
    (() => {
      const visText = (document.body && document.body.innerText) ? document.body.innerText.slice(0, 4000) : '';
      const visEls = document.querySelectorAll('body *');
      let visibleCount = 0;
      for (const el of visEls) {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        if (r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05) {
          visibleCount++;
        }
      }
      return JSON.stringify({
        url: location.href,
        hash: location.hash,
        text: visText,
        visibleCount,
        title: document.title,
      });
    })()
    """)
    return hashlib.sha256(snap.encode("utf-8")).hexdigest()[:16]


def walk_experience(build_path: Path, screenshot_dir: Path, build_id: str,
                    max_steps: int = WALKER_MAX_STEPS) -> dict:
    """Walk an HTML prototype by clicking interactive elements BFS-style.

    Generic — no run-specific logic. Returns:
        {
          'steps': [
            {'index', 'screenshot', 'state_hash', 'clicked_label',
             'clicked_selector', 'state_changed', 'console_errors'}
          ],
          'unique_states': int,
          'interactive_elements_found': int,
          'clicks_attempted': int,
          'clicks_that_changed_state': int,
          'console_errors_total': int,
          'dead_prototype': bool,        # found buttons but none worked
          'inert_prototype': bool,       # no clickable elements at all
          'render_ok': bool,
          'walker_error': str | None,
        }
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "steps": [],
        "unique_states": 0,
        "interactive_elements_found": 0,
        "clicks_attempted": 0,
        "clicks_that_changed_state": 0,
        "console_errors_total": 0,
        "dead_prototype": False,
        "inert_prototype": False,
        "render_ok": False,
        "walker_error": None,
    }

    seen_states: set = set()
    console_errors: list = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            try:
                page.goto(f"file://{build_path.resolve()}", wait_until="networkidle", timeout=15000)
            except PWTimeout:
                # Some prototypes never reach networkidle (running animations). Fall back to load.
                try:
                    page.goto(f"file://{build_path.resolve()}", wait_until="load", timeout=10000)
                except Exception as e:
                    result["walker_error"] = f"goto failed: {e}"
                    browser.close()
                    return result
            page.wait_for_timeout(WALKER_INITIAL_SETTLE_MS)

            # Initial screenshot
            initial_path = screenshot_dir / f"{build_id}-step-00.png"
            page.screenshot(path=str(initial_path), full_page=False)
            initial_hash = _walker_state_hash(page)
            seen_states.add(initial_hash)
            result["render_ok"] = _check_render(str(initial_path))
            result["steps"].append({
                "index": 0,
                "screenshot": str(initial_path),
                "state_hash": initial_hash,
                "clicked_label": None,
                "clicked_selector": None,
                "state_changed": None,
                "console_errors": list(console_errors),
            })

            # BFS queue of (selector, label) to click
            # On each new state, re-discover interactive elements and append new ones
            queue: list = []
            visited_selectors: set = set()

            def refill_queue():
                try:
                    elements = page.evaluate(_walker_discover_interactive_js())
                except Exception:
                    elements = []
                result["interactive_elements_found"] = max(
                    result["interactive_elements_found"], len(elements)
                )
                for el in elements:
                    key = el.get("selector", "") + "::" + el.get("label", "")
                    if key in visited_selectors:
                        continue
                    visited_selectors.add(key)
                    queue.append(el)

            refill_queue()

            if not queue:
                result["inert_prototype"] = True

            step_idx = 0
            while queue and step_idx < max_steps:
                step_idx += 1
                el = queue.pop(0)
                selector = el.get("selector", "")
                label = el.get("label", "")
                x = el.get("x", 0)
                y = el.get("y", 0)
                pre_hash = _walker_state_hash(page)
                pre_errors = len(console_errors)

                clicked = False
                # Try selector click first, fall back to coordinate click
                try:
                    handle = page.query_selector(selector)
                    if handle:
                        try:
                            handle.scroll_into_view_if_needed(timeout=1000)
                        except Exception:
                            pass
                        try:
                            handle.click(timeout=2000, force=False)
                            clicked = True
                        except Exception:
                            try:
                                handle.click(timeout=1500, force=True)
                                clicked = True
                            except Exception:
                                clicked = False
                except Exception:
                    clicked = False

                if not clicked:
                    try:
                        page.mouse.click(x, y)
                        clicked = True
                    except Exception:
                        clicked = False

                result["clicks_attempted"] += 1
                page.wait_for_timeout(WALKER_STABILIZE_MS)

                # Dismiss any native alerts/dialogs that may have appeared (best effort)
                try:
                    page.evaluate("() => { if (window.__pwAlertHooked) return; window.__pwAlertHooked = true; window.alert = ()=>{}; window.confirm = ()=>true; window.prompt = ()=>''; }")
                except Exception:
                    pass

                post_hash = _walker_state_hash(page)
                state_changed = (post_hash != pre_hash)
                if state_changed:
                    result["clicks_that_changed_state"] += 1

                new_errors = console_errors[pre_errors:]
                shot_path = screenshot_dir / f"{build_id}-step-{step_idx:02d}.png"
                try:
                    page.screenshot(path=str(shot_path), full_page=False)
                except Exception as e:
                    result["walker_error"] = f"screenshot at step {step_idx} failed: {e}"
                    break

                result["steps"].append({
                    "index": step_idx,
                    "screenshot": str(shot_path),
                    "state_hash": post_hash,
                    "clicked_label": label,
                    "clicked_selector": selector,
                    "state_changed": state_changed,
                    "console_errors": new_errors,
                })

                if state_changed and post_hash not in seen_states:
                    seen_states.add(post_hash)
                    # Re-discover new clickable elements after navigation/state change
                    refill_queue()

            browser.close()
    except Exception as e:
        result["walker_error"] = f"walker exception: {e}"

    result["unique_states"] = len(seen_states)
    result["console_errors_total"] = len(console_errors)
    # Dead prototype: had interactive elements but none of them changed state
    if (
        result["interactive_elements_found"] > 0
        and result["clicks_attempted"] >= max(2, min(5, result["interactive_elements_found"]))
        and result["clicks_that_changed_state"] == 0
    ):
        result["dead_prototype"] = True

    return result


def _select_journey_screenshots(walk: dict, max_count: int = WALKER_MAX_SCREENSHOTS) -> list:
    """Pick a representative ordered set of screenshots that best summarize the journey.

    Strategy: always include initial; prefer steps that produced a state change;
    pad with evenly-spaced others if needed. Cap at max_count.
    """
    steps = walk.get("steps", [])
    if not steps:
        return []
    initial = steps[0]
    changed = [s for s in steps[1:] if s.get("state_changed")]
    others = [s for s in steps[1:] if not s.get("state_changed")]

    chosen = [initial]
    # Take state-change screenshots, evenly spaced if too many
    if len(changed) <= (max_count - 1):
        chosen.extend(changed)
    else:
        # evenly sample
        step = len(changed) / (max_count - 1)
        chosen.extend([changed[int(i * step)] for i in range(max_count - 1)])
    # If we still have headroom, sprinkle some 'no-change' frames in chronological order
    headroom = max_count - len(chosen)
    if headroom > 0 and others:
        chosen.extend(others[:headroom])
    # Sort chronologically by step index
    chosen = sorted({s["index"]: s for s in chosen}.values(), key=lambda s: s["index"])
    return chosen[:max_count]


def walk_builds(builds: list, run_name: str) -> dict:
    """Walk each build's experience. Returns {build_index: walk_result}."""
    walk_dir = RUNS_DIR / run_name / "walks"
    walk_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for b in builds:
        idx = b["index"]
        build_path = Path(b["path"])
        if not build_path.exists():
            results[idx] = {"walker_error": "build file missing", "steps": [],
                            "render_ok": False, "inert_prototype": True,
                            "dead_prototype": False, "interactive_elements_found": 0,
                            "clicks_attempted": 0, "clicks_that_changed_state": 0,
                            "unique_states": 0, "console_errors_total": 0}
            continue
        build_id = f"concept-{idx}"
        print(f"  🚶 Walking {build_id}...")
        walk = walk_experience(build_path, walk_dir, build_id)
        results[idx] = walk
        # Persist walk summary for debugging
        try:
            summary_path = walk_dir / f"{build_id}-walk.json"
            summary = {
                "build_id": build_id,
                "interactive_elements_found": walk["interactive_elements_found"],
                "clicks_attempted": walk["clicks_attempted"],
                "clicks_that_changed_state": walk["clicks_that_changed_state"],
                "unique_states": walk["unique_states"],
                "console_errors_total": walk["console_errors_total"],
                "dead_prototype": walk["dead_prototype"],
                "inert_prototype": walk["inert_prototype"],
                "render_ok": walk["render_ok"],
                "walker_error": walk["walker_error"],
                "steps": [
                    {k: v for k, v in s.items() if k != "console_errors"}
                    for s in walk["steps"]
                ],
            }
            summary_path.write_text(json.dumps(summary, indent=2))
        except Exception:
            pass
        print(f"     · {walk['interactive_elements_found']} interactive elements, "
              f"{walk['clicks_attempted']} clicks attempted, "
              f"{walk['clicks_that_changed_state']} produced state changes, "
              f"{walk['unique_states']} unique states"
              + ("  ⚠️ DEAD" if walk['dead_prototype'] else "")
              + ("  ⚠️ INERT" if walk['inert_prototype'] else ""))
    return results


def encode_image(path: str) -> str:
    """Read image and return base64 string."""
    import base64
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Playability Loop: post-QA, pre-judge surgical-patch loop
#
# For each build that QA did not flag BROKEN, scan completion signals (walker +
# DOM-text regex) and, if the experience isn't end-to-end playable, ask Claude
# Opus 4.7 for a single <script> patch that gets appended to the file. Repeat
# up to MAX_PLAYABILITY_ITERATIONS per build. Pre-judge so the judge sees
# playable builds. See wiki/builds/playability-loop.md.
# ──────────────────────────────────────────────────────────────────────────

import re as _re
import shutil as _shutil


def _playability_extract_code_chunks(html: str, max_chars: int = PLAYABILITY_CODE_MAX_CHARS) -> str:
    """Pull <script> blocks + button markup, stripping base64 assets.

    Lifted from iterate-playability.py. Avoids shipping 15MB asset blobs to
    the patch model.
    """
    stripped = _re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+",
                       "data:image/png;base64,[ASSET]", html)
    parts = []
    for m in _re.finditer(r"<script[^>]*>(.*?)</script>", stripped, _re.DOTALL):
        parts.append(("SCRIPT", m.group(0)))
    button_blocks = _re.findall(r"<button[^>]*>[^<]{0,200}</button>", stripped)
    for b in button_blocks[:50]:
        parts.append(("BUTTON", b))
    out_lines = []
    for kind, block in parts:
        if kind == "BUTTON":
            out_lines.append(f"// {kind}: {block}")
        else:
            out_lines.append(f"// {kind} (start) ---")
            out_lines.append(block)
            out_lines.append(f"// {kind} (end) ---")
    out = "\n".join(out_lines)
    if len(out) > max_chars:
        half = max_chars // 2
        out = out[:half] + "\n\n// ... [middle truncated] ...\n\n" + out[-half:]
    return out


def _playability_infer_requirements(brief: str) -> dict:
    """Best-effort extraction of end-to-end completion requirements from the brief.

    Returns:
        {
          'min_rounds': int,          # default PLAYABILITY_MIN_ROUNDS
          'needs_performance': bool,  # "reveal/performance/results" required
          'needs_share': bool,        # share-card required
          'is_multistep': bool,       # heuristic: brief talks about rounds/steps/screens
        }
    """
    brief_lower = (brief or "").lower()

    # Try to find "N rounds" / "N customers" / "N steps" markers
    min_rounds = PLAYABILITY_MIN_ROUNDS
    m = _re.search(r"(\d+)\s*(rounds?|customers?|steps?|levels?|screens?|questions?)", brief_lower)
    if m:
        try:
            candidate = int(m.group(1))
            if 2 <= candidate <= 20:
                min_rounds = candidate
        except Exception:
            pass

    needs_performance = any(k in brief_lower for k in [
        "performance reveal", "results screen", "score reveal", "total profit",
        "final score", "game over", "p&l", "end-of-game", "end of game",
        "reveal screen", "performance screen",
    ])
    needs_share = any(k in brief_lower for k in [
        "share card", "share-card", "shareable", "share button",
        "copy link", "shareable card", "share result", "social card",
    ])
    is_multistep = bool(m) or any(k in brief_lower for k in [
        "round", "multi-step", "multi-screen", "flow through", "each customer",
        "game", "quiz", "questions",
    ])

    return {
        "min_rounds": min_rounds,
        "needs_performance": needs_performance,
        "needs_share": needs_share,
        "is_multistep": is_multistep,
    }


_PLAYABILITY_PERF_REGEX = _re.compile(
    r"(total profit|performance|final score|p&?l|net flip|game over|results)",
    _re.I,
)
_PLAYABILITY_SHARE_REGEX = _re.compile(
    r"(share|copy.*link|share card|tweet|social|instagram)", _re.I,
)
_PLAYABILITY_ROUND_REGEX = _re.compile(
    r"(?:round|customer|question|step|level)\s*([0-9]+)\s*(?:/|of)\s*([0-9]+)", _re.I,
)


def _playability_signals_from_walk(walk: dict, requirements: dict) -> dict:
    """Aggregate completion signals from an existing walker result.

    We re-scan every captured step's visible-text-equivalent (walker stores
    `state_hash` but not the raw text; we rely on the walker having visited
    states. The walker writes screenshots but not raw text snapshots, so the
    most reliable signals are from the step click labels + the walker's
    `unique_states` + `clicks_that_changed_state` counters).

    Then we layer on a fresh DOM-text scan via Playwright (similar to
    iterate-playability.py) to catch round/perf/share markers we couldn't see
    in the cached walk.
    """
    signals = {
        "max_round_seen": 0,
        "required_rounds": requirements.get("min_rounds", PLAYABILITY_MIN_ROUNDS),
        "reaches_performance": False,
        "reaches_share_card": False,
        "walked_states": walk.get("unique_states", 0),
        "clicks_that_changed_state": walk.get("clicks_that_changed_state", 0),
        "console_errors": [],
        "console_errors_total": walk.get("console_errors_total", 0),
        "dead_prototype": walk.get("dead_prototype", False),
        "inert_prototype": walk.get("inert_prototype", False),
        "render_ok": walk.get("render_ok", False),
        "walker_error": walk.get("walker_error"),
    }
    # Look at step click labels for round-progression hints (rough heuristic;
    # the real signal comes from the DOM scan below).
    for step in walk.get("steps", []):
        for err in step.get("console_errors", []) or []:
            if err and err not in signals["console_errors"]:
                signals["console_errors"].append(err)
        label = step.get("clicked_label") or ""
        m = _PLAYABILITY_ROUND_REGEX.search(label)
        if m:
            try:
                signals["max_round_seen"] = max(signals["max_round_seen"], int(m.group(1)))
            except Exception:
                pass
        if _PLAYABILITY_PERF_REGEX.search(label):
            signals["reaches_performance"] = True
        if _PLAYABILITY_SHARE_REGEX.search(label):
            signals["reaches_share_card"] = True
    signals["console_errors"] = signals["console_errors"][:10]
    return signals


def _playability_scan_dom_signals(build_path: Path, requirements: dict) -> dict:
    """Re-render the build and scan visible text for completion markers.

    Reuses the same scanning pattern as iterate-playability.py — clicks the
    largest-area visible clickable element repeatedly, tracks the highest
    "round N/M" + presence of perf/share keywords in visible body text.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    import hashlib

    signals = {
        "max_round_seen": 0,
        "required_rounds": requirements.get("min_rounds", PLAYABILITY_MIN_ROUNDS),
        "reaches_performance": False,
        "reaches_share_card": False,
        "walked_states": 0,
        "console_errors": [],
        "playable_path_len": 0,
    }

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            try:
                page.goto(f"file://{build_path.resolve()}", wait_until="networkidle", timeout=15000)
            except PWTimeout:
                page.goto(f"file://{build_path.resolve()}", wait_until="load", timeout=10000)
            page.wait_for_timeout(WALKER_INITIAL_SETTLE_MS)

            visited_hashes = set()
            for _step in range(40):
                visible_text = page.evaluate("() => (document.body && document.body.innerText) || ''")
                m = _PLAYABILITY_ROUND_REGEX.search(visible_text)
                if m:
                    try:
                        signals["max_round_seen"] = max(signals["max_round_seen"], int(m.group(1)))
                    except Exception:
                        pass
                if _PLAYABILITY_PERF_REGEX.search(visible_text):
                    signals["reaches_performance"] = True
                if _PLAYABILITY_SHARE_REGEX.search(visible_text):
                    signals["reaches_share_card"] = True

                h = hashlib.sha256(visible_text.encode("utf-8")).hexdigest()[:12]
                visited_hashes.add(h)

                elements = page.evaluate(r"""
                () => {
                  const isVis = el => {
                    const r = el.getBoundingClientRect();
                    if (r.width < 4 || r.height < 4) return false;
                    const s = getComputedStyle(el);
                    return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05;
                  };
                  const clickable = el => {
                    const t = el.tagName.toLowerCase();
                    if (['button','a','input','select','label','summary'].includes(t)) return true;
                    const r = (el.getAttribute('role')||'').toLowerCase();
                    if (['button','link','menuitem','tab','option','switch','checkbox','radio'].includes(r)) return true;
                    if (el.hasAttribute('onclick')) return true;
                    return getComputedStyle(el).cursor === 'pointer';
                  };
                  const all = Array.from(document.querySelectorAll('*'));
                  const out = [];
                  for (const el of all) {
                    if (!isVis(el) || !clickable(el)) continue;
                    let p = el.parentElement;
                    let parentClick = false;
                    while (p) { if (clickable(p) && isVis(p)) { parentClick = true; break; } p = p.parentElement; }
                    if (parentClick) continue;
                    const r = el.getBoundingClientRect();
                    out.push({
                      x: Math.round(r.left + r.width/2),
                      y: Math.round(r.top + r.height/2),
                      area: r.width * r.height,
                      label: (el.innerText || el.textContent || el.tagName).slice(0, 60).trim(),
                    });
                  }
                  out.sort((a,b)=>b.area-a.area);
                  return out.slice(0, 20);
                }
                """)
                if not elements:
                    break
                clicked = False
                for el in elements:
                    try:
                        page.mouse.click(el["x"], el["y"])
                        page.wait_for_timeout(1500)
                        new_text = page.evaluate("() => (document.body && document.body.innerText) || ''")
                        new_h = hashlib.sha256(new_text.encode("utf-8")).hexdigest()[:12]
                        if new_h not in visited_hashes:
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    break

            signals["walked_states"] = len(visited_hashes)
            signals["console_errors"] = errors[:10]
            signals["playable_path_len"] = signals["walked_states"]
            browser.close()
    except Exception as e:
        signals["scan_error"] = str(e)

    return signals


def _playability_merge_signals(walk_signals: dict, dom_signals: dict) -> dict:
    """Merge walker-cached signals with a fresh DOM scan, keeping max values."""
    merged = dict(walk_signals)
    merged["max_round_seen"] = max(
        walk_signals.get("max_round_seen", 0),
        dom_signals.get("max_round_seen", 0),
    )
    merged["reaches_performance"] = (
        walk_signals.get("reaches_performance", False)
        or dom_signals.get("reaches_performance", False)
    )
    merged["reaches_share_card"] = (
        walk_signals.get("reaches_share_card", False)
        or dom_signals.get("reaches_share_card", False)
    )
    merged["walked_states"] = max(
        walk_signals.get("walked_states", 0),
        dom_signals.get("walked_states", 0),
    )
    seen_errs = list(walk_signals.get("console_errors") or [])
    for e in dom_signals.get("console_errors") or []:
        if e and e not in seen_errs:
            seen_errs.append(e)
    merged["console_errors"] = seen_errs[:10]
    if dom_signals.get("scan_error"):
        merged["scan_error"] = dom_signals["scan_error"]
    merged["playable_path_len"] = dom_signals.get("playable_path_len", merged.get("walked_states", 0))
    return merged


def _playability_is_complete(signals: dict, requirements: dict) -> bool:
    """Decide whether the build looks end-to-end playable.

    For multi-step experiences we require: reach min_rounds AND, if the brief
    asks for them, performance + share. For non-multi-step artifacts (static
    share cards, posters) the loop is a no-op (caller should skip).
    """
    if not requirements.get("is_multistep"):
        # Nothing to verify — treat as already complete.
        return True
    min_rounds = requirements.get("min_rounds", PLAYABILITY_MIN_ROUNDS)
    if signals.get("max_round_seen", 0) < min_rounds:
        return False
    if requirements.get("needs_performance") and not signals.get("reaches_performance", False):
        return False
    if requirements.get("needs_share") and not signals.get("reaches_share_card", False):
        return False
    return True


def _playability_gap_summary(signals: dict, requirements: dict) -> str:
    gaps = []
    rounds = signals.get("max_round_seen", 0)
    min_rounds = requirements.get("min_rounds", PLAYABILITY_MIN_ROUNDS)
    if rounds < min_rounds:
        gaps.append(f"Only reaches round {rounds}/{min_rounds}.")
    if requirements.get("needs_performance") and not signals.get("reaches_performance"):
        gaps.append("Never reaches the end-of-experience PERFORMANCE/RESULTS REVEAL screen (no 'total profit'/'P&L'/'results' text found).")
    if requirements.get("needs_share") and not signals.get("reaches_share_card"):
        gaps.append("Never reaches the SHARE CARD screen (no 'share'/'copy link' text found).")
    if signals.get("console_errors"):
        gaps.append(f"Console errors present: {signals['console_errors'][:3]}")
    if not gaps:
        gaps.append("Build is end-to-end complete.")
    return " ".join(gaps)


def _playability_build_patch_prompt(brief_text: str, signals: dict, requirements: dict,
                                    concept_index: int, code_context: str,
                                    iteration: int, max_iter: int,
                                    approach_doc: str = "") -> tuple[str, str]:
    """Build the playability-continuation prompt anchored to the ORIGINAL approach doc.

    The approach doc is the creative anchor that keeps each concept's voice intact
    across the playability patch — different builders (Opus / GPT-5 / Gemini) keep
    their distinct directions instead of converging on a generic UI.
    """
    gaps = _playability_gap_summary(signals, requirements)
    min_rounds = requirements.get("min_rounds", PLAYABILITY_MIN_ROUNDS)
    need_perf = requirements.get("needs_performance", False)
    need_share = requirements.get("needs_share", False)

    completion_clauses = [f"all {min_rounds} rounds (each as a distinct screen with its own content)"]
    if need_perf:
        completion_clauses.append("the end-of-experience PERFORMANCE / RESULTS REVEAL screen")
    if need_share:
        completion_clauses.append("the SHAREABLE CARD screen with a visible 'Share' or 'Copy Link' button")
    completion_sentence = "intro → " + " → ".join(completion_clauses)

    system = (
        "You are the original builder of this concept, continuing your work.\n\n"
        "You wrote an approach doc describing the creative direction, palette, mechanics,"
        " and tone you committed to. Continue building this experience in the SAME voice.\n\n"
        "Your job is to make the user reach the end of the experience. The build is partially"
        " complete; some screens or flow logic was not finished in the initial pass. Build the"
        f" missing pieces in your original creative voice so the user can travel through {completion_sentence}.\n\n"
        "OUTPUT FORMAT:"
        "\n- Output ONLY a single <script>...</script> block. No markdown fences. No explanation. No <html>/<body>/<head>."
        "\n- It will be appended to the file right before </body> and runs AFTER all existing code."
        "\n- Reference existing functions/variables where they exist; define new ones if needed."
        "\n- Use vanilla JS only. No frameworks. No imports."
        "\n- Guard with DOMContentLoaded so it runs even if the file has script-loading bugs."
        "\n- If previous patches have already been applied (look for `<!-- AUTO-PATCH:` comments), your new patch must SUPERSEDE them, not duplicate handlers. Wrap your logic in a unique namespace and remove old listeners first."
        + (f"\n- Each round must use distinct content. Hardcode {min_rounds} distinct rounds in your patch if needed." if requirements.get("is_multistep") else "")
        + (f"\n- Add a clear round counter (e.g. 'STEP 1/{min_rounds}') visible at all times so the walker can detect progress." if requirements.get("is_multistep") else "")
        + ("\n- The performance reveal screen MUST contain the text 'TOTAL PROFIT' or 'P&L' or 'PERFORMANCE' or 'RESULTS' so it's detectable." if need_perf else "")
        + ("\n- The share card screen MUST contain a 'Share' or 'Copy Link' or 'Share Result' button." if need_share else "")
        + "\n\nStay true to your approach doc. The patcher is free to refactor broken state machines or add missing screens — what it shouldn't do is redesign in a generic style. The approach doc is your creative anchor; trust it."
    )

    approach_block = (approach_doc[:8000] if approach_doc else "(approach doc unavailable — stay true to the existing code's style)")

    user = f"""## YOUR ORIGINAL APPROACH DOC (concept-{concept_index}) — creative anchor
{approach_block}

## BRIEF CONTEXT
{brief_text[:4000]}

## ITERATION {iteration}/{max_iter}

## DIAGNOSIS FROM AUTOMATED WALKER (what's still missing/broken)
{gaps}

Telemetry:
- max round seen: {signals.get('max_round_seen', 0)}/{min_rounds}
- reaches performance reveal: {signals.get('reaches_performance', False)}
- reaches share card: {signals.get('reaches_share_card', False)}
- distinct visible states reached: {signals.get('walked_states', 0)}
- console errors (up to 3): {signals.get('console_errors', [])[:3]}

## CURRENT BUILD (code chunks, base64 assets stripped to placeholders)
{code_context}

## YOUR TASK
Write a single <script> block that completes the unbuilt portions of this experience in your original creative voice. Focus on closing the gaps identified above. Stay true to your approach doc — same palette, same mechanics, same tone. The end goal is a user can click through {completion_sentence}.
"""
    return system, user


def _playability_apply_patch(html: str, patch_text: str) -> str:
    """Append a patch <script> block right before </body>. Never rewrites the file."""
    patch = patch_text.strip()
    if "```html" in patch:
        patch = patch.split("```html", 1)[1].split("```", 1)[0]
    elif "```" in patch:
        patch = _re.sub(r"```[a-zA-Z]*\n?", "", patch)
        patch = patch.replace("```", "")
    patch = patch.strip()
    if "<script" not in patch.lower():
        patch = f"<script>\n{patch}\n</script>"

    marker = f"\n<!-- AUTO-PATCH: iter {time.strftime('%H:%M:%S')} -->\n"
    if "</body>" in html:
        return html.replace("</body>", f"{marker}{patch}\n</body>", 1)
    return html + f"{marker}{patch}\n"


def _sync_eval_builds(run_dir: Path, indices: list) -> None:
    """Mirror builds/concept-N.html into eval/builds so the eval app sees patched files."""
    eval_builds = run_dir / "eval" / "builds"
    if not eval_builds.exists():
        return
    for idx in indices:
        src = run_dir / "builds" / f"concept-{idx}.html"
        dst = eval_builds / f"concept-{idx}.html"
        if src.exists():
            try:
                _shutil.copy(src, dst)
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────────
# Unified-builder playability runner
#
# This replaces the legacy `playability_loop_node`. Each non-BROKEN build now
# routes back through `builder_node` in playability mode via parallel fan-out
# (`fan_out_playability_mode`). The per-build playability work happens inside
# `_builder_playability_run`, which is called from `builder_node` when
# state["builder_mode"] == "playability".
#
# Key invariants:
#   - Each concept's patches are made by its ORIGINAL builder model
#     (Opus → Opus build, GPT-5 → GPT-5, Gemini → Gemini). The model is
#     pulled from build["model"] (set during the initial builder pass).
#   - Each playability call has the original approach doc as creative anchor.
#   - Phase metadata is "playability" so cost rollups separate cleanly from
#     the initial builder pass.
#   - The walker + signal-scan + prompt-build + patch-apply helpers
#     (`_playability_*`) are reused as-is; only the loop wrapper changed.
# ──────────────────────────────────────────────────────────────────────────


def _build_for_index(builds: list, idx: int) -> Optional[dict]:
    """Find the build dict for a given build_index in state["builds"]."""
    for b in builds:
        if b.get("index") == idx:
            return b
    return None


def _approach_for_designer(approaches: list, designer_id) -> Optional[dict]:
    """Find the approach dict for a given designer_id."""
    for a in approaches:
        if a.get("designer_id") == designer_id:
            return a
    return None


def _call_playability_patch_model(model: str, system: str, user: str,
                                  max_tokens: int, gen) -> tuple[str, dict]:
    """Call the appropriate frontier provider for the playability patch.

    Routes by model family to mirror builder_node's initial-build routing:
      - claude-* → Anthropic streaming (preserves the old loop's streaming UX)
      - gpt-*    → OpenAI sync chat completion
      - gemini-* → Google GenAI sync generate_content

    Returns (patch_text, usage_dict). Tracks cost under phase="playability".
    """
    resolved = resolve_model(model)
    patch_text = ""
    usage = {"input": 0, "output": 0}

    if resolved.startswith("claude"):
        # Streaming Anthropic call — same pattern as the legacy loop.
        parts = []
        with anthropic_client.messages.stream(
            model=resolved,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for chunk in stream.text_stream:
                parts.append(chunk)
            final_resp = stream.get_final_message()
        patch_text = "".join(parts)
        if getattr(final_resp, "usage", None):
            usage["input"] = getattr(final_resp.usage, "input_tokens", 0) or 0
            usage["output"] = getattr(final_resp.usage, "output_tokens", 0) or 0
        track_cost(resolved, usage["input"], usage["output"], "playability")
    elif resolved.startswith("gpt"):
        # Combine system + user since OpenAI chat lacks a separate "system"
        # parameter idiom in this codebase's existing usage pattern.
        response = openai_client.chat.completions.create(
            model=resolved,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        patch_text = response.choices[0].message.content or ""
        if response.usage:
            usage["input"] = response.usage.prompt_tokens or 0
            usage["output"] = response.usage.completion_tokens or 0
            track_cost(resolved, usage["input"], usage["output"], "playability")
    elif resolved.startswith("gemini"):
        from google import genai as google_genai
        gemini_client = google_genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
        response = gemini_client.models.generate_content(
            model=resolved,
            contents=f"{system}\n\n---\n\n{user}",
            config={"max_output_tokens": max_tokens},
        )
        patch_text = response.text or ""
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage["input"] = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            usage["output"] = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
            track_cost(resolved, usage["input"], usage["output"], "playability")
    else:
        raise RuntimeError(f"Unknown model family for playability patch: {model} (resolved={resolved})")

    if usage["input"] or usage["output"]:
        gen.set_usage(input_tokens=usage["input"], output_tokens=usage["output"])
    gen.set_output(patch_text)
    return patch_text, usage


def _builder_playability_run(state: dict) -> dict:
    """Playability-mode branch of the unified builder_node.

    Runs the surgical-patch loop for a single build (the one identified by
    state["build_index"]) in the SAME model voice as its initial build. Returns
    state updates for the playability_* dict fields plus a routing signal.
    """
    idx = state["build_index"]
    builds = state.get("builds", []) or []
    build = _build_for_index(builds, idx)
    approaches = state.get("approaches", []) or []
    max_iter = state.get("playability_max_iter") or MAX_PLAYABILITY_ITERATIONS
    requirements = _playability_infer_requirements(state.get("brief", ""))

    concept_name = f"concept-{idx}"

    # Routing signal for downstream conditional edges.
    routing = {"builder_mode": "playability"}

    if build is None:
        print(f"[PLAYABILITY {idx}] build dict not found — skipping")
        return {
            **routing,
            "playability_status": {idx: "skipped"},
            "playability_signals": {idx: {"reason": "build_not_found"}},
            "playability_iterations": {idx: 0},
            "playability_patches": {idx: []},
        }

    build_path = Path(build["path"])
    run_dir = RUNS_DIR / state["name"]
    iter_log_dir = run_dir / "iter-logs"
    iter_log_dir.mkdir(parents=True, exist_ok=True)
    walks_dir = run_dir / "walks"
    walks_dir.mkdir(parents=True, exist_ok=True)

    # QA gate: skip BROKEN builds entirely.
    qa_reports = state.get("qa_reports", []) or []
    qa_by_concept = {r.get("build"): r for r in qa_reports}
    qa_report = qa_by_concept.get(concept_name)
    if qa_report and qa_report.get("verdict") == "BROKEN":
        print(f"[PLAYABILITY {idx}] QA verdict BROKEN — skipping playability")
        return {
            **routing,
            "playability_status": {idx: "skipped"},
            "playability_signals": {idx: {"reason": "qa_broken"}},
            "playability_iterations": {idx: 0},
            "playability_patches": {idx: []},
        }

    if not build_path.exists() or build_path.stat().st_size < 500:
        print(f"[PLAYABILITY {idx}] missing/empty build — skipping")
        return {
            **routing,
            "playability_status": {idx: "skipped"},
            "playability_signals": {idx: {"reason": "missing_build"}},
            "playability_iterations": {idx: 0},
            "playability_patches": {idx: []},
        }

    # Short-circuit non-multistep briefs (no rounds/screens to verify).
    if not requirements.get("is_multistep"):
        print(f"[PLAYABILITY {idx}] brief is not multi-step — skipping")
        return {
            **routing,
            "playability_status": {idx: "skipped"},
            "playability_signals": {idx: {"reason": "non_multistep_brief"}},
            "playability_iterations": {idx: 0},
            "playability_patches": {idx: []},
        }

    # Resolve the ORIGINAL builder model for this concept and pull the
    # approach doc to anchor the patch prompt.
    builder_model = (
        state.get("builder_model")
        or build.get("model")
        or "claude-opus"
    )
    approach = _approach_for_designer(approaches, build.get("designer_id"))
    approach_doc = approach.get("content", "") if approach else ""

    print(f"\n[PLAYABILITY {idx}] {concept_name}: continuation in {builder_model} voice "
          f"(up to {max_iter} iter(s), multistep={requirements['is_multistep']}, "
          f"min_rounds={requirements['min_rounds']}, perf={requirements['needs_performance']}, "
          f"share={requirements['needs_share']})")

    span = tracer.start_span(f"builder-{idx}-playability", input={
        "concept": concept_name,
        "model": builder_model,
        "max_iter": max_iter,
        "mode": "playability",
        "requirements": requirements,
    })

    brief_text = state.get("brief", "") or ""
    patch_model_alias = builder_model
    patch_model_resolved = resolve_model(patch_model_alias)
    patch_max_tokens = max_output_for(patch_model_resolved, kind="generation")

    iter_log = {
        "concept": idx,
        "model": builder_model,
        "iterations": [],
        "requirements": requirements,
    }
    final_signals: dict = {}
    patch_entries: list = []
    final_status = "partial"
    iterations_used = 0

    for it in range(1, max_iter + 1):
        iterations_used = it
        iter_span = tracer.start_span(
            f"playability_iter_{idx}_{it}",
            input={"iteration": it, "concept": concept_name, "model": builder_model},
        )
        try:
            # 1. Walk + DOM-scan to refresh signals.
            walk = walk_experience(build_path, walks_dir, f"{concept_name}-iter{it}")
            walk_signals = _playability_signals_from_walk(walk, requirements)
            dom_signals = _playability_scan_dom_signals(build_path, requirements)
            signals = _playability_merge_signals(walk_signals, dom_signals)
            final_signals = signals

            rounds = signals.get("max_round_seen", 0)
            print(f"     iter {it}/{max_iter} [{builder_model}]: rounds={rounds}/{requirements['min_rounds']}, "
                  f"perf={signals.get('reaches_performance')}, share={signals.get('reaches_share_card')}, "
                  f"states={signals.get('walked_states')}, errors={len(signals.get('console_errors', []))}")

            iter_log["iterations"].append({"iter": it, "signals": signals})

            if _playability_is_complete(signals, requirements):
                final_status = "complete"
                print(f"     ✅ end-to-end complete on iteration {it}")
                tracer.end_span(iter_span, output={"complete": True, "signals": signals})
                break

            print(f"     diagnosis: {_playability_gap_summary(signals, requirements)}")

            # 2. Build the patch prompt anchored to the original approach doc.
            html = build_path.read_text(errors="ignore")
            code_ctx = _playability_extract_code_chunks(html, max_chars=PLAYABILITY_CODE_MAX_CHARS)
            system, user = _playability_build_patch_prompt(
                brief_text, signals, requirements, idx, code_ctx, it, max_iter,
                approach_doc=approach_doc,
            )

            with tracer.generation(
                name=f"playability_patch_{idx}_iter{it}_{builder_model}",
                model=patch_model_resolved,
                input=user,
                model_parameters={"max_tokens": patch_max_tokens},
                metadata={
                    "phase": "playability",
                    "concept": idx,
                    "iteration": it,
                    "intended_model": builder_model,
                    "designer_id": build.get("designer_id"),
                },
            ) as gen:
                try:
                    t0 = time.time()
                    patch_text, _usage = _call_playability_patch_model(
                        patch_model_alias, system, user, patch_max_tokens, gen
                    )
                    elapsed = time.time() - t0
                    print(f"     patch returned {len(patch_text)//1024}KB in {elapsed:.1f}s [{builder_model}]")
                except Exception as e:
                    gen.set_error(str(e)[:500])
                    print(f"     ❌ patch generation failed: {e}")
                    iter_log["iterations"][-1]["error"] = str(e)
                    tracer.end_span(iter_span, output={"error": str(e)[:500]})
                    final_status = "failed"
                    break

            if len(patch_text) < PLAYABILITY_PATCH_MIN_BYTES:
                print(f"     ❌ patch too short ({len(patch_text)} bytes) — aborting concept")
                iter_log["iterations"][-1]["error"] = f"patch_too_short:{len(patch_text)}"
                tracer.end_span(iter_span, output={"error": "patch_too_short", "bytes": len(patch_text)})
                final_status = "failed"
                break

            # 3. Apply patch (append-only).
            patched = _playability_apply_patch(html, patch_text)
            backup = build_path.with_suffix(f".pre-playability-iter{it}-{int(time.time())}.html")
            try:
                _shutil.copy(build_path, backup)
            except Exception:
                backup = None
            build_path.write_text(patched)
            patch_entries.append({
                "iter": it,
                "bytes": len(patch_text),
                "backup": backup.name if backup else None,
                "model": builder_model,
                "applied_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            iter_log["iterations"][-1]["patch_bytes"] = len(patch_text)
            iter_log["iterations"][-1]["backup"] = backup.name if backup else None
            iter_log["iterations"][-1]["model"] = builder_model
            print(f"     ✅ patch applied (size {len(patched)//1024}KB)")
            tracer.end_span(iter_span, output={
                "complete": False,
                "patch_bytes": len(patch_text),
                "signals": signals,
            })
        except Exception as e:
            print(f"     ❌ iteration {it} crashed: {e}")
            iter_log["iterations"].append({"iter": it, "error": str(e)[:500]})
            tracer.end_span(iter_span, output={"error": str(e)[:500]})
            final_status = "failed"
            break

    # Final post-budget scan if we didn't break out as complete.
    if final_status == "partial":
        try:
            walk = walk_experience(build_path, walks_dir, f"{concept_name}-final")
            walk_signals = _playability_signals_from_walk(walk, requirements)
            dom_signals = _playability_scan_dom_signals(build_path, requirements)
            final_signals = _playability_merge_signals(walk_signals, dom_signals)
            iter_log["iterations"].append({"iter": "final", "signals": final_signals})
            if _playability_is_complete(final_signals, requirements):
                final_status = "complete"
        except Exception as e:
            iter_log["iterations"].append({"iter": "final", "error": str(e)[:500]})

    # Sync the eval app build for this concept.
    try:
        _sync_eval_builds(run_dir, [idx])
    except Exception as e:
        print(f"  ⚠️  eval-build sync failed for concept-{idx} (non-fatal): {e}")

    # Persist per-concept iter log.
    try:
        (iter_log_dir / f"{concept_name}-iterlog.json").write_text(
            json.dumps(iter_log, indent=2, default=str)
        )
    except Exception:
        pass

    tracer.end_span(span, output={
        "status": final_status,
        "iterations": iterations_used,
        "signals": final_signals,
        "patches": len(patch_entries),
        "model": builder_model,
    })

    status_emoji = {"complete": "✅", "partial": "⚠️", "failed": "❌", "skipped": "⏭"}.get(final_status, "·")
    print(f"  {status_emoji} {concept_name}: {final_status} after {iterations_used} iter(s) [{builder_model}]")

    return {
        **routing,
        "playability_signals": {idx: final_signals},
        "playability_iterations": {idx: iterations_used},
        "playability_status": {idx: final_status},
        "playability_patches": {idx: patch_entries},
    }


def _builder_qa_fix_run(state: dict) -> dict:
    """QA-fix mode — one patch iteration driven by the QA loop.

    Reuses `_builder_playability_run` as the patch driver (walker + DOM
    signals + approach-doc-anchored prompt) because the qa_fix scope is a
    superset of the playability scope: same surgical-patch model, same
    per-concept-model routing, just with broader trigger criteria. On top of
    the playability return shape, we also bump `qa_iterations` for this
    concept and set `builder_mode="qa_fix"` so the router sends us back to
    qa_loop for re-validation.

    NOTE: The QA loop itself drives the OUTER iteration counter (one
    `_builder_qa_fix_run` invocation = ONE patch attempt). This wrapper sets
    `playability_max_iter=1` for the inner call so it doesn't burn its own
    internal budget on top of the outer loop's budget.
    """
    idx = state.get("build_index")
    # Force the playability driver to do exactly one patch per outer-loop visit.
    inner_state = {**state, "playability_max_iter": 1}
    out = _builder_playability_run(inner_state)
    out["builder_mode"] = "qa_fix"
    # Bump per-concept qa_iterations by 1 — the _merge_dict reducer ADDS this to
    # whatever the previous value was (well, REPLACES — so we have to read it
    # from state and emit current+1).
    prev_iters = (state.get("qa_iterations", {}) or {}).get(idx, 0)
    out["qa_iterations"] = {idx: prev_iters + 1}
    return out


def _judge_polish_build_patch_prompt(brief_text: str, score_json: dict,
                                       approach_doc: str, code_context: str,
                                       iteration: int, max_iter: int,
                                       concept_index: int) -> tuple[str, str]:
    """Build the judge-polish patch prompt.

    Anchored to the ORIGINAL approach doc (per-concept-model voice) and driven
    by the latest REVIEWER score's Priority Fixes list. The model gets the
    JSON-structured feedback verbatim so it can address each item.
    """
    fixes = score_json.get("priority_fixes", {}) or {}
    p0 = fixes.get("p0_broken", []) or []
    p1 = fixes.get("p1_must_fix", []) or []
    p2 = fixes.get("p2_polish", []) or []
    scores = score_json.get("scores", {}) or {}
    weighted = score_json.get("weighted_total")
    weighted_s = f"{weighted:.2f}" if isinstance(weighted, (int, float)) else "?"
    gut = (score_json.get("gut_reaction") or "").strip()
    slop = score_json.get("ai_slop_flagged")

    weak_dims = [k for k, v in scores.items() if isinstance(v, (int, float)) and v < 6.0]

    def _fmt(items, label):
        if not items:
            return f"({label}: none)"
        return f"### {label}\n" + "\n".join(f"- {it}" for it in items)

    system = (
        "You are the original builder of this concept, doing a JUDGE-POLISH PATCH.\n\n"
        "The build has rendered and is interactive, but a calibrated design reviewer"
        " scored it below the taste bar. Your job: apply the Priority Fixes listed"
        " below WITHOUT redesigning the concept. Stay true to your approach doc —"
        " same palette, same metaphor, same composition logic.\n\n"
        "OUTPUT FORMAT:"
        "\n- Output ONLY a single <script>...</script> block. No markdown fences. No prose. No <html>/<body>."
        "\n- It will be appended right before </body> and runs AFTER all existing code."
        "\n- Vanilla JS only. Guard with DOMContentLoaded."
        "\n- Address P0 (broken) FIRST, then P1 (must fix), then P2 (polish)."
        "\n- For visual changes: mutate the DOM / inject <style> tags / replace innerHTML."
        "\n- For typography fixes: add a new <style> block with concrete font-size / letter-spacing / weight rules."
        "\n- For composition fixes: add transforms, reposition elements, change layout via CSS."
        "\n- If previous polish patches exist (look for `<!-- AUTO-PATCH:` comments), your new patch must SUPERSEDE them via more-specific selectors or by removing the prior <style> blocks first."
        "\n- Do NOT rewrite the entire concept. Surgical changes only."
    )

    approach_block = (approach_doc[:8000] if approach_doc else "(approach doc unavailable — stay true to the existing code's style)")

    user = f"""## YOUR ORIGINAL APPROACH DOC (concept-{concept_index}) — creative anchor
{approach_block}

## BRIEF CONTEXT
{brief_text[:3000]}

## ITERATION {iteration}/{max_iter}

## REVIEWER SCORECARD (most recent pass)
Weighted total: {weighted_s} / 10
Gut reaction: {gut}
AI slop flagged: {slop}
Weak dimensions (< 6.0): {weak_dims if weak_dims else '(none — fixes are about pushing above 7.0)'}

Per-dimension scores:
{json.dumps(scores, indent=2)}

## PRIORITY FIXES (apply in order)
{_fmt(p0, 'P0 — BROKEN (must fix first)')}

{_fmt(p1, 'P1 — MUST FIX (taste-gate blockers)')}

{_fmt(p2, 'P2 — POLISH (do these if you have headroom)')}

## CURRENT BUILD (code chunks, base64 assets stripped to placeholders)
{code_context}

## YOUR TASK
Write a single <script> block that surgically applies the Priority Fixes above to the existing build. Stay in your original creative voice — same palette, same metaphor. The goal is to push the weighted total above 7.0 and every dimension above 5.0 without redesigning the concept.
"""
    return system, user


def _builder_judge_polish_run(state: dict) -> dict:
    """Judge-polish mode — one patch iteration driven by the judge loop.

    Mirrors `_builder_qa_fix_run` but uses the REVIEWER score's Priority
    Fixes as patch input instead of the walker's playability gaps. The patch
    is appended (non-destructive, same pattern as playability).
    """
    idx = state.get("build_index")
    builds = state.get("builds", []) or []
    build = _build_for_index(builds, idx)
    approaches = state.get("approaches", []) or []
    judge_scores = state.get("judge_scores", {}) or {}
    score = judge_scores.get(idx, {}) or {}

    routing = {"builder_mode": "judge_polish"}

    if build is None:
        print(f"[JUDGE-POLISH {idx}] build dict not found — skipping")
        return {**routing}

    build_path = Path(build["path"])
    if not build_path.exists() or build_path.stat().st_size < 500:
        print(f"[JUDGE-POLISH {idx}] missing/empty build — skipping")
        return {**routing}

    if _cost_circuit_broken(state):
        print(f"[JUDGE-POLISH {idx}] cost circuit broken — skipping")
        return {**routing, "cost_circuit_broken": True}

    builder_model = (
        state.get("builder_model")
        or build.get("model")
        or "claude-opus"
    )
    approach = _approach_for_designer(approaches, build.get("designer_id"))
    approach_doc = approach.get("content", "") if approach else ""

    iter_now = (state.get("judge_polish_iterations", {}) or {}).get(idx, 0) + 1
    max_iter = state.get("judge_max_iter") or MAX_JUDGE_ITERATIONS

    print(f"\n[JUDGE-POLISH {idx}] concept-{idx}: polish patch via {builder_model} "
          f"(iter {iter_now}/{max_iter})")

    span = tracer.start_span(f"judge_polish-{idx}", input={
        "concept": f"concept-{idx}",
        "model": builder_model,
        "iteration": iter_now,
        "max_iter": max_iter,
    })

    patch_model_alias = builder_model
    patch_model_resolved = resolve_model(patch_model_alias)
    patch_max_tokens = max_output_for(patch_model_resolved, kind="generation")

    try:
        html = build_path.read_text(errors="ignore")
        code_ctx = _playability_extract_code_chunks(html, max_chars=PLAYABILITY_CODE_MAX_CHARS)
        system, user = _judge_polish_build_patch_prompt(
            brief_text=state.get("brief", "") or "",
            score_json=score,
            approach_doc=approach_doc,
            code_context=code_ctx,
            iteration=iter_now,
            max_iter=max_iter,
            concept_index=idx,
        )

        with tracer.generation(
            name=f"judge_polish_patch_{idx}_iter{iter_now}_{builder_model}",
            model=patch_model_resolved,
            input=user,
            model_parameters={"max_tokens": patch_max_tokens},
            metadata={
                "phase": "judge_polish",
                "concept": idx,
                "iteration": iter_now,
                "intended_model": builder_model,
                "designer_id": build.get("designer_id"),
            },
        ) as gen:
            patch_text, _usage = _call_playability_patch_model(
                patch_model_alias, system, user, patch_max_tokens, gen
            )

        if len(patch_text) < PLAYABILITY_PATCH_MIN_BYTES:
            print(f"     ❌ judge-polish patch too short ({len(patch_text)} bytes) — aborting concept")
            tracer.end_span(span, output={"error": "patch_too_short"})
            return {**routing, "judge_polish_iterations": {idx: iter_now}}

        patched = _playability_apply_patch(html, patch_text)
        backup = build_path.with_suffix(f".pre-judge-polish-iter{iter_now}-{int(time.time())}.html")
        try:
            _shutil.copy(build_path, backup)
        except Exception:
            backup = None
        build_path.write_text(patched)
        print(f"     ✅ judge-polish patch applied (size {len(patched)//1024}KB)")

        # Sync the eval app build for this concept.
        run_dir = RUNS_DIR / state["name"]
        try:
            _sync_eval_builds(run_dir, [idx])
        except Exception as e:
            print(f"  ⚠️  eval-build sync failed for concept-{idx} (non-fatal): {e}")

        tracer.end_span(span, output={"patch_bytes": len(patch_text), "iteration": iter_now})
    except Exception as e:
        print(f"     ❌ judge-polish iteration crashed: {e}")
        tracer.end_span(span, output={"error": str(e)[:500]})
        return {**routing, "judge_polish_iterations": {idx: iter_now}}

    # Clear this concept's `judge_status` so the next judge_loop visit will
    # re-score (instead of seeing the previous `pending_polish` and skipping).
    return {
        **routing,
        "judge_polish_iterations": {idx: iter_now},
        "judge_status": {idx: "pending_polish"},  # placeholder; judge_loop will overwrite
    }


def fan_out_playability_mode(state: PipelineState) -> list:
    """Fan out to N parallel `builder` invocations in playability mode.

    Mirrors `fan_out_builders` exactly — one Send per build, each carrying:
      - build_index: which build to patch
      - builder_model: the ORIGINAL builder model for that concept
                       (claude-opus / gpt-5 / gemini-3.1-pro), pulled from
                       build["model"] so the playability patch comes from the
                       same provider that did the initial build
      - builder_mode: "playability" — routes builder_node to _builder_playability_run

    If playability is disabled (max_iter == 0) returns an empty list so the
    graph router can short-circuit qa → judge.
    """
    max_iter = state.get("playability_max_iter")
    if max_iter is None:
        max_iter = MAX_PLAYABILITY_ITERATIONS
    if not max_iter or max_iter <= 0:
        return []

    builds = state.get("builds", []) or []
    sends = []
    for build in builds:
        idx = build.get("index")
        if idx is None:
            continue
        # Default to claude-opus if model field is missing for any reason.
        builder_model = build.get("model") or "claude-opus"
        sends.append(Send("builder", {
            **state,
            "build_index": idx,
            "builder_model": builder_model,
            "builder_mode": "playability",
        }))
    return sends


def route_after_qa(state: PipelineState) -> list:
    """Legacy conditional-edge router from the old `qa` node.

    Retained only so the legacy graph wiring still compiles. The active graph
    uses `qa_loop` → `route_after_qa_loop` instead. Kept verbatim for fast
    rollback to the old qa→playability→judge flow.
    """
    max_iter = state.get("playability_max_iter")
    if max_iter is None:
        max_iter = MAX_PLAYABILITY_ITERATIONS
    if not max_iter or max_iter <= 0:
        return "judge"
    builds = state.get("builds", []) or []
    if not builds:
        return "judge"
    return fan_out_playability_mode(state)


def route_after_builder(state: PipelineState) -> str:
    """Conditional-edge router from `builder` → next loop node.

    Reads the `builder_mode` written by builder_node into the merged state. All
    parallel Sends of a given pass write the same value so the merged read is
    well-defined regardless of fan-in ordering.

    Modes:
      - "initial"        → qa_loop (run QA on the fresh build)
      - "qa_fix"         → qa_loop (re-run QA on the patched build)
      - "playability"    → qa_loop (legacy alias for qa_fix)
      - "judge_polish"   → judge_loop (re-score the patched build)
    """
    mode = state.get("builder_mode") or "initial"
    if mode == "judge_polish":
        return "judge_loop"
    # initial, qa_fix, playability → qa_loop
    return "qa_loop"


# ──────────────────────────────────────────────────────────────────────────
# QA Loop + Judge Polish Loop (2026-05-13 refactor)
# Plan: ~/.openclaw/workspace/memory/plans/qa-judge-loop-refactor.md
# Backup of pre-refactor pipeline: pipeline.py.before-qa-judge-loops
# ──────────────────────────────────────────────────────────────────────────

def _cost_circuit_broken(state: PipelineState) -> bool:
    """True if either the in-state breaker is set OR the live run cost has
    crossed MAX_COST_USD. Either side trips the breaker for the rest of the
    run.
    """
    if state.get("cost_circuit_broken"):
        return True
    # _run_costs is the module-level accumulator track_cost() updates.
    return _run_costs.get("total_usd", 0.0) >= MAX_COST_USD


def _run_qa_checks_for_build(build: dict, state: PipelineState,
                              qa_dir: Path, screenshot_dir: Path,
                              walks_dir: Path) -> dict:
    """Run the full QA check battery on ONE build and return a structured report.

    Folds together everything the legacy `qa_station_node` did per-build
    (source checks, render, console errors, mobile viewport, design system,
    asset references) PLUS the walker-driven playability completion check
    that used to live in `_builder_playability_run`. Output mirrors the
    legacy QA report shape (so eval-app readers keep working) and adds
    `playability_signals` + `verdict` semantics consistent with the loop.
    """
    from playwright.sync_api import sync_playwright

    idx = build["index"]
    concept_name = f"concept-{idx}"
    build_path = Path(build["path"])
    sample_items = _extract_sample_items(state.get("brief", "") or "")
    requirements = _playability_infer_requirements(state.get("brief", "") or "")

    report = {
        "build": concept_name,
        "index": idx,
        "model": build.get("model", "unknown"),
        "source_checks": {},
        "experience_checks": {},
        "playability": {"requirements": requirements, "signals": {}, "complete": False},
        "verdict": "BROKEN",
        "issues": [],
        "fix_attempts": build.get("qa_fix_attempts", 0),
    }

    if not build_path.exists() or build_path.stat().st_size < 500:
        report["issues"].append(
            f"Build file missing or empty ({build_path.stat().st_size if build_path.exists() else 0} bytes)"
        )
        return report

    html_content = build_path.read_text(errors="ignore")

    # ── SOURCE CHECKS ──
    items_found = [it for it in sample_items if it.lower() in html_content.lower()]
    items_missing = [it for it in sample_items if it not in items_found]
    report["source_checks"]["content"] = {
        "items_found": len(items_found),
        "items_expected": len(sample_items),
        "missing": items_missing,
        "pass": len(sample_items) == 0 or len(items_found) >= len(sample_items) * 0.7,
    }
    if not report["source_checks"]["content"]["pass"]:
        report["issues"].append(
            f"Content fidelity: only {len(items_found)}/{len(sample_items)} sample items found. "
            f"Missing: {', '.join(items_missing[:3])}"
        )

    has_width = "1080" in html_content
    has_height = "1920" in html_content
    report["source_checks"]["dimensions"] = {
        "width_ref": has_width, "height_ref": has_height, "pass": has_width and has_height,
    }

    report["source_checks"]["spec_compliance"] = build.get("compliance", {})
    report["source_checks"]["asset_validation"] = build.get("asset_validation", {})

    if state.get("design_system"):
        ds_result = check_design_system_compliance(build_path, state["design_system"])
        report["source_checks"]["design_system"] = ds_result
        if not ds_result["pass"]:
            for v in ds_result["violations"]:
                report["issues"].append(f"Design system violation: {v}")

    # ── EXPERIENCE CHECKS (Playwright) ──
    pw = None
    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception as e:
        report["experience_checks"]["error"] = f"Playwright failed: {e}"
        report["issues"].append(f"Browser QA unavailable: {e}")

    if browser:
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            console_errors: list = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: console_errors.append(str(err)))
            page.goto(f"file://{build_path.resolve()}", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1000)
            ss_t0 = screenshot_dir / f"{concept_name}.png"
            page.screenshot(path=str(ss_t0), full_page=False)
            page.wait_for_timeout(3000)
            ss_t3 = screenshot_dir / f"{concept_name}-t3.png"
            page.screenshot(path=str(ss_t3), full_page=False)

            render_ok = _check_render(str(ss_t0))
            report["experience_checks"]["render"] = {"pass": render_ok, "screenshot": str(ss_t0)}
            if not render_ok:
                report["issues"].append("Render check FAILED — page appears blank or near-blank")

            anim_diff = _compare_screenshots(str(ss_t0), str(ss_t3))
            report["experience_checks"]["animation"] = {
                "diff_percent": anim_diff,
                "has_animation": anim_diff > 2.0,
            }

            report["experience_checks"]["console_errors"] = {
                "count": len(console_errors),
                "errors": console_errors[:5],
                "pass": len(console_errors) == 0,
            }
            if console_errors:
                report["issues"].append(f"Console errors: {len(console_errors)} — {console_errors[0][:80]}")

            images_status = page.evaluate("""() => {
                const imgs = document.querySelectorAll('img');
                let loaded = 0, broken = 0;
                imgs.forEach(img => {
                    if (img.complete && img.naturalWidth > 0) loaded++;
                    else broken++;
                });
                return { total: imgs.length, loaded, broken };
            }""")
            report["experience_checks"]["images"] = images_status
            if images_status.get("broken", 0) > 0:
                report["issues"].append(f"Broken images: {images_status['broken']}/{images_status['total']}")
            page.close()

            # Mobile viewport spot-check
            try:
                mp = browser.new_page(viewport={"width": 390, "height": 844})
                mp.goto(f"file://{build_path}", wait_until="networkidle")
                mp.wait_for_timeout(2000)
                mob = mp.evaluate("""() => {
                    const body = document.documentElement;
                    return {
                        scrollWidth: body.scrollWidth,
                        scrollHeight: body.scrollHeight,
                        clientWidth: body.clientWidth,
                        clientHeight: body.clientHeight,
                        needsScroll: body.scrollHeight > body.clientHeight * 1.5,
                    };
                }""")
                report["experience_checks"]["mobile_viewport"] = {
                    "viewport": "390x844",
                    "needs_scroll": mob.get("needsScroll", False),
                    "scroll_height": mob.get("scrollHeight", 0),
                    "pass": not mob.get("needsScroll", False),
                }
                if mob.get("needsScroll", False):
                    report["issues"].append(
                        f"Mobile viewport: content overflows 844px (scroll height {mob.get('scrollHeight', 0)}px)"
                    )
                mp.close()
            except Exception as me:
                report["experience_checks"]["mobile_viewport"] = {"error": str(me)}
        except Exception as e:
            report["experience_checks"]["error"] = str(e)
            report["issues"].append(f"Browser QA failed: {type(e).__name__}: {str(e)[:100]}")

        try:
            browser.close()
        except Exception:
            pass
    if pw:
        try:
            pw.stop()
        except Exception:
            pass

    # ── PLAYABILITY (walker-driven) ──
    # For multi-step briefs, the walker determines whether the experience
    # actually reaches its end states (rounds, performance reveal, share card).
    try:
        walks_dir.mkdir(parents=True, exist_ok=True)
        walk = walk_experience(build_path, walks_dir, f"{concept_name}-qa-iter{report['fix_attempts']}")
        walk_signals = _playability_signals_from_walk(walk, requirements)
        dom_signals = _playability_scan_dom_signals(build_path, requirements)
        signals = _playability_merge_signals(walk_signals, dom_signals)
        report["playability"]["signals"] = signals
        if requirements.get("is_multistep"):
            complete = _playability_is_complete(signals, requirements)
            report["playability"]["complete"] = complete
            if not complete:
                gap = _playability_gap_summary(signals, requirements)
                report["issues"].append(f"Playability incomplete: {gap}")
        else:
            # Non-multistep briefs auto-pass playability.
            report["playability"]["complete"] = True
        # Also flag dead/inert prototypes regardless of multistep-ness.
        if walk.get("inert_prototype"):
            report["issues"].append("Prototype is inert — no interactive elements detected.")
        elif walk.get("dead_prototype"):
            report["issues"].append("Prototype is dead — buttons exist but clicking them produced no state change.")
    except Exception as e:
        report["playability"]["error"] = str(e)
        report["issues"].append(f"Walker error: {type(e).__name__}: {str(e)[:80]}")

    # ── VERDICT ──
    critical = [i for i in report["issues"] if "BROKEN" in i or "blank" in i.lower() or "missing/empty" in i.lower()]
    if critical:
        report["verdict"] = "BROKEN"
    elif report["issues"]:
        report["verdict"] = "FIXABLE"
    else:
        report["verdict"] = "PASS"

    # Persist this iteration's report under qa-reports/<concept>-qa-iter<N>.json
    try:
        qa_dir.mkdir(parents=True, exist_ok=True)
        path = qa_dir / f"{concept_name}-qa-iter{report['fix_attempts']}.json"
        path.write_text(json.dumps(report, indent=2, default=str))
        # Also keep a `<concept>-qa.json` pointer to the latest, matching legacy eval-app readers.
        (qa_dir / f"{concept_name}-qa.json").write_text(json.dumps(report, indent=2, default=str))
    except Exception:
        pass

    return report


def qa_loop_node(state: PipelineState) -> dict:
    """Per-concept QA loop. Replaces qa_station_node + playability_loop.

    Fans out internally: each concept is QA'd, and if it fails, sent back to
    `builder_node` in `builder_mode="qa_fix"` for a surgical patch in the
    SAME builder model voice that produced the initial build. Loops up to
    MAX_QA_ITERATIONS per concept. The actual builder calls happen via Send
    edges back to the `builder` node — this node ITSELF only runs the QA
    checks on whatever builds currently exist in state.

    State contract:
      - On entry: state["builds"] has the freshly-built (or freshly-patched)
                  HTML files for every concept.
      - On exit:  per-concept `qa_status` is one of "pass" / "failed_max" /
                  "cost_circuit"; `qa_reports_by_concept` holds the latest
                  report for each concept.
      - Routing:  `route_after_qa_loop` then either issues Sends back to
                  `builder` (concepts still needing qa_fix and under iter
                  cap) or advances the graph to `judge_loop`.
    """
    builds = state.get("builds", []) or []
    if not builds:
        return {"phase": "qa_loop_empty"}

    print(f"[QA-LOOP] Running QA checks on {len(builds)} concepts")
    span = tracer.start_span("qa_loop", input={"build_count": len(builds)})

    run_dir = RUNS_DIR / state["name"]
    qa_dir = run_dir / "qa-reports"
    screenshot_dir = run_dir / "screenshots"
    walks_dir = run_dir / "walks"
    qa_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    walks_dir.mkdir(parents=True, exist_ok=True)

    max_iter = state.get("qa_max_iter")
    if max_iter is None:
        max_iter = MAX_QA_ITERATIONS

    prev_status = dict(state.get("qa_status", {}) or {})
    prev_iters = dict(state.get("qa_iterations", {}) or {})
    new_reports: Dict[int, dict] = {}
    new_status: Dict[int, str] = {}
    new_iters: Dict[int, int] = {}
    legacy_reports: list = []

    cost_broken_now = _cost_circuit_broken(state)

    for b in builds:
        idx = b["index"]
        # If this concept already PASSED in a previous loop visit, leave it alone.
        if prev_status.get(idx) == "pass":
            new_status[idx] = "pass"
            new_iters[idx] = prev_iters.get(idx, 0)
            old_report = (state.get("qa_reports_by_concept", {}) or {}).get(idx)
            if old_report:
                new_reports[idx] = old_report
                legacy_reports.append(old_report)
            continue

        # Cost circuit: stop spending on this concept.
        if cost_broken_now or prev_status.get(idx) in ("cost_circuit",):
            new_status[idx] = "cost_circuit"
            new_iters[idx] = prev_iters.get(idx, 0)
            print(f"  ⛔ concept-{idx}: cost circuit broken — skipping QA")
            continue

        # Make sure the build dict carries its current fix-attempt count for the helper.
        b["qa_fix_attempts"] = prev_iters.get(idx, 0)
        report = _run_qa_checks_for_build(b, state, qa_dir, screenshot_dir, walks_dir)
        new_reports[idx] = report
        legacy_reports.append(report)

        if report["verdict"] == "PASS":
            new_status[idx] = "pass"
            new_iters[idx] = prev_iters.get(idx, 0)
            print(f"  ✅ concept-{idx}: QA PASS (iter {new_iters[idx]})")
        else:
            # Verdict is FIXABLE or BROKEN. Either way, we attempt a qa_fix
            # iteration unless we've hit the cap.
            current_iter = prev_iters.get(idx, 0)
            if current_iter >= max_iter:
                new_status[idx] = "failed_max"
                new_iters[idx] = current_iter
                print(f"  ❌ concept-{idx}: QA {report['verdict']} — max iterations ({max_iter}) reached")
            else:
                # Pending qa_fix — route_after_qa_loop will fan out to builder.
                new_status[idx] = "pending"
                new_iters[idx] = current_iter  # bumped when the Send is issued
                print(f"  🔧 concept-{idx}: QA {report['verdict']} — will patch (iter {current_iter+1}/{max_iter})")
                for issue in report["issues"][:5]:
                    print(f"      → {issue}")

    passed = sum(1 for s in new_status.values() if s == "pass")
    failed = sum(1 for s in new_status.values() if s == "failed_max")
    cost_c = sum(1 for s in new_status.values() if s == "cost_circuit")
    pending = sum(1 for s in new_status.values() if s == "pending")
    print(f"[QA-LOOP] Status: {passed} pass | {pending} need fix | {failed} failed_max | {cost_c} cost_circuit")

    tracer.end_span(span, output={"pass": passed, "pending": pending,
                                    "failed_max": failed, "cost_circuit": cost_c})

    return {
        "qa_status": new_status,
        "qa_iterations": new_iters,
        "qa_reports_by_concept": new_reports,
        # Mirror to the legacy `qa_reports` list so existing eval-app + verdict
        # consumers keep functioning. (List replaces, not appends — not Annotated[add].)
        "qa_reports": legacy_reports,
        "phase": "qa_loop",
        "cost_circuit_broken": cost_broken_now,
    }


def fan_out_qa_fix(state: PipelineState) -> list:
    """Fan out one Send per concept whose qa_status == 'pending'.

    Each Send targets the builder node in builder_mode="qa_fix" using the
    ORIGINAL builder model for that concept (per-concept-model rule).
    """
    qa_status = state.get("qa_status", {}) or {}
    builds = state.get("builds", []) or []
    sends = []
    for build in builds:
        idx = build.get("index")
        if idx is None:
            continue
        if qa_status.get(idx) != "pending":
            continue
        builder_model = build.get("model") or "claude-opus"
        sends.append(Send("builder", {
            **state,
            "build_index": idx,
            "builder_model": builder_model,
            "builder_mode": "qa_fix",
        }))
    return sends


def route_after_qa_loop(state: PipelineState):
    """From `qa_loop` → builder (qa_fix Sends) OR → `judge_loop`.

    Returns either a list of Sends (one per concept needing qa_fix, fanning
    into `builder`) or the string `"judge_loop"` to advance.
    """
    # If cost circuit tripped, short-circuit to judge_loop — judge_loop will
    # itself notice the breaker and mark every concept cost_circuit.
    if _cost_circuit_broken(state):
        return "judge_loop"
    sends = fan_out_qa_fix(state)
    if sends:
        return sends
    return "judge_loop"


# ──────────────────────────────────────────────────────────────────────────
# Judge Loop — per-build scoring using REVIEWER persona
# ──────────────────────────────────────────────────────────────────────────

def _score_meets_threshold(scores_json: dict, threshold: dict) -> tuple[bool, str]:
    """Check a per-build score JSON against the hybrid threshold.

    Returns (passes, reason_string). The reason string is a human-readable
    one-line summary used for logs and for the priority-fix prompt.
    """
    if not scores_json or not isinstance(scores_json, dict):
        return False, "no score JSON"

    if threshold.get("ai_slop_hardcap", True) and scores_json.get("ai_slop_flagged"):
        return False, "AI slop flagged (hard-cap)"

    if scores_json.get("renders_and_runs") is False:
        return False, "renders_and_runs == false (binary tech gate)"

    scores = scores_json.get("scores", {}) or {}
    min_dim = float(threshold.get("min_dimension", 5.0))
    low_dims = [k for k, v in scores.items() if isinstance(v, (int, float)) and v < min_dim]
    if low_dims:
        return False, f"dimension(s) below {min_dim}: {', '.join(low_dims)}"

    weighted = scores_json.get("weighted_total")
    if not isinstance(weighted, (int, float)):
        return False, "missing weighted_total"
    if weighted < float(threshold.get("weighted_total", 7.0)):
        return False, f"weighted_total {weighted:.2f} < {threshold.get('weighted_total', 7.0)}"

    return True, f"weighted_total {weighted:.2f} clears bar"


def _judge_score_one_build(build: dict, state: PipelineState, score_dir: Path,
                            walks_dir: Path, judge_model: str,
                            judge_max_tokens: int, judge_system: str,
                            other_approach_summaries: str) -> dict:
    """Score ONE build using the REVIEWER persona via judge_score.txt.

    Returns the parsed JSON response (or an error envelope).
    """
    idx = build["index"]
    concept_name = f"concept-{idx}"
    build_path = Path(build["path"])

    # 1. Walker journey for THIS build only.
    walk = walk_experience(build_path, walks_dir, f"{concept_name}-judge")
    journey = _select_journey_screenshots(walk, max_count=WALKER_MAX_SCREENSHOTS)

    # 2. Approach doc for this concept.
    approaches = state.get("approaches", []) or []
    approach = _approach_for_designer(approaches, build.get("designer_id")) or {}
    approach_content = approach.get("content", "") or ""

    # 3. Moodboard refs.
    moodboard_dir = RUNS_DIR / state["name"] / "moodboard"
    moodboard_parts = []
    if moodboard_dir.exists():
        files = sorted([f for f in moodboard_dir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png"]])
        for mf in files[:3]:
            try:
                mb_b64 = encode_image(str(mf))
                ext = mf.suffix.lower().lstrip(".")
                mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
                moodboard_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{mb_b64}"}})
            except Exception:
                pass

    # 4. Build the user-message parts.
    parts: list = []
    if moodboard_parts:
        parts.append({"type": "text", "text": "MOODBOARD REFERENCES (the visual direction this build should match):"})
        parts.extend(moodboard_parts)

    brief_excerpt = (state.get("brief", "") or "")[:1500]
    parts.append({
        "type": "text",
        "text": (
            f"# Brief context\n{brief_excerpt}\n\n"
            f"# Concept index being scored: {idx}\n\n"
            f"# This concept's approach doc\n{approach_content[:8000]}\n\n"
            f"# Sibling concepts (approach doc summaries — for Distinctiveness scoring only)\n"
            f"{other_approach_summaries or '(no siblings)'}"
        ),
    })

    walk_summary = (
        f"\n# Walker journey for THIS concept\n"
        f"- {len(journey)} screenshots, "
        f"{walk.get('interactive_elements_found', 0)} interactive elements found, "
        f"{walk.get('clicks_attempted', 0)} click(s) attempted, "
        f"{walk.get('clicks_that_changed_state', 0)} produced state changes, "
        f"{walk.get('unique_states', 0)} unique states visited."
    )
    if walk.get("inert_prototype"):
        walk_summary += " ⚠️ INERT — no interactive elements detected."
    elif walk.get("dead_prototype"):
        walk_summary += " ⚠️ DEAD — buttons exist but clicking produced no state change."
    if walk.get("console_errors_total"):
        walk_summary += f" {walk['console_errors_total']} console error(s) observed."
    parts.append({"type": "text", "text": walk_summary})

    for k, s in enumerate(journey):
        caption = f"Journey screen {k + 1} of {len(journey)}"
        if k == 0:
            caption += " (initial state)"
        elif s.get("clicked_label"):
            action = (s.get("clicked_label") or "")[:60].replace("\n", " ").strip()
            if s.get("state_changed"):
                caption += f" — after clicking “{action}”"
            else:
                caption += f" — after clicking “{action}” (no visible state change)"
        parts.append({"type": "text", "text": caption})
        try:
            b64 = encode_image(s["screenshot"]) if s.get("screenshot") else None
        except Exception:
            b64 = None
        if b64:
            parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

    parts.append({"type": "text", "text": "Now score this concept. Respond with VALID JSON ONLY — no markdown fences, no prose."})

    text_only = judge_system + "\n\n[USER]\n" + "\n".join(p["text"] for p in parts if p.get("type") == "text")
    n_images = sum(1 for p in parts if p.get("type") == "image_url")

    # 5. Call the judge model. (Frontier-only — resolve_model has already been applied to judge_model.)
    with tracer.generation(
        name=f"judge_score_{idx}",
        model=judge_model,
        input=text_only,
        model_parameters={"max_tokens": judge_max_tokens},
        metadata={"phase": "judge_score", "concept": idx, "image_count": n_images},
    ) as gen:
        try:
            response = openai_client.chat.completions.create(
                model=judge_model,
                max_completion_tokens=judge_max_tokens,
                messages=[
                    {"role": "system", "content": judge_system},
                    {"role": "user", "content": parts},
                ],
            )
            raw = response.choices[0].message.content or ""
            gen.set_output(raw[:8000])
            if response.usage:
                gen.set_usage(input_tokens=response.usage.prompt_tokens,
                              output_tokens=response.usage.completion_tokens)
                track_cost(judge_model, response.usage.prompt_tokens,
                            response.usage.completion_tokens, "judge_score")
        except Exception as e:
            gen.set_error(str(e)[:500])
            return {"concept_index": idx, "error": str(e)[:500], "verdict": "below_bar",
                    "weighted_total": 0.0, "scores": {}, "renders_and_runs": False,
                    "priority_fixes": {"p0_broken": [f"Judge call failed: {e}"], "p1_must_fix": [], "p2_polish": []}}

    # 6. Parse JSON.
    parsed = _parse_judge_score_json(raw)
    parsed["_raw_response"] = raw[:4000]
    parsed["concept_index"] = idx

    # Persist per-iteration score file for debugging.
    try:
        score_dir.mkdir(parents=True, exist_ok=True)
        iters = (state.get("judge_polish_iterations", {}) or {}).get(idx, 0)
        (score_dir / f"{concept_name}-score-iter{iters}.json").write_text(
            json.dumps(parsed, indent=2, default=str)
        )
    except Exception:
        pass

    return parsed


def _parse_judge_score_json(raw: str) -> dict:
    """Tolerant JSON extractor for judge_score responses.

    The prompt asks for plain JSON, but models still occasionally wrap it in
    ```json fences or add a leading sentence. We strip fences and try to
    extract the first {...} block.
    """
    text = (raw or "").strip()
    # Strip markdown fences
    if "```json" in text:
        text = text.split("```json", 1)[1]
        if "```" in text:
            text = text.split("```", 1)[0]
    elif text.startswith("```"):
        text = text.strip("`")
        # Try to drop a leading language tag like "json\n"
        if text.startswith("json"):
            text = text[4:].lstrip()
        if "```" in text:
            text = text.split("```", 1)[0]
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass

    # Fallback: find the largest {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return {
        "error": "failed_to_parse_score_json",
        "verdict": "below_bar",
        "weighted_total": 0.0,
        "scores": {},
        "renders_and_runs": False,
        "priority_fixes": {
            "p0_broken": ["Judge returned non-JSON output. Retry the build with renewed instructions."],
            "p1_must_fix": [],
            "p2_polish": [],
        },
        "_raw_excerpt": (raw or "")[:500],
    }


def _summarize_approach_for_distinctiveness(approach: dict, max_chars: int = 800) -> str:
    """Compress an approach doc to a short blurb used for sibling Distinctiveness scoring."""
    if not approach:
        return ""
    content = approach.get("content", "") or ""
    # Grab the first paragraph + any 'palette' / 'tech stack' / 'composition' lines.
    head = content[:max_chars]
    return f"## Designer {approach.get('designer_id', '?')} ({approach.get('model', '?')})\n{head.strip()}\n"


def judge_loop_node(state: PipelineState) -> dict:
    """Per-concept judge polish loop. Replaces pairwise_judge_node for scoring.

    Scores each build using the REVIEWER persona via prompts/judge_score.txt.
    Concepts that clear the hybrid threshold are marked "above_bar".
    Concepts that don't are sent back to `builder` in builder_mode="judge_polish"
    until they pass or hit MAX_JUDGE_ITERATIONS.

    After ALL concepts complete, the next node (pairwise_rank) does the
    final ordering tournament — but only among above_bar survivors.
    """
    builds = state.get("builds", []) or []
    if not builds:
        return {"phase": "judge_loop_empty"}

    # Concepts that didn't get through QA never enter the judge loop —
    # they stay flagged at qa_status level so the human can see why.
    qa_status = state.get("qa_status", {}) or {}

    print(f"[JUDGE-LOOP] Scoring {len(builds)} concepts against threshold")
    span = tracer.start_span("judge_loop", input={"build_count": len(builds)})

    run_dir = RUNS_DIR / state["name"]
    score_dir = run_dir / "judge-scores"
    walks_dir = run_dir / "walks"
    score_dir.mkdir(parents=True, exist_ok=True)
    walks_dir.mkdir(parents=True, exist_ok=True)

    max_iter = state.get("judge_max_iter")
    if max_iter is None:
        max_iter = MAX_JUDGE_ITERATIONS

    threshold = state.get("judge_threshold") or JUDGE_DEFAULT_THRESHOLD

    judge_model = resolve_model("judge")
    judge_max_tokens = max_output_for(judge_model, kind="verdict")

    # Load reviewer persona + compile judge_score prompt.
    persona_path = WORKSPACE / "skills/creative-technologist/personas/REVIEWER.md"
    persona = persona_path.read_text() if persona_path.exists() else ""
    judge_score_prompt = prompts.get("judge_score")
    judge_system = judge_score_prompt.compile(persona=persona)

    # Pre-build sibling approach summaries (used in every per-build call).
    approaches = state.get("approaches", []) or []
    approach_by_idx: Dict[int, dict] = {}
    for b in builds:
        ap = _approach_for_designer(approaches, b.get("designer_id"))
        if ap is not None:
            approach_by_idx[b["index"]] = ap

    prev_status = dict(state.get("judge_status", {}) or {})
    prev_iters = dict(state.get("judge_polish_iterations", {}) or {})
    prev_scores = dict(state.get("judge_scores", {}) or {})
    new_status: Dict[int, str] = {}
    new_iters: Dict[int, int] = {}
    new_scores: Dict[int, dict] = {}

    cost_broken_now = _cost_circuit_broken(state)

    for b in builds:
        idx = b["index"]

        # Concepts that already cleared the bar in an earlier loop visit — keep them.
        if prev_status.get(idx) == "above_bar":
            new_status[idx] = "above_bar"
            new_iters[idx] = prev_iters.get(idx, 0)
            if idx in prev_scores:
                new_scores[idx] = prev_scores[idx]
            continue

        # Concepts that never made it through QA — don't score them.
        if qa_status.get(idx) in ("failed_max", "cost_circuit"):
            new_status[idx] = qa_status[idx]
            new_iters[idx] = prev_iters.get(idx, 0)
            if idx in prev_scores:
                new_scores[idx] = prev_scores[idx]
            print(f"  ⏭ concept-{idx}: skipped (qa_status={qa_status[idx]})")
            continue

        # Cost circuit: stop spending.
        if cost_broken_now or prev_status.get(idx) == "cost_circuit":
            new_status[idx] = "cost_circuit"
            new_iters[idx] = prev_iters.get(idx, 0)
            print(f"  ⛔ concept-{idx}: cost circuit broken — skipping judge score")
            continue

        # Score this concept.
        siblings = "\n\n".join(
            _summarize_approach_for_distinctiveness(approach_by_idx[other_idx])
            for other_idx in approach_by_idx
            if other_idx != idx
        )
        scores_json = _judge_score_one_build(
            b, state, score_dir, walks_dir,
            judge_model, judge_max_tokens, judge_system,
            other_approach_summaries=siblings,
        )
        new_scores[idx] = scores_json

        passes, reason = _score_meets_threshold(scores_json, threshold)
        current_iter = prev_iters.get(idx, 0)

        # Honor the model's own "verdict" field only if it matches our threshold logic;
        # otherwise our threshold check wins (model can be over-eager).
        if passes:
            new_status[idx] = "above_bar"
            new_iters[idx] = current_iter
            print(f"  ✅ concept-{idx}: ABOVE BAR — {reason}")
        else:
            if current_iter >= max_iter:
                new_status[idx] = "failed_max"
                new_iters[idx] = current_iter
                print(f"  ❌ concept-{idx}: BELOW BAR — {reason} — max iter ({max_iter}) reached")
            else:
                new_status[idx] = "pending_polish"
                new_iters[idx] = current_iter
                fixes = scores_json.get("priority_fixes", {}) or {}
                top_fixes = (fixes.get("p0_broken", []) or []) + (fixes.get("p1_must_fix", []) or [])
                print(f"  🎨 concept-{idx}: BELOW BAR — {reason} — polishing (iter {current_iter+1}/{max_iter})")
                for fx in top_fixes[:3]:
                    print(f"      → {fx}")

    above = sum(1 for s in new_status.values() if s == "above_bar")
    pending = sum(1 for s in new_status.values() if s == "pending_polish")
    failed = sum(1 for s in new_status.values() if s == "failed_max")
    cost_c = sum(1 for s in new_status.values() if s == "cost_circuit")
    print(f"[JUDGE-LOOP] Status: {above} above_bar | {pending} polishing | {failed} failed_max | {cost_c} cost_circuit")

    tracer.end_span(span, output={"above_bar": above, "pending": pending,
                                    "failed_max": failed, "cost_circuit": cost_c})

    return {
        "judge_status": new_status,
        "judge_polish_iterations": new_iters,
        "judge_scores": new_scores,
        "phase": "judge_loop",
        "cost_circuit_broken": cost_broken_now,
    }


def fan_out_judge_polish(state: PipelineState) -> list:
    """Fan out one Send per concept whose judge_status == 'pending_polish'.

    Each Send targets the builder node in builder_mode="judge_polish" using
    the ORIGINAL builder model for that concept (per-concept-model rule).
    """
    judge_status = state.get("judge_status", {}) or {}
    builds = state.get("builds", []) or []
    sends = []
    for build in builds:
        idx = build.get("index")
        if idx is None:
            continue
        if judge_status.get(idx) != "pending_polish":
            continue
        builder_model = build.get("model") or "claude-opus"
        sends.append(Send("builder", {
            **state,
            "build_index": idx,
            "builder_model": builder_model,
            "builder_mode": "judge_polish",
        }))
    return sends


def route_after_judge_loop(state: PipelineState):
    """From `judge_loop` → builder (judge_polish Sends) OR → `pairwise_rank`.

    Returns either a list of Sends (one per concept needing polish, fanning
    into `builder`) or the string `"pairwise_rank"` to advance to the final
    ordering pass.
    """
    if _cost_circuit_broken(state):
        return "pairwise_rank"
    sends = fan_out_judge_polish(state)
    if sends:
        # Iteration bumps happen inside the builder's judge_polish branch
        # (so the count reflects iterations actually attempted).
        return sends
    return "pairwise_rank"


def pairwise_rank_node(state: PipelineState) -> dict:
    """Tie-breaker pairwise ranking pass, AFTER thresholds have decided pass/fail.

    Runs the legacy bidirectional pairwise tournament *only* among above_bar
    survivors, purely for ordering in the eval app. Concepts that didn't make
    it (failed_max / cost_circuit / qa failed) are appended at the bottom of
    the ranking with rank > N(survivors).

    If <= 1 survivor exists, the ranking is trivial and we skip the
    tournament entirely.
    """
    builds = state.get("builds", []) or []
    judge_status = state.get("judge_status", {}) or {}
    judge_scores = state.get("judge_scores", {}) or {}

    survivors_idx = [b["index"] for b in builds if judge_status.get(b["index"]) == "above_bar"]
    non_survivors_idx = [b["index"] for b in builds if b["index"] not in survivors_idx]

    print(f"[PAIRWISE-RANK] {len(survivors_idx)} survivors, {len(non_survivors_idx)} non-survivors")
    span = tracer.start_span("pairwise_rank", input={
        "survivors": survivors_idx,
        "non_survivors": non_survivors_idx,
    })

    # Build a lookup of build dicts by index for convenience.
    build_by_idx = {b["index"]: b for b in builds}

    pairwise_results: list = []
    wins: Dict[int, int] = {i: 0 for i in survivors_idx}

    if len(survivors_idx) >= 2 and not _cost_circuit_broken(state):
        # Run a smaller version of the legacy bidirectional tournament — same
        # judge_system prompt as before (pairwise comparison wording), but
        # cheaper because survivors only.
        try:
            from itertools import combinations
        except Exception:
            combinations = None
        pairs = list(combinations(survivors_idx, 2)) if combinations else []

        # Reuse the existing prompt file via the prompts manager.
        judge_prompt_obj = prompts.get("judge_system")
        persona_path = WORKSPACE / "skills/creative-technologist/personas/REVIEWER.md"
        persona = persona_path.read_text() if persona_path.exists() else ""
        judge_system = judge_prompt_obj.compile(persona=persona)
        judge_model = resolve_model("judge")
        judge_max_tokens = max_output_for(judge_model, kind="verdict")

        # Walk + gather journey for survivors only.
        survivors_builds = [build_by_idx[i] for i in survivors_idx if i in build_by_idx]
        walks = walk_builds(survivors_builds, state["name"])
        journeys = {}
        for b in survivors_builds:
            walk = walks.get(b["index"], {})
            journeys[b["index"]] = {
                "walk": walk,
                "screenshots": _select_journey_screenshots(walk, max_count=WALKER_MAX_SCREENSHOTS),
            }

        # Moodboard for context.
        moodboard_dir = RUNS_DIR / state["name"] / "moodboard"
        moodboard_parts: list = []
        if moodboard_dir.exists():
            for mf in sorted([f for f in moodboard_dir.iterdir()
                              if f.suffix.lower() in [".jpg", ".jpeg", ".png"]])[:3]:
                try:
                    mb_b64 = encode_image(str(mf))
                    ext = mf.suffix.lower().lstrip(".")
                    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
                    moodboard_parts.append({"type": "image_url",
                                            "image_url": {"url": f"data:{mime};base64,{mb_b64}"}})
                except Exception:
                    pass

        def _journey_block(label: str, idx: int) -> list:
            jr = journeys.get(idx, {})
            walk = jr.get("walk", {})
            shots = jr.get("screenshots", [])
            block = [{"type": "text", "text":
                f"ARTIFACT {label} — journey: {len(shots)} screenshot(s), "
                f"{walk.get('interactive_elements_found', 0)} interactive elements, "
                f"{walk.get('clicks_attempted', 0)} clicks attempted, "
                f"{walk.get('clicks_that_changed_state', 0)} produced state changes."
            }]
            for k, s in enumerate(shots):
                cap = f"ARTIFACT {label} — screen {k+1} of {len(shots)}"
                block.append({"type": "text", "text": cap})
                try:
                    b64 = encode_image(s["screenshot"]) if s.get("screenshot") else None
                except Exception:
                    b64 = None
                if b64:
                    block.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
            return block

        for i, j in pairs:
            if _cost_circuit_broken(state):
                print(f"  ⛔ cost circuit broken — skipping pair {i} vs {j}")
                break
            for direction, (a, b) in (("forward", (i, j)), ("reverse", (j, i))):
                parts: list = []
                if moodboard_parts:
                    parts.append({"type": "text", "text": "MOODBOARD REFERENCES:"})
                    parts.extend(moodboard_parts)
                parts.append({"type": "text", "text":
                    f"Compare these two interactive prototypes.\n\n"
                    f"Brief context: {state.get('brief', '')[:500]}"
                })
                parts.extend(_journey_block("A", a))
                parts.extend(_journey_block("B", b))

                text_only = judge_system + "\n\n[USER]\n" + "\n".join(
                    p["text"] for p in parts if p.get("type") == "text"
                )

                with tracer.generation(
                    name=f"pairwise_rank_{a}v{b}_{direction}",
                    model=judge_model,
                    input=text_only,
                    prompt_obj=judge_prompt_obj,
                    model_parameters={"max_tokens": judge_max_tokens},
                    metadata={"phase": "pairwise_rank", "direction": direction, "pair": [a, b]},
                ) as gen:
                    try:
                        resp = openai_client.chat.completions.create(
                            model=judge_model,
                            max_completion_tokens=judge_max_tokens,
                            messages=[
                                {"role": "system", "content": judge_system},
                                {"role": "user", "content": parts},
                            ],
                        )
                        text = resp.choices[0].message.content or ""
                        gen.set_output(text)
                        if resp.usage:
                            gen.set_usage(input_tokens=resp.usage.prompt_tokens,
                                          output_tokens=resp.usage.completion_tokens)
                            track_cost(judge_model, resp.usage.prompt_tokens,
                                        resp.usage.completion_tokens, "pairwise_rank")
                        first = text.strip().split("\n", 1)[0].upper()
                        if direction == "forward":
                            fwd_winner = "A" if "PREFER_A" in first else ("B" if "PREFER_B" in first else "TIE")
                            fwd_reasoning = text
                        else:
                            rev_winner = "A" if "PREFER_A" in first else ("B" if "PREFER_B" in first else "TIE")
                            rev_reasoning = text
                    except Exception as e:
                        gen.set_error(str(e)[:500])
                        if direction == "forward":
                            fwd_winner, fwd_reasoning = "TIE", f"error: {e}"
                        else:
                            rev_winner, rev_reasoning = "TIE", f"error: {e}"

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
            pairwise_results.append({
                "pair": [i, j],
                "forward": fwd_winner,
                "reverse": rev_winner,
                "agreed": agreed,
                "winner": winner,
                "fwd_reasoning": fwd_reasoning,
                "rev_reasoning": rev_reasoning,
            })
            print(f"  pair {i} vs {j}: {'agreed' if agreed else 'disagreed'} → {winner if winner is not None else 'tie'}")

    # Build the final ranking:
    # 1. Survivors sorted by wins desc, then by weighted_total desc.
    survivor_ranking = sorted(
        survivors_idx,
        key=lambda i: (
            -wins.get(i, 0),
            -(judge_scores.get(i, {}).get("weighted_total") or 0.0),
        ),
    )
    # 2. Non-survivors at the bottom, sorted by their (possibly partial) weighted_total.
    non_survivor_ranking = sorted(
        non_survivors_idx,
        key=lambda i: -(judge_scores.get(i, {}).get("weighted_total") or 0.0),
    )

    ranked_indices = survivor_ranking + non_survivor_ranking
    ranked_builds = []
    for rank, idx in enumerate(ranked_indices, start=1):
        b = build_by_idx.get(idx, {})
        ranked_builds.append({
            "rank": rank,
            "build_index": idx,
            "wins": wins.get(idx, 0),
            "judge_status": judge_status.get(idx, "unknown"),
            "weighted_total": (judge_scores.get(idx, {}) or {}).get("weighted_total"),
            **b,
        })

    # Persist rank + scores together for the eval app.
    try:
        results_dir = RUNS_DIR / state["name"] / "reviews"
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "pairwise-rank.json").write_text(json.dumps({
            "pairs": pairwise_results,
            "ranking": [{"rank": r["rank"], "index": r["build_index"],
                          "wins": r["wins"], "status": r["judge_status"],
                          "weighted_total": r["weighted_total"]}
                         for r in ranked_builds],
        }, indent=2, default=str))
        (results_dir / "judge-scores.json").write_text(json.dumps(
            {str(i): judge_scores.get(i) for i in build_by_idx},
            indent=2, default=str,
        ))
    except Exception:
        pass

    print("[PAIRWISE-RANK] Final ranking:")
    for r in ranked_builds:
        wt = r["weighted_total"]
        wt_s = f"{wt:.2f}" if isinstance(wt, (int, float)) else "?"
        print(f"  #{r['rank']} — concept {r['build_index']} ({r.get('model','?')}) "
              f"— status={r['judge_status']} wins={r['wins']} weighted={wt_s}")

    for r in ranked_builds:
        try:
            tracer.score(f"build-{r['build_index']}-rank",
                          float(len(ranked_builds) - r["rank"] + 1),
                          comment=f"Rank #{r['rank']} ({r['judge_status']})")
        except Exception:
            pass

    tracer.end_span(span, output={
        "ranking": [{"rank": r["rank"], "build": r["build_index"],
                      "status": r["judge_status"], "weighted_total": r["weighted_total"]}
                     for r in ranked_builds],
    })

    return {
        "pairwise_results": pairwise_results,
        "ranking": ranked_builds,
        "phase": "pairwise_rank_complete",
    }


# Kept for fast rollback. The new graph uses qa_loop + judge_loop + pairwise_rank.
# To rollback: re-wire build_graph() to use this `pairwise_judge_node_legacy`
# (and remove the qa_loop / judge_loop / pairwise_rank nodes).
def pairwise_judge_node_legacy(state: PipelineState) -> dict:
    """LEGACY — Phase 5: Vision-based bidirectional pairwise tournament.

    Preserved verbatim (modulo the rename) for fast rollback to the previous
    qa→playability→judge→human_gate flow. Not wired into the active graph.
    """
    print(f"[JUDGE] Running vision-based pairwise tournament on {len(state['builds'])} builds")
    span = tracer.start_span("judge", input={"build_count": len(state["builds"])})
    
    builds = state["builds"]
    if len(builds) < 2:
        return {"ranking": builds, "phase": "judge_complete"}
    
    # Walk each build's experience (clicks through interactive elements,
    # captures journey screenshots, detects dead/inert prototypes).
    print(f"[JUDGE] Walking {len(builds)} builds (interactive QA + journey capture)...")
    walks = walk_builds(builds, state["name"])
    journeys = {}
    for b in builds:
        idx = b["index"]
        walk = walks.get(idx, {})
        chosen = _select_journey_screenshots(walk, max_count=WALKER_MAX_SCREENSHOTS)
        journeys[idx] = {
            "walk": walk,
            "screenshots": chosen,
        }

    # Load reviewer persona
    persona_path = WORKSPACE / "skills/creative-technologist/personas/REVIEWER.md"
    persona = persona_path.read_text() if persona_path.exists() else ""
    
    # Use OpenAI as judge (cross-model — builders are Claude/Hermes)
    judge_model = resolve_model("judge")
    judge_max_tokens = max_output_for(judge_model, kind="verdict")
    
    judge_prompt_obj = prompts.get("judge_system")
    judge_system = judge_prompt_obj.compile(persona=persona)

    # Load moodboard images for judge context (research recommendation: judge should see moodboard)
    moodboard_dir = RUNS_DIR / state["name"] / "moodboard"
    judge_moodboard_parts = []
    if moodboard_dir.exists():
        moodboard_files = sorted([f for f in moodboard_dir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png"]])
        for mf in moodboard_files[:3]:  # top 3 moodboard images for context
            try:
                mb_b64 = encode_image(str(mf))
                ext = mf.suffix.lower().lstrip(".")
                mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
                judge_moodboard_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{mb_b64}"}})
            except Exception:
                pass
        if judge_moodboard_parts:
            print(f"  📎 Judge will see {len(judge_moodboard_parts)} moodboard reference images")
    
    pairs = list(itertools.combinations(range(len(builds)), 2))
    wins = {i: 0 for i in range(len(builds))}
    results = []
    
    def _build_journey_block(label: str, idx: int) -> list:
        """Return content parts (text + image_url) describing one artifact's journey."""
        parts = []
        j = journeys.get(idx, {})
        walk = j.get("walk", {})
        shots = j.get("screenshots", [])
        signal = (
            f"ARTIFACT {label} — journey: {len(shots)} screenshot(s), "
            f"{walk.get('interactive_elements_found', 0)} interactive elements found, "
            f"{walk.get('clicks_attempted', 0)} click(s) attempted, "
            f"{walk.get('clicks_that_changed_state', 0)} produced state changes, "
            f"{walk.get('unique_states', 0)} unique states visited."
        )
        if walk.get("inert_prototype"):
            signal += " ⚠️ No interactive elements were detected — this prototype may be a static artifact."
        elif walk.get("dead_prototype"):
            signal += " ⚠️ Interactive elements were present but clicking them produced no state changes — this prototype appears non-functional."
        if walk.get("console_errors_total"):
            signal += f" {walk['console_errors_total']} console error(s) observed."
        parts.append({"type": "text", "text": signal})
        for k, s in enumerate(shots):
            caption = f"ARTIFACT {label} — screen {k + 1} of {len(shots)}"
            if k == 0:
                caption += " (initial state)"
            elif s.get("clicked_label"):
                action = (s.get("clicked_label") or "")[:60].replace("\n", " ").strip()
                if s.get("state_changed"):
                    caption += f" — after clicking “{action}”"
                else:
                    caption += f" — after clicking “{action}” (no visible state change)"
            parts.append({"type": "text", "text": caption})
            try:
                b64 = encode_image(s["screenshot"]) if s.get("screenshot") else None
            except Exception:
                b64 = None
            if b64:
                parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        return parts

    for i, j in pairs:
        print(f"  ⚖️  Comparing concept {i} vs concept {j}...")

        if not journeys.get(i, {}).get("screenshots") or not journeys.get(j, {}).get("screenshots"):
            results.append({"pair": [i, j], "agreed": False, "winner": None, "error": "missing journey"})
            continue

        # Build context with optional moodboard reference
        context_parts = []
        if judge_moodboard_parts:
            context_parts.append({"type": "text", "text": "MOODBOARD REFERENCES (the visual direction these builds should match):"})
            context_parts.extend(judge_moodboard_parts)
        context_parts.append({
            "type": "text",
            "text": (
                f"Compare these two interactive prototypes.\n\n"
                f"Brief context: {state['brief'][:500]}\n\n"
                f"For each artifact you will see an ordered sequence of screenshots representing the journey through the experience. "
                f"Evaluate both visual quality across all screenshots AND whether the experience feels functional and intentional."
            ),
        })
        context_parts.extend(_build_journey_block("A", i))
        context_parts.extend(_build_journey_block("B", j))

        text_only_summary = judge_system + "\n\n[USER]\n" + "\n".join(
            p["text"] for p in context_parts if p.get("type") == "text"
        )
        n_images = sum(1 for p in context_parts if p.get("type") == "image_url")

        # Forward direction: A=i, B=j
        fwd_messages = [{"role": "user", "content": context_parts}]

        with tracer.generation(
            name=f"judge_fwd_{i}v{j}",
            model=judge_model,
            input=text_only_summary,
            prompt_obj=judge_prompt_obj,
            model_parameters={"max_tokens": judge_max_tokens},
            metadata={"phase": "judge", "direction": "forward", "pair": [i, j],
                       "image_count": n_images},
        ) as gen:
            fwd_response = openai_client.chat.completions.create(
                model=judge_model,
                max_completion_tokens=judge_max_tokens,
                messages=[{"role": "system", "content": judge_system}] + fwd_messages,
            )
            fwd_text = fwd_response.choices[0].message.content
            gen.set_output(fwd_text)
            if fwd_response.usage:
                gen.set_usage(input_tokens=fwd_response.usage.prompt_tokens,
                              output_tokens=fwd_response.usage.completion_tokens)
                track_cost(judge_model, fwd_response.usage.prompt_tokens, fwd_response.usage.completion_tokens, "judge")

        # Reverse direction: A=j, B=i (swap which artifact is labeled A vs B)
        rev_parts = []
        if judge_moodboard_parts:
            rev_parts.append({"type": "text", "text": "MOODBOARD REFERENCES (the visual direction these builds should match):"})
            rev_parts.extend(judge_moodboard_parts)
        rev_parts.append({
            "type": "text",
            "text": (
                f"Compare these two interactive prototypes.\n\n"
                f"Brief context: {state['brief'][:500]}\n\n"
                f"For each artifact you will see an ordered sequence of screenshots representing the journey through the experience. "
                f"Evaluate both visual quality across all screenshots AND whether the experience feels functional and intentional."
            ),
        })
        rev_parts.extend(_build_journey_block("A", j))
        rev_parts.extend(_build_journey_block("B", i))
        rev_messages = [{"role": "user", "content": rev_parts}]

        with tracer.generation(
            name=f"judge_rev_{j}v{i}",
            model=judge_model,
            input=text_only_summary,
            prompt_obj=judge_prompt_obj,
            model_parameters={"max_tokens": judge_max_tokens},
            metadata={"phase": "judge", "direction": "reverse", "pair": [i, j],
                       "image_count": n_images},
        ) as gen:
            rev_response = openai_client.chat.completions.create(
                model=judge_model,
                max_completion_tokens=judge_max_tokens,
                messages=[{"role": "system", "content": judge_system}] + rev_messages,
            )
            rev_text = rev_response.choices[0].message.content
            gen.set_output(rev_text)
            if rev_response.usage:
                gen.set_usage(input_tokens=rev_response.usage.prompt_tokens,
                              output_tokens=rev_response.usage.completion_tokens)
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


def generate_eval_app_for_run(state: PipelineState) -> Optional[str]:
    """Generate and deploy mobile evaluation app for human gate.
    
    Returns deployed URL or None on failure.
    """
    run_dir = RUNS_DIR / state["name"]
    builds_dir = run_dir / "builds"
    
    if not builds_dir.exists():
        print("  ⚠️  No builds dir — skipping eval app generation")
        return None
    
    try:
        # Import the eval app generator
        sys.path.insert(0, str(PIPELINE_DIR))
        from importlib import import_module
        eval_mod_path = PIPELINE_DIR / "generate-eval-app.py"
        if not eval_mod_path.exists():
            print("  ⚠️  generate-eval-app.py not found — skipping eval app")
            return None
        
        import importlib.util
        spec = importlib.util.spec_from_file_location("generate_eval_app", str(eval_mod_path))
        eval_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eval_mod)
        
        # Generate eval app
        deploy_dir = run_dir / "eval"
        deploy_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy builds into eval dir for deployment
        eval_builds = deploy_dir / "builds"
        eval_builds.mkdir(exist_ok=True)
        for html_file in builds_dir.glob("concept-*.html"):
            import shutil
            shutil.copy2(html_file, eval_builds / html_file.name)
        
        # Inject model info into builds list
        builds_with_models = []
        ranking = state.get("ranking", [])
        model_map = {}
        for r in ranking:
            idx = r.get("build_index", r.get("index", -1))
            model_map[idx] = r.get("model", "unknown")
        
        html = eval_mod.generate_eval_html(run_dir)
        eval_html_path = deploy_dir / "index.html"
        eval_html_path.write_text(html)
        
        # Deploy via here-now
        publish_script = WORKSPACE / ".." / ".agents/skills/here-now/scripts/publish.sh"
        if publish_script.exists():
            result = subprocess.run(
                ["bash", str(publish_script), str(deploy_dir)],
                capture_output=True, text=True, timeout=60
            )
            # Parse URL from output
            for line in result.stdout.split("\n"):
                if "here.now" in line and "://" in line:
                    url = line.strip()
                    if url.startswith("https://"):
                        print(f"  🎨 Eval app deployed: {url}")
                        return url
        
        print(f"  📁 Eval app generated locally: {eval_html_path}")
        return str(eval_html_path)
        
    except Exception as e:
        print(f"  ⚠️  Eval app generation failed (non-fatal): {e}")
        return None


def load_structured_verdict(run_name: str) -> Optional[dict]:
    """Load structured verdict.json from run directory if it exists.
    
    Returns parsed verdict dict or None.
    """
    verdict_path = RUNS_DIR / run_name / "verdict.json"
    if verdict_path.exists():
        try:
            verdict = json.loads(verdict_path.read_text())
            print(f"  📋 Loaded structured verdict from {verdict_path.name}")
            return verdict
        except Exception as e:
            print(f"  ⚠️  Failed to parse verdict.json: {e}")
    return None


_VERDICT_SCORE_MAP = {"approve": 3.0, "iterate": 2.0, "reject": 1.0}
_RATING_SCORE_MAP = {"great": 3.0, "acceptable": 2.0, "bad": 1.0}
_VERDICT_DIMENSIONS = ["creative_ambition", "ai_slop", "visual_depth", "typography", "hierarchy"]


def _build_run_rollup(run_name: str, state: Optional[dict] = None,
                       extra: Optional[dict] = None) -> dict:
    """Build the Phase 3 rollup payload attached to Langfuse on end_run.

    Captures total cost, per-phase cost, all model calls (lightweight),
    builder model lineup, iteration count, design system, compliance summary,
    and final ranking. Safe to call mid-run (state may be None on bare paths).
    """
    rollup: Dict[str, Any] = {
        "run_name": run_name,
        "total_cost_usd": round(_run_costs.get("total_usd", 0.0), 4),
        "cost_by_phase": {k: round(v, 4) for k, v in _run_costs.get("by_phase", {}).items()},
        "llm_call_count": len(_run_costs.get("calls", [])),
    }

    if state:
        approaches = state.get("approaches", []) or []
        builds = state.get("builds", []) or []
        ranking = state.get("ranking", []) or []
        rollup.update({
            "iteration": state.get("iteration", 0),
            "design_system": "SMPLX" if state.get("design_system") else "none",
            "approach_count": len(approaches),
            "build_count": len(builds),
            "models_designer": [a.get("model") for a in approaches],
            "models_builder": [b.get("model") for b in builds],
            "compliance_summary": {
                "passed": sum(1 for b in builds if (b.get("compliance") or {}).get("pass")),
                "failed": sum(1 for b in builds if not (b.get("compliance") or {}).get("pass")),
            },
            "final_ranking": [
                {"rank": r.get("rank"), "build_index": r.get("build_index"),
                 "wins": r.get("wins"), "model": r.get("model"),
                 "compliance_pass": (r.get("compliance") or {}).get("pass")}
                for r in ranking
            ],
        })
    if extra:
        rollup.update(extra)
    return rollup


def _build_run_tags(state: Optional[dict] = None) -> list:
    """Build searchable tags for the trace (filter by these in Langfuse UI)."""
    tags = []
    if state:
        if state.get("design_system"):
            tags.append("smplx")
        it = state.get("iteration", 0)
        tags.append(f"iter-{it}")
        approaches = state.get("approaches", []) or []
        for a in approaches:
            m = (a.get("model") or "").lower()
            if m and f"designer:{m}" not in tags:
                tags.append(f"designer:{m}")
        builds = state.get("builds", []) or []
        for b in builds:
            m = (b.get("model") or "").lower()
            if m and f"builder:{m}" not in tags:
                tags.append(f"builder:{m}")
    return tags


def _finalize_trace_with_rollup(run_name: str, status: str,
                                  state: Optional[dict] = None,
                                  extra: Optional[dict] = None):
    """End the current Langfuse run trace with the Phase 3 rollup + tags."""
    try:
        rollup = _build_run_rollup(run_name, state, extra)
        tags = _build_run_tags(state)
        # Tags live on the underlying root span via metadata.langfuse_tags
        # (Langfuse v3 reads tags from trace-level update; we put them in metadata as a list).
        tracer.end_run(
            status=status,
            output={"rollup": rollup},
            metadata={**rollup, "tags": tags},
        )
    except Exception as e:
        print(f"  ⚠️  Failed to finalize trace rollup: {e}")
        # Fall back to a plain end_run so we don't leak open traces
        try:
            tracer.end_run(status=status, metadata={"run_name": run_name})
        except Exception:
            pass


def _push_verdict_to_langfuse(run_name: str, verdict: dict):
    """Push structured verdict scores to the Langfuse trace for this run.

    Resolves trace_id via the local registry file (langfuse-trace.json) written
    when the pipeline started. Best-effort — logs and returns on failure.
    """
    registry_path = RUNS_DIR / run_name / "langfuse-trace.json"
    if not registry_path.exists():
        print(f"  ℹ️  No langfuse-trace.json registry for {run_name} — skipping verdict push")
        return

    try:
        entries = json.loads(registry_path.read_text())
    except Exception as e:
        print(f"  ⚠️  Failed to read trace registry: {e}")
        return

    primary = next((e for e in entries if e.get("kind") == "initial"), entries[0] if entries else None)
    if not primary:
        return
    trace_id = primary["trace_id"]

    # Build score plan
    plan = []
    v = verdict.get("verdict")
    if v in _VERDICT_SCORE_MAP:
        plan.append(("verdict_decision", _VERDICT_SCORE_MAP[v],
                     f"verdict={v}; best_concept={verdict.get('best_concept')}; {verdict.get('overall_note','')}".strip()[:1000]))

    bc = verdict.get("best_concept")
    if bc is not None:
        plan.append(("best_concept_index", float(bc),
                     "Index of the best concept in this run; -1 means no winner"))

    for c in verdict.get("concepts", []):
        idx = c.get("index")
        model = c.get("model", "unknown")
        rating = c.get("rating", "unrated")
        note = (c.get("note") or "")[:1000]
        if rating in _RATING_SCORE_MAP:
            plan.append((f"concept_{idx}_rating", _RATING_SCORE_MAP[rating],
                         f"model={model}; rating={rating}; {note}"))
        for dim in _VERDICT_DIMENSIONS:
            dval = c.get("dimensions", {}).get(dim)
            if isinstance(dval, (int, float)) and dval > 0:
                plan.append((f"concept_{idx}_{dim}", float(dval),
                             f"model={model}; {dim}={dval}"))

    # Push via tracer's underlying client
    pushed = 0
    failed = 0
    if not getattr(tracer, "_enabled", False) or not getattr(tracer, "_client", None):
        print(f"  ⚠️  Langfuse not initialized — cannot push verdict")
        return
    for name, value, comment in plan:
        try:
            tracer._client.create_score(
                trace_id=trace_id,
                name=name,
                value=value,
                data_type="NUMERIC",
                comment=comment,
            )
            pushed += 1
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  ⚠️  Score push failed ({name}): {e}")
    try:
        tracer._client.flush()
    except Exception:
        pass
    print(f"  📊 Verdict → Langfuse: pushed {pushed} scores, {failed} failed (trace={trace_id[:8]})")


def append_to_calibration_set(state: PipelineState, verdict_data: dict):
    """Append structured verdict to calibration-set.json for cross-run learning.
    
    Each rated concept becomes a calibration entry.
    """
    cal_path = PIPELINE_DIR / "memory" / "calibration-set.json"
    cal_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if cal_path.exists():
            cal = json.loads(cal_path.read_text())
        else:
            cal = {
                "_schema": "calibration-set-v1",
                "rated_by": "creative-director",
                "rated_at": time.strftime("%Y-%m-%d"),
                "count": 0,
                "distribution": {"great": 0, "acceptable": 0, "bad": 0},
                "ratings": [],
                "taste_notes": {}
            }
        
        run_name = state["name"]
        run_dir = RUNS_DIR / run_name
        
        for concept in verdict_data.get("concepts", []):
            rating = concept.get("rating", "unrated")
            if rating == "unrated":
                continue
            
            # Map great→great, ok→acceptable, bad→bad
            cal_rating = {"great": "great", "ok": "acceptable", "bad": "bad"}.get(rating, rating)
            
            entry = {
                "run": run_name,
                "concept": concept.get("index", -1),
                "model": concept.get("model", "unknown"),
                "rating": cal_rating,
                "dimensions": concept.get("dimensions", {}),
                "techniques": concept.get("techniques", {}),
                "note": concept.get("note", ""),
                "timestamp": verdict_data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ")),
                "build_file": f"builds/concept-{concept.get('index', 0)}.html",
            }
            
            cal["ratings"].append(entry)
            cal["count"] = len(cal["ratings"])
            
            # Update distribution
            if cal_rating in cal["distribution"]:
                cal["distribution"][cal_rating] = sum(
                    1 for r in cal["ratings"] if r.get("rating") == cal_rating
                )
        
        cal["rated_at"] = time.strftime("%Y-%m-%d")
        cal_path.write_text(json.dumps(cal, indent=2))
        
        rated_count = sum(1 for c in verdict_data.get("concepts", []) if c.get("rating") != "unrated")
        print(f"  📊 Calibration set updated: +{rated_count} entries → {cal['count']} total")
        
    except Exception as e:
        print(f"  ⚠️  Calibration set update failed (non-fatal): {e}")


# Bug B: per-brief learnings cap. Older entries beyond this size get dropped
# from the bottom of the file (oldest = top of file in our format). 5K chars
# is enough for ~10 run entries before rotation kicks in.
PER_BRIEF_LEARNINGS_MAX_CHARS = 5000


def append_per_brief_learnings(state: dict, verdict_data: dict) -> Optional[Path]:
    """Write/append a brief-scoped learnings entry next to the brief file.

    Layout::

        memory/plans/sneaker-game-creative-brief.md
        memory/plans/sneaker-game-creative-brief.LEARNINGS.md  ← this file

    Each run appends one block to the file. When the file exceeds
    ``PER_BRIEF_LEARNINGS_MAX_CHARS``, the oldest blocks are dropped (the file
    is rewritten with the most recent blocks that fit).

    Returns the path written, or ``None`` if no ``brief_path`` was in state.
    """
    bp = _brief_path_from_state(state)
    if bp is None:
        return None

    learnings_path = bp.with_name(bp.stem + ".LEARNINGS.md")

    run_name = state.get("name", "unknown-run")
    decision = verdict_data.get("verdict", "unknown")
    overall_note = verdict_data.get("overall_note", "") or ""
    concepts = verdict_data.get("concepts", []) or []
    date = time.strftime("%Y-%m-%d")

    block_lines = [f"## Run `{run_name}` ({date}) — verdict: {decision}"]
    if overall_note:
        block_lines.append(f"> {overall_note[:300]}")
    if concepts:
        block_lines.append("")
        for c in concepts:
            idx = c.get("index", "?")
            model = c.get("model", "?")
            rating = c.get("rating", "unrated")
            note = (c.get("note", "") or "")[:160]
            block_lines.append(f"- C{idx} ({model}) — {rating}{(': ' + note) if note else ''}")
            stand = [t for t, s in (c.get("techniques", {}) or {}).items() if s == "standout"]
            missed = [t for t, s in (c.get("techniques", {}) or {}).items() if s == "missed"]
            if stand:
                block_lines.append(f"    - standout: {', '.join(stand[:4])}")
            if missed:
                block_lines.append(f"    - missed: {', '.join(missed[:4])}")
    new_block = "\n".join(block_lines) + "\n\n"

    # Preamble for fresh files — makes them readable on their own.
    if not learnings_path.exists():
        header = (
            f"# Brief-Specific Learnings\n\n"
            f"_Auto-generated by the pipeline (Bug B). Loaded by `get_wiki_context()` on\n"
            f"subsequent runs of this brief. Most recent runs at the bottom; older runs\n"
            f"rotate off the top once the file exceeds ~{PER_BRIEF_LEARNINGS_MAX_CHARS} chars._\n\n"
            f"Source brief: `{bp.name}`\n\n"
            f"---\n\n"
        )
        content = header + new_block
    else:
        content = learnings_path.read_text().rstrip() + "\n\n" + new_block

    # Rotate oldest entries off if we're over budget.
    if len(content) > PER_BRIEF_LEARNINGS_MAX_CHARS:
        # Split on the run-block delimiter, keep header + most recent blocks.
        if "\n---\n\n" in content:
            head, _, body = content.partition("\n---\n\n")
            head = head + "\n---\n\n"
        else:
            head, body = "", content
        # Split body by '## Run ' markers (keep marker on each chunk).
        marker = "## Run `"
        chunks = body.split(marker)
        # chunks[0] is anything before the first '## Run' (likely empty or partial)
        rebuilt_blocks = [marker + ch for ch in chunks if ch.strip()]
        # Drop oldest blocks until we fit.
        while rebuilt_blocks and len(head + "".join(rebuilt_blocks)) > PER_BRIEF_LEARNINGS_MAX_CHARS:
            rebuilt_blocks.pop(0)
        content = head + "".join(rebuilt_blocks)

    learnings_path.write_text(content)
    print(f"  📝 Wrote per-brief learnings: {learnings_path.name} ({len(content)} chars)")
    return learnings_path


def wiki_ingest_structured(state: dict, verdict_data: dict):
    """Enhanced wiki ingest using structured verdict data.
    
    Routes per-concept, per-dimension, per-technique feedback to wiki pages.
    Falls back to basic wiki_ingest if structured data is incomplete.
    """
    import re
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    
    run_name = state["name"]
    decision = verdict_data.get("verdict", "reject")
    overall_note = verdict_data.get("overall_note", "")
    concepts = verdict_data.get("concepts", [])
    ranking = state.get("ranking", [])
    cost = state.get("cost_usd", 0)
    iteration = state.get("iteration", 0)
    design_system = "SMPLX" if state.get("design_system") else "none"
    
    # 1. Write detailed run summary
    runs_dir = WIKI_DIR / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    
    summary_lines = [f"# Run: {run_name}", ""]
    summary_lines.append(f"- **Date:** {time.strftime('%Y-%m-%d %H:%M')}")
    summary_lines.append(f"- **Verdict:** {decision}")
    summary_lines.append(f"- **Iteration:** {iteration}")
    summary_lines.append(f"- **Cost:** ${cost:.2f}")
    summary_lines.append(f"- **Design System:** {design_system}")
    summary_lines.append(f"- **Best Concept:** {verdict_data.get('best_concept', '?')}")
    summary_lines.append("")
    
    if overall_note:
        summary_lines.append(f"## Overall Note")
        summary_lines.append(f"> {overall_note}")
        summary_lines.append("")
    
    # Per-concept structured feedback
    summary_lines.append("## Concepts (Structured Feedback)")
    for c in concepts:
        idx = c.get("index", "?")
        model = c.get("model", "unknown")
        rating = c.get("rating", "unrated")
        rating_emoji = {"great": "🔥", "ok": "✅", "bad": "❌"}.get(rating, "⬜")
        
        summary_lines.append(f"\n### Concept {idx} ({model}) — {rating_emoji} {rating}")
        
        dims = c.get("dimensions", {})
        if dims:
            summary_lines.append("**Dimensions:**")
            for k, v in dims.items():
                label = k.replace("_", " ").title()
                dots = "●" * v + "○" * (5 - v) if isinstance(v, int) else str(v)
                summary_lines.append(f"- {label}: {dots} ({v}/5)")
        
        techs = c.get("techniques", {})
        if techs:
            summary_lines.append("**Techniques:**")
            tech_icons = {"landed": "✅", "standout": "🔥", "partial": "⚠️", "missed": "❌"}
            for tech, status in techs.items():
                summary_lines.append(f"- {tech_icons.get(status, '○')} {tech} → {status}")
        
        note = c.get("note", "")
        if note:
            summary_lines.append(f"**CD Note:** > \"{note}\"")
        summary_lines.append("")
    
    run_summary_path = runs_dir / f"{run_name}.md"
    run_summary_path.write_text("\n".join(summary_lines))
    
    # 2. Update log
    log_path = WIKI_DIR / "log.md"
    log_entry = f"\n## [{time.strftime('%Y-%m-%d')}] ingest | {run_name}\n"
    log_entry += f"Verdict: {decision}. Cost: ${cost:.2f}. "
    ratings_summary = ", ".join(
        f"C{c['index']}({c.get('model','?')})={c.get('rating','?')}" for c in concepts
    )
    log_entry += f"Ratings: {ratings_summary}. "
    if overall_note:
        log_entry += f'Note: "{overall_note[:100]}"'
    log_entry += "\n"
    
    if log_path.exists():
        with open(log_path, "a") as f:
            f.write(log_entry)
    
    # 3. Route technique feedback to technique pages
    for c in concepts:
        for tech_name, status in c.get("techniques", {}).items():
            tech_slug = tech_name.lower().replace(" ", "-").replace("/", "-")
            tech_path = WIKI_DIR / f"techniques/{tech_slug}.md"
            
            evidence = f"- [{status}] Run {run_name}, Concept {c['index']} ({c.get('model', '?')})"
            if c.get("note"):
                evidence += f" — \"{c['note'][:100]}\""
            evidence += f" ({time.strftime('%Y-%m-%d')})"
            
            if tech_path.exists():
                content = tech_path.read_text()
                if "## Evidence" in content:
                    content = content.replace("## Evidence", f"## Evidence\n{evidence}")
                else:
                    content = content.rstrip() + f"\n\n## Evidence\n{evidence}\n"
                tech_path.write_text(content)
            else:
                # Create new technique page
                status_map = {"standout": "proven", "landed": "promising", "partial": "experimental", "missed": "untested"}
                new_page = f"# Technique: {tech_name}\n\n"
                new_page += f"**Status:** {status_map.get(status, 'experimental')}\n\n"
                new_page += f"## Evidence\n{evidence}\n"
                tech_path.write_text(new_page)
    
    # 4. Route dimension feedback to model pages + aesthetic pages
    for c in concepts:
        model = c.get("model", "unknown")
        model_name = {
            "claude-opus": "claude-opus",
            "gpt-5.4": "gpt-5.4",
            "gemini-3.1-pro": "gemini-3.1-pro",
            "gemini-3.1-pro-preview": "gemini-3.1-pro",
            "gemini-pro-latest": "gemini-3.1-pro",
        }.get(model, model)
        
        model_page = WIKI_DIR / f"models/{model_name}.md"
        if model_page.exists():
            content = model_page.read_text()
            rating = c.get("rating", "unrated")
            rating_emoji = {"great": "🔥", "ok": "✅", "bad": "❌"}.get(rating, "⬜")
            dims = c.get("dimensions", {})
            dims_str = "/".join(f"{v}" for v in dims.values()) if dims else "—"
            note_snippet = c.get("note", "")[:80]
            
            new_row = f"| {run_name} | Builder {c['index']} | {rating_emoji} {rating} | {decision} | {dims_str} | {note_snippet} |"
            
            if "## Performance History" in content:
                content = content.rstrip() + f"\n{new_row}\n"
                model_page.write_text(content)
        
        # Update anti-patterns from bad-rated concepts
        dims = c.get("dimensions", {})
        note = c.get("note", "")
        rating = c.get("rating", "unrated")
        
        if rating == "bad" and note:
            ap_path = WIKI_DIR / "aesthetics/anti-patterns.md"
            if ap_path.exists():
                content = ap_path.read_text()
                entry = f"\n### {run_name} C{c['index']} ({model}) — auto-ingested\n"
                entry += f"- **Rating:** ❌ bad\n"
                entry += f"- **CD Note:** > \"{note[:200]}\"\n"
                low_dims = [k.replace("_", " ").title() for k, v in dims.items() if isinstance(v, int) and v <= 2]
                if low_dims:
                    entry += f"- **Weak dimensions:** {', '.join(low_dims)}\n"
                entry += f"- **Date:** {time.strftime('%Y-%m-%d')}\n"
                content = content.rstrip() + "\n" + entry
                ap_path.write_text(content)
        
        # Update what-scores-well from great-rated concepts
        if rating == "great" and note:
            ws_path = WIKI_DIR / "aesthetics/what-scores-well.md"
            if ws_path.exists():
                content = ws_path.read_text()
                entry = f"\n### {run_name} C{c['index']} ({model}) — auto-ingested\n"
                entry += f"- **Rating:** 🔥 great\n"
                entry += f"- **Dimensions:** {', '.join(f'{k.replace(chr(95), chr(32)).title()} {v}/5' for k, v in dims.items())}\n"
                entry += f"- **CD Note:** > \"{note[:200]}\"\n"
                standout_techs = [t for t, s in c.get("techniques", {}).items() if s == "standout"]
                if standout_techs:
                    entry += f"- **Standout techniques:** {', '.join(standout_techs)}\n"
                entry += f"- **Date:** {time.strftime('%Y-%m-%d')}\n"
                content = content.rstrip() + "\n" + entry
                ws_path.write_text(content)
    
    # 5. Update wiki index
    index_path = WIKI_DIR / "index.md"
    if index_path.exists():
        content = index_path.read_text()
        if run_name not in content:
            if "## Run Summaries" in content:
                content = content.replace(
                    "## Run Summaries",
                    f"## Run Summaries\n- [{run_name}](runs/{run_name}.md) — {decision}"
                )
            index_path.write_text(content)
    
    rated = sum(1 for c in concepts if c.get("rating") != "unrated")
    techniques_routed = sum(len(c.get("techniques", {})) for c in concepts)
    print(f"  📚 Wiki ingested (structured): {rated} rated concepts, {techniques_routed} technique tags routed")

    # 5.5 Bug B: write per-brief LEARNINGS.md next to the brief file.
    # This is what get_wiki_context() loads on the NEXT run of the same brief.
    try:
        append_per_brief_learnings(state, verdict_data)
    except Exception as e:
        print(f"  ⚠️  per-brief learnings write failed (non-fatal): {e}")

    # 6. Check if it's time for a persona amendment proposal (every 5 runs)
    try:
        generate_persona_amendment_proposal(run_name)
    except Exception as e:
        print(f"  ⚠️  Persona amendment check failed (non-fatal): {e}")


def generate_persona_amendment_proposal(current_run: str):
    """Every 5 runs, generate a proposal for persona file updates.
    
    Reads accumulated wiki evidence and proposes specific edits to
    BUILDER.md and REVIEWER.md. Saved as a proposal file for human review.
    Does NOT auto-apply — human gate required (Constitutional AI pattern).
    """
    proposals_dir = WIKI_DIR / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    
    # Count runs in wiki log
    log_path = WIKI_DIR / "log.md"
    if not log_path.exists():
        return
    
    log_content = log_path.read_text()
    run_count = log_content.count("] ingest |")
    
    # Only generate every 5 runs
    if run_count % 5 != 0 or run_count == 0:
        return
    
    print(f"  📝 Generating persona amendment proposal (run #{run_count})...")
    
    # Collect evidence from wiki
    evidence = {"what_works": "", "anti_patterns": "", "model_notes": ""}
    
    ws_path = WIKI_DIR / "aesthetics/what-scores-well.md"
    if ws_path.exists():
        evidence["what_works"] = ws_path.read_text()[-3000:]  # Recent entries
    
    ap_path = WIKI_DIR / "aesthetics/anti-patterns.md"
    if ap_path.exists():
        evidence["anti_patterns"] = ap_path.read_text()[-3000:]
    
    # Collect recent technique evidence
    tech_evidence = []
    tech_dir = WIKI_DIR / "techniques"
    if tech_dir.exists():
        for tp in tech_dir.glob("*.md"):
            content = tp.read_text()
            if "standout" in content.lower() or "missed" in content.lower():
                tech_evidence.append(f"### {tp.stem}\n{content[-500:]}")
    
    # Read current personas
    builder_path = WORKSPACE / "skills/creative-technologist/personas/BUILDER.md"
    reviewer_path = WORKSPACE / "skills/creative-technologist/personas/REVIEWER.md"
    
    builder_current = builder_path.read_text() if builder_path.exists() else ""
    reviewer_current = reviewer_path.read_text() if reviewer_path.exists() else ""
    
    # Generate proposal document
    proposal = f"""# Persona Amendment Proposal — Run #{run_count}
Generated: {time.strftime('%Y-%m-%d %H:%M')}
Trigger: {current_run} (every 5 runs)

## Status: PENDING HUMAN REVIEW
⚠️ Do NOT auto-apply. Review each proposed change and approve/reject individually.

---

## Evidence Summary (from wiki)

### What Scores Well (recent)
{evidence['what_works'][-1500:] if evidence['what_works'] else '(no data)'}

### Anti-Patterns (recent)
{evidence['anti_patterns'][-1500:] if evidence['anti_patterns'] else '(no data)'}

### Technique Evidence
{chr(10).join(tech_evidence[-5:]) if tech_evidence else '(no technique data)'}

---

## Proposed Changes to BUILDER.md

Review the evidence above and consider whether BUILDER.md should be updated with:

1. **New anti-patterns to add to builder's "don't do" list:**
   - [Review anti-patterns above — any new patterns that builders keep hitting?]

2. **New techniques to emphasize:**
   - [Review what-scores-well — any techniques that consistently get "standout" tags?]

3. **New build rules based on failures:**
   - [Review technique evidence — any "missed" techniques that should become harder requirements?]

### Current BUILDER.md (first 2000 chars for reference):
```
{builder_current[:2000]}
```

---

## Proposed Changes to REVIEWER.md

Review the evidence above and consider whether REVIEWER.md should be updated with:

1. **Scoring weight adjustments:**
   - [Has the CD's dimension scoring pattern shifted? e.g., hierarchy consistently rated higher than ambition]

2. **New evaluation criteria:**
   - [Any new dimensions emerging from technique tags?]

3. **Calibration drift:**
   - [Are "great" ratings becoming more/less common? Are the criteria changing?]

### Current REVIEWER.md (first 2000 chars for reference):
```
{reviewer_current[:2000]}
```

---

## How to Apply

1. Read this proposal
2. For each suggested change, decide: apply / skip / modify
3. Edit the persona files directly
4. Mark this proposal as APPLIED or REJECTED
5. Commit changes

"""
    
    proposal_path = proposals_dir / f"proposal-run-{run_count}.md"
    proposal_path.write_text(proposal)
    print(f"  📝 Persona amendment proposal saved: {proposal_path.name}")
    print(f"     Review it and apply approved changes to BUILDER.md / REVIEWER.md")


def human_gate_node(state: PipelineState) -> Command:
    """Phase 7: Pause for human taste review.
    
    Auto-generates and deploys mobile eval app, then pauses.
    On resume: reads structured verdict.json if available, auto-ingests to wiki + calibration.
    """
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
    
    # Save cost report before pausing
    save_cost_report(state["name"])
    
    # Auto-generate and deploy eval app
    eval_url = generate_eval_app_for_run(state)
    
    print(f"\nBuilds at: {RUNS_DIR / state['name'] / 'builds'}")
    if eval_url:
        print(f"Eval app: {eval_url}")
    print(f"{'='*60}\n")
    
    # This pauses the pipeline until resumed
    decision = interrupt({
        "action": "taste_gate",
        "ranking": state.get("ranking", []),
        "pairwise_results": state.get("pairwise_results", []),
        "builds_dir": str(RUNS_DIR / state["name"] / "builds"),
        "eval_url": eval_url,
        "iteration": state.get("iteration", 0),
        "message": f"Review builds at eval app: {eval_url or 'N/A'}. Submit verdict.json to run dir, then resume.",
    })
    
    human_decision = decision.get("decision", "reject") if isinstance(decision, dict) else str(decision)
    human_feedback = decision.get("feedback", "") if isinstance(decision, dict) else ""
    
    # Check for structured verdict.json (auto-written by eval app flow)
    structured_verdict = load_structured_verdict(state["name"])
    
    if structured_verdict:
        # Override decision/feedback from structured verdict
        human_decision = structured_verdict.get("verdict", human_decision)
        human_feedback = structured_verdict.get("overall_note", human_feedback)
        
        # Per-concept notes as combined feedback if no overall note
        if not human_feedback:
            concept_notes = [
                f"C{c['index']}: {c['note']}" 
                for c in structured_verdict.get("concepts", []) if c.get("note")
            ]
            human_feedback = " | ".join(concept_notes)
    
    # Langfuse: score the run with human decision
    decision_scores = {"approve": 1.0, "iterate": 0.5, "reject": 0.0}
    tracer.score("human_decision", decision_scores.get(human_decision, 0.0),
                 comment=f"{human_decision}: {human_feedback[:200]}")
    
    # Record verdict to technique registry (legacy — kept for backwards compat)
    record_verdict(
        run_name=state["name"],
        decision=human_decision,
        feedback=human_feedback,
        ranking=state.get("ranking", []),
        builds=state.get("builds", []),
        approaches=state.get("approaches", []),
    )
    
    # Push verdict to Langfuse as scores (Phase 2 — auto-fire on every verdict)
    if structured_verdict:
        try:
            _push_verdict_to_langfuse(state["name"], structured_verdict)
        except Exception as e:
            print(f"  ⚠️  Langfuse verdict push failed (non-fatal): {e}")

    # Ingest into wiki — use structured version if available, else basic
    try:
        if structured_verdict:
            wiki_ingest_structured(state, structured_verdict)
            append_to_calibration_set(state, structured_verdict)
        else:
            wiki_ingest(state, human_decision, human_feedback)
    except Exception as e:
        print(f"  ⚠️  Wiki ingest failed (non-fatal): {e}")
    
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
        # Reset playability tracking so the next pass re-runs the loop
        # from scratch against the freshly-built concepts.
        "playability_signals": {},
        "playability_iterations": {},
        "playability_status": {},
        "playability_patches": {},
        # Reset the new QA + Judge loop state so each pass starts fresh.
        "qa_iterations": {},
        "qa_status": {},
        "qa_reports_by_concept": {},
        "judge_scores": {},
        "judge_polish_iterations": {},
        "judge_status": {},
        "cost_circuit_broken": False,
        "builder_mode": None,  # reset so the next pass starts in "initial" mode
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
    graph.add_node("asset_gen", asset_gen_node)
    graph.add_node("builder", builder_node)
    # New loop nodes (2026-05-13 refactor)
    graph.add_node("qa_loop", qa_loop_node)
    graph.add_node("judge_loop", judge_loop_node)
    graph.add_node("pairwise_rank", pairwise_rank_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("iterate", iterate_node)
    graph.add_node("deploy", deploy_node)

    # Edges
    graph.add_edge(START, "research")
    graph.add_conditional_edges("research", fan_out_designers, ["designer"])
    graph.add_edge("designer", "approach_gate")
    graph.add_edge("approach_gate", "asset_gen")
    # Initial builder fan-out (mode="initial")
    graph.add_conditional_edges("asset_gen", fan_out_builders, ["builder"])
    # builder → qa_loop (initial / qa_fix) OR judge_loop (judge_polish)
    graph.add_conditional_edges("builder", route_after_builder, ["qa_loop", "judge_loop"])
    # qa_loop → builder (qa_fix Sends) OR judge_loop
    graph.add_conditional_edges("qa_loop", route_after_qa_loop, ["builder", "judge_loop"])
    # judge_loop → builder (judge_polish Sends) OR pairwise_rank
    graph.add_conditional_edges("judge_loop", route_after_judge_loop, ["builder", "pairwise_rank"])
    graph.add_edge("pairwise_rank", "human_gate")
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
    run_parser.add_argument("--design-system", default=None, help="Path to design system tokens file (e.g., smplx-design-system.md)")
    run_parser.add_argument("--playability-iter", type=int, default=MAX_PLAYABILITY_ITERATIONS,
                            help=f"(LEGACY) Max playability-loop iterations per build (default {MAX_PLAYABILITY_ITERATIONS}). Folded into QA loop.")
    run_parser.add_argument("--qa-iter", type=int, default=MAX_QA_ITERATIONS,
                            help=f"Max QA-loop iterations per concept (default {MAX_QA_ITERATIONS}). Set 0 to skip the QA loop entirely.")
    run_parser.add_argument("--judge-iter", type=int, default=MAX_JUDGE_ITERATIONS,
                            help=f"Max judge-polish iterations per concept (default {MAX_JUDGE_ITERATIONS}). Set 0 to skip the judge polish loop entirely.")
    run_parser.add_argument("--max-cost", type=float, default=MAX_COST_USD,
                            help=f"Cost circuit breaker in USD (default {MAX_COST_USD}). Loops stop spending past this.")
    run_parser.add_argument("--judge-threshold-total", type=float, default=JUDGE_DEFAULT_THRESHOLD["weighted_total"],
                            help="Judge threshold: weighted total a concept must clear (default 7.0).")
    run_parser.add_argument("--judge-threshold-min-dim", type=float, default=JUDGE_DEFAULT_THRESHOLD["min_dimension"],
                            help="Judge threshold: minimum dimension score (default 5.0).")
    
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
        
        # Load design system if specified
        design_system = None
        if getattr(args, 'design_system', None):
            ds_path = Path(args.design_system)
            if not ds_path.exists():
                # Try references dir
                ds_path = WORKSPACE / "skills/creative-technologist/references" / args.design_system
            if ds_path.exists():
                design_system = ds_path.read_text()
                print(f"📐 Design system loaded: {ds_path.name} ({len(design_system)//1024}KB)")
            else:
                print(f"⚠️  Design system not found: {args.design_system}")
        
        initial_state = {
            "name": args.name,
            "brief": brief,
            "brief_path": str(brief_path.resolve()),  # Bug B: per-brief LEARNINGS.md lookup
            "research": None,
            "diversification_axes": None,  # Bug A: populated by research_node
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
            "design_system": design_system,
            "playability_signals": {},
            "playability_iterations": {},
            "playability_status": {},
            "playability_patches": {},
            "playability_max_iter": int(getattr(args, "playability_iter", MAX_PLAYABILITY_ITERATIONS)),
            # New QA + Judge loop state
            "qa_iterations": {},
            "qa_status": {},
            "qa_reports_by_concept": {},
            "qa_max_iter": int(getattr(args, "qa_iter", MAX_QA_ITERATIONS)),
            "judge_scores": {},
            "judge_polish_iterations": {},
            "judge_status": {},
            "judge_max_iter": int(getattr(args, "judge_iter", MAX_JUDGE_ITERATIONS)),
            "judge_threshold": {
                "weighted_total": float(getattr(args, "judge_threshold_total", JUDGE_DEFAULT_THRESHOLD["weighted_total"])),
                "min_dimension": float(getattr(args, "judge_threshold_min_dim", JUDGE_DEFAULT_THRESHOLD["min_dimension"])),
                "ai_slop_hardcap": JUDGE_DEFAULT_THRESHOLD["ai_slop_hardcap"],
            },
            "cost_circuit_broken": False,
        }
        # Honor --max-cost by mutating the module-level constant before the run
        # starts. (We can't pass it into track_cost otherwise.)
        try:
            requested_max_cost = float(getattr(args, "max_cost", MAX_COST_USD))
            if requested_max_cost > 0:
                globals()["MAX_COST_USD"] = requested_max_cost
                print(f"💰 Cost circuit breaker set to ${MAX_COST_USD:.2f}")
        except Exception:
            pass
        
        config["configurable"]["thread_id"] = args.name
        
        # Initialize Langfuse tracing
        tracer.init()
        trace_id = tracer.start_run(args.name, brief)
        # Persist trace_id registry next to the run for verdict pusher / Phase 2
        if trace_id:
            try:
                registry_path = RUNS_DIR / args.name / "langfuse-trace.json"
                registry_path.parent.mkdir(parents=True, exist_ok=True)
                existing = []
                if registry_path.exists():
                    existing = json.loads(registry_path.read_text())
                existing.append({
                    "trace_id": trace_id,
                    "run_name": args.name,
                    "kind": "initial",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
                registry_path.write_text(json.dumps(existing, indent=2))
            except Exception as e:
                print(f"  ⚠️  Failed to write langfuse-trace.json: {e}")
        
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
        
        # Phase 3: rollup cost + run metadata into the final trace
        try:
            final_state = app.get_state(config)
            final_values = final_state.values if final_state else None
        except Exception:
            final_values = None
        _finalize_trace_with_rollup(args.name, status="paused_or_completed", state=final_values)
        print(f"\n✅ Pipeline paused or completed. Resume with:")
        print(f"  python pipeline.py resume --thread {args.name} --decision approve")
    
    elif args.command == "resume":
        tracer.init()
        resume_trace_id = tracer.start_run(f"{args.thread}-resume", metadata={"decision": args.decision, "feedback": args.feedback})
        if resume_trace_id:
            try:
                registry_path = RUNS_DIR / args.thread / "langfuse-trace.json"
                registry_path.parent.mkdir(parents=True, exist_ok=True)
                existing = []
                if registry_path.exists():
                    existing = json.loads(registry_path.read_text())
                existing.append({
                    "trace_id": resume_trace_id,
                    "run_name": args.thread,
                    "kind": f"resume-{args.decision}",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
                registry_path.write_text(json.dumps(existing, indent=2))
            except Exception as e:
                print(f"  ⚠️  Failed to update langfuse-trace.json: {e}")
        print(f"\n🔄 Resuming pipeline: {args.thread}")
        print(f"Decision: {args.decision}")
        
        resume_value = {"decision": args.decision, "feedback": args.feedback}

        for event in app.stream(Command(resume=resume_value), config, stream_mode="updates"):
            for node, update in event.items():
                phase = update.get("phase", "")
                if phase:
                    print(f"  → {node}: {phase}")

        # Phase 3: rollup at end of resume
        try:
            final_state = app.get_state(config)
            final_values = final_state.values if final_state else None
        except Exception:
            final_values = None
        _finalize_trace_with_rollup(
            args.thread,
            status=f"resume-{args.decision}",
            state=final_values,
            extra={"decision": args.decision, "feedback": (args.feedback or "")[:500]},
        )
    
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
