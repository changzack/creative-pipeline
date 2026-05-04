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
    "gpt-5.4": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-3.1-pro-preview": {"input": 2.0, "output": 12.0},
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
    
    # QA
    qa_reports: list[dict]
    
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
            "gemini": "gemini-3.1-pro",
            "gemini-3.1-pro-preview": "gemini-3.1-pro",
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


def get_wiki_context(brief: str, max_chars: int = 8000) -> str:
    """Load relevant wiki pages as context for pipeline agents.
    
    Reads compiled knowledge from the wiki instead of raw techniques.json.
    Returns a formatted string to inject into agent prompts.
    """
    context_parts = []
    
    # Always include: what scores well + anti-patterns (taste model)
    for page in ["aesthetics/what-scores-well.md", "aesthetics/anti-patterns.md"]:
        page_path = WIKI_DIR / page
        if page_path.exists():
            content = page_path.read_text()
            context_parts.append(content)
    
    # Include overview
    overview_path = WIKI_DIR / "overview.md"
    if overview_path.exists():
        context_parts.append(overview_path.read_text())
    
    # Include relevant technique pages
    tech_dir = WIKI_DIR / "techniques"
    if tech_dir.exists():
        for tech_page in sorted(tech_dir.glob("*.md")):
            content = tech_page.read_text()
            # Only include proven/promising techniques
            if "Status: proven" in content or "Status: promising" in content:
                context_parts.append(content)
    
    combined = "\n\n---\n\n".join(context_parts)
    
    # Respect max_chars budget
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
        "gpt-5": (10.0, 30.0),                  # estimated
        "gpt-5.4": (2.50, 10.0),               # per 1M tokens
        "gemini-2.5-pro": (1.25, 10.0),         # per 1M tokens
        "gemini-3.1-pro-preview": (2.0, 12.0),  # per 1M tokens
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
    wiki_context = get_wiki_context(state["brief"])
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
    tactics = load_reference("enhancement-tactics.md")
    techniques_index = load_reference("advanced-techniques.md")
    contract_template = load_reference("design-contract-template.md")
    wiki_context = get_wiki_context(state["brief"])
    
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
        f"## Designer {a['designer_id']} ({a['model']})\n{a['content']}"
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
    """Fan out to 3 parallel builder nodes, each with a different model assignment."""
    model_assignments = ["claude-opus", "gpt-5.4", "gemini-3.1-pro-preview"]
    builders = []
    for i in range(len(state["approaches"])):
        model = model_assignments[i % len(model_assignments)]
        builders.append(Send("builder", {**state, "build_index": i, "builder_model": model}))
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
            
            response = openai_client.chat.completions.create(
                model=model,
                max_completion_tokens=32000,
                messages=messages,
            )
            html = response.choices[0].message.content
            if response.usage:
                track_cost(model, response.usage.prompt_tokens, response.usage.completion_tokens, "builder")
                
        elif model.startswith("gemini"):
            from google import genai as google_genai
            gemini_client = google_genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
            gemini_model_id = "gemini-3.1-pro-preview"
            
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
                config={"max_output_tokens": 32000},
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
                        max_completion_tokens=32000,
                        messages=[{"role": "user", "content": prompt + "\n\nRespond with ONLY the complete HTML file content. No markdown fences, no explanation. Start with <!DOCTYPE html>."}],
                    )
                    html = response.choices[0].message.content
                    if response.usage:
                        track_cost(model, response.usage.prompt_tokens, response.usage.completion_tokens, "builder")
                elif model.startswith("gemini"):
                    from google import genai as google_genai
                    gemini_client = google_genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
                    response = gemini_client.models.generate_content(
                        model="gemini-3.1-pro-preview",
                        contents=prompt + "\n\nRespond with ONLY the complete HTML file content. No markdown fences, no explanation. Start with <!DOCTYPE html>.",
                        config={"max_output_tokens": 32000},
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
    recipes = load_reference("recipes.md")
    
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
        
        assets_ref = f"""
## 🎨 GENERATED VISUAL ASSETS (CRITICAL — USE THESE)

You have pre-generated visual assets. Reference them using the `asset://` prefix shown below.
After you write the HTML, a post-processor will replace every `asset://name` with the actual
base64-encoded image data, making the HTML fully self-contained.

Do NOT use CSS gradients, colored divs, or placeholder boxes where an asset exists.
Do NOT try to base64-encode images yourself — just use `asset://name` references.

{asset_ref_block if asset_ref_block else assets_md.read_text()}

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

{"## ⛔ DESIGN SYSTEM ENFORCEMENT (automated checking — violations = rejection)" + chr(10) + "Your build will be scanned for design system compliance. ONLY the following fonts and colors are allowed:" + chr(10) + state.get('design_system', '') + chr(10) + "Any font-family not in this system = REJECTION. Any hex color not in this palette (or within tolerance) = REJECTION." + chr(10) if state.get('design_system') else ""}## Build Rules
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
    
    # Route to appropriate builder based on model
    if builder_model.startswith("gpt") or builder_model.startswith("gemini"):
        # Direct API — model generates HTML directly, with moodboard + asset vision
        result = build_direct_api(builder_model, task, build_path, state["name"], moodboard_images=all_vision_images)
    else:
        # Hermes (Claude) — agent with tool use
        result = run_hermes(f"{state['name']}-builder-{idx}", task, max_time=1800, max_turns=50)
    
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
        }],
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
        
        if build.get("model", "").startswith("gpt") or build.get("model", "").startswith("gemini"):
            # Direct API fix
            try:
                html_content = build_path.read_text()
                fix_response = openai_client.chat.completions.create(
                    model="gpt-5.4" if "gpt" in build.get("model", "") else "gemini-3.1-pro-preview",
                    max_completion_tokens=32000,
                    messages=[
                        {"role": "system", "content": "You are fixing HTML/CSS/JS issues in a build. Output ONLY the complete fixed HTML file, no explanation."},
                        {"role": "user", "content": f"{fix_prompt}\n\nCurrent HTML:\n```html\n{html_content[:30000]}\n```"},
                    ],
                )
                fixed_html = fix_response.choices[0].message.content
                # Extract HTML from markdown code block if present
                if "```html" in fixed_html:
                    fixed_html = fixed_html.split("```html")[1].split("```")[0]
                elif "```" in fixed_html:
                    fixed_html = fixed_html.split("```")[1].split("```")[0]
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

Use the Calibrated Scoring Weights from your persona to evaluate.
Start skeptical. Most AI prototypes are mediocre. A "winner" of a mediocre pair is still mediocre.
If both are bad, say so — but you MUST still pick the less-bad one.

YOU MUST CHOOSE. Respond with EXACTLY one line first: PREFER_A or PREFER_B
TIE is NOT allowed unless the artifacts are pixel-identical. There is always a less-bad option.
Then explain in 3-5 sentences WHY, citing specific visual elements you see in the screenshots."""

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
    
    for i, j in pairs:
        print(f"  ⚖️  Comparing concept {i} vs concept {j}...")
        
        img_i = encode_image(screenshots[i]) if screenshots[i] else None
        img_j = encode_image(screenshots[j]) if screenshots[j] else None
        
        if not img_i or not img_j:
            results.append({"pair": [i, j], "agreed": False, "winner": None, "error": "missing screenshot"})
            continue
        
        # Build context with optional moodboard reference
        context_parts = []
        if judge_moodboard_parts:
            context_parts.append({"type": "text", "text": "MOODBOARD REFERENCES (the visual direction these builds should match):"})
            context_parts.extend(judge_moodboard_parts)
        context_parts.append({"type": "text", "text": f"Compare these two share card prototypes.\n\nBrief context: {state['brief'][:500]}\n\nImage 1 is ARTIFACT A. Image 2 is ARTIFACT B."})
        context_parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_i}"}})
        context_parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_j}"}})
        
        # Forward direction: A=i, B=j
        fwd_messages = [{"role": "user", "content": context_parts}]
        
        fwd_response = openai_client.chat.completions.create(
            model=judge_model,
            max_tokens=600,
            messages=[{"role": "system", "content": judge_system}] + fwd_messages,
        )
        fwd_text = fwd_response.choices[0].message.content
        if fwd_response.usage:
            track_cost(judge_model, fwd_response.usage.prompt_tokens, fwd_response.usage.completion_tokens, "judge")
        
        # Reverse direction: A=j, B=i (swap images)
        rev_parts = []
        if judge_moodboard_parts:
            rev_parts.append({"type": "text", "text": "MOODBOARD REFERENCES (the visual direction these builds should match):"})
            rev_parts.extend(judge_moodboard_parts)
        rev_parts.append({"type": "text", "text": f"Compare these two share card prototypes.\n\nBrief context: {state['brief'][:500]}\n\nImage 1 is ARTIFACT A. Image 2 is ARTIFACT B."})
        rev_parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_j}"}})
        rev_parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_i}"}})
        rev_messages = [{"role": "user", "content": rev_parts}]
        
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
    
    # Record verdict to technique registry (cross-run learning — legacy)
    record_verdict(
        run_name=state["name"],
        decision=human_decision,
        feedback=human_feedback,
        ranking=state.get("ranking", []),
        builds=state.get("builds", []),
        approaches=state.get("approaches", []),
    )
    
    # Ingest run results into the wiki (compounding knowledge base)
    try:
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
    graph.add_node("qa", qa_station_node)
    graph.add_node("judge", pairwise_judge_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("iterate", iterate_node)
    graph.add_node("deploy", deploy_node)
    
    # Edges
    graph.add_edge(START, "research")
    graph.add_conditional_edges("research", fan_out_designers, ["designer"])
    graph.add_edge("designer", "approach_gate")
    graph.add_edge("approach_gate", "asset_gen")
    graph.add_conditional_edges("asset_gen", fan_out_builders, ["builder"])
    graph.add_edge("builder", "qa")
    graph.add_edge("qa", "judge")
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
    run_parser.add_argument("--design-system", default=None, help="Path to design system tokens file (e.g., smplx-design-system.md)")
    
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
            "design_system": design_system,
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
