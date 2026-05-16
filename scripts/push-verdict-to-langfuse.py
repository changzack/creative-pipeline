#!/usr/bin/env python3
"""
Push a creative pipeline verdict to Langfuse as scores on the corresponding trace.

Verdict shape (from generate-eval-app.py output, the JSON the user submits):
{
  "run": "sharecard-v4c",
  "timestamp": "2026-05-12T...",
  "verdict": "iterate" | "approve" | "reject",
  "overall_note": "...",
  "best_concept": 0 | 1 | 2 | -1,
  "concepts": [
    {
      "index": 0,
      "model": "claude-opus",
      "rating": "great" | "acceptable" | "bad" | "unrated",
      "dimensions": {
        "creative_ambition": 0-5,
        "ai_slop": 0-5,
        "visual_depth": 0-5,
        "typography": 0-5,
        "hierarchy": 0-5
      },
      "techniques": {...},
      "note": "..."
    },
    ...
  ]
}

Trace lookup order:
  1. <run_dir>/langfuse-trace.json registry (Phase 1.1 — preferred)
  2. Langfuse trace search by name (pipeline-<run_name>) for backfilled runs

Usage:
    python scripts/push-verdict-to-langfuse.py path/to/verdict.json
    python scripts/push-verdict-to-langfuse.py --run sharecard-v4c   (auto-locates verdict.json)
    python scripts/push-verdict-to-langfuse.py --backfill            (push all verdicts found)
    python scripts/push-verdict-to-langfuse.py --dry-run path/to/verdict.json
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = THIS_DIR.parent
WORKSPACE = PIPELINE_DIR.parent
RUNS_DIR = WORKSPACE / "overnight-runs"


# ── Score mapping ───────────────────────────────────────────────
RATING_TO_SCORE = {
    "great": 3.0,
    "acceptable": 2.0,
    "bad": 1.0,
    "unrated": None,  # skip
}

VERDICT_TO_SCORE = {
    "approve": 3.0,
    "iterate": 2.0,
    "reject": 1.0,
}

DIMENSIONS = ["creative_ambition", "ai_slop", "visual_depth", "typography", "hierarchy"]


def _lf_client():
    try:
        from langfuse import Langfuse
    except ImportError:
        print("❌ langfuse SDK not installed")
        sys.exit(1)
    return Langfuse(
        host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
        public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
    )


def find_trace_ids(client, run_name: str) -> list:
    """Resolve trace IDs for a run, preferring local registry."""
    # Preferred: local registry written by pipeline.py
    registry = RUNS_DIR / run_name / "langfuse-trace.json"
    if registry.exists():
        try:
            entries = json.loads(registry.read_text())
            # initial trace first, then resumes
            return entries
        except Exception as e:
            print(f"  ⚠️  registry read failed: {e}")

    # Fallback: search Langfuse traces and match by run_name metadata on any observation
    found = []
    try:
        # Trace names can vary depending on ingestion order, so we scan recent traces
        # and check root span metadata. Page through results (API caps page at 100).
        page = 1
        scanned = 0
        while scanned < 500:
            result = client.api.trace.list(limit=100, page=page)
            traces = result.data if hasattr(result, "data") else []
            if not traces:
                break
            for t in traces:
                md = t.metadata if isinstance(t.metadata, dict) else {}
                if md.get("run_name") == run_name:
                    found.append({"trace_id": t.id, "run_name": run_name, "kind": "found-by-metadata"})
            scanned += len(traces)
            if len(traces) < 100:
                break
            page += 1
        return found
    except Exception as e:
        print(f"  ⚠️  Langfuse trace search failed: {e}")
        return []


def push_verdict(client, verdict_path: Path, dry_run: bool = False) -> bool:
    verdict = json.loads(verdict_path.read_text())
    run_name = verdict.get("run", "unknown")
    print(f"\n📋 verdict: {verdict_path}")
    print(f"   run={run_name}  verdict={verdict.get('verdict')}  best_concept={verdict.get('best_concept')}")
    print(f"   timestamp={verdict.get('timestamp')}")

    trace_entries = find_trace_ids(client, run_name)
    if not trace_entries:
        print(f"   ❌ no trace found for run '{run_name}' — skipping")
        return False

    # Pick the most relevant trace: prefer initial trace (the pipeline run itself),
    # fall back to the first one found.
    primary = next((t for t in trace_entries if t.get("kind") == "initial"), trace_entries[0])
    primary_id = primary["trace_id"]
    all_ids = [t["trace_id"] for t in trace_entries]
    print(f"   trace ids: {all_ids}  (primary={primary_id})")

    # Score plan
    plan = []

    # Run-level verdict
    v = verdict.get("verdict")
    if v in VERDICT_TO_SCORE:
        plan.append({
            "trace_id": primary_id,
            "name": "verdict_decision",
            "value": VERDICT_TO_SCORE[v],
            "data_type": "NUMERIC",
            "comment": f"verdict={v}; best_concept={verdict.get('best_concept')}; {verdict.get('overall_note','')}".strip()[:1000],
        })

    # Run-level "best concept index" (categorical → numeric for sorting)
    bc = verdict.get("best_concept")
    if bc is not None:
        plan.append({
            "trace_id": primary_id,
            "name": "best_concept_index",
            "value": float(bc),
            "data_type": "NUMERIC",
            "comment": "Index of the best concept in this run; -1 means no winner",
        })

    # Per-concept scores
    for c in verdict.get("concepts", []):
        idx = c.get("index")
        model = c.get("model", "unknown")
        rating = c.get("rating", "unrated")
        note = (c.get("note") or "")[:1000]
        score_val = RATING_TO_SCORE.get(rating)
        if score_val is not None:
            plan.append({
                "trace_id": primary_id,
                "name": f"concept_{idx}_rating",
                "value": score_val,
                "data_type": "NUMERIC",
                "comment": f"model={model}; rating={rating}; {note}",
            })
        # Per-dimension scores
        for dim in DIMENSIONS:
            dval = c.get("dimensions", {}).get(dim)
            if dval is not None and isinstance(dval, (int, float)) and dval > 0:
                plan.append({
                    "trace_id": primary_id,
                    "name": f"concept_{idx}_{dim}",
                    "value": float(dval),
                    "data_type": "NUMERIC",
                    "comment": f"model={model}; {dim}={dval}",
                })

    print(f"   📊 {len(plan)} scores to push")
    if dry_run:
        for p in plan[:8]:
            print(f"     • {p['name']} = {p['value']}  ({p['comment'][:80]})")
        if len(plan) > 8:
            print(f"     ... and {len(plan)-8} more")
        return True

    pushed = 0
    failed = 0
    for p in plan:
        try:
            client.create_score(
                trace_id=p["trace_id"],
                name=p["name"],
                value=p["value"],
                data_type=p["data_type"],
                comment=p["comment"],
            )
            pushed += 1
        except Exception as e:
            print(f"   ❌ failed to push {p['name']}: {e}")
            failed += 1

    client.flush()
    print(f"   ✅ pushed {pushed}, failed {failed}")
    return failed == 0


def find_all_verdicts() -> list:
    """Find all verdict.json files under overnight-runs."""
    if not RUNS_DIR.exists():
        return []
    return sorted(RUNS_DIR.glob("*/verdict.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verdict_path", nargs="?", help="Path to verdict.json (or use --run)")
    ap.add_argument("--run", help="Run name (auto-locates overnight-runs/<run>/verdict.json)")
    ap.add_argument("--backfill", action="store_true", help="Push all verdict.json files found")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = _lf_client()

    if args.backfill:
        paths = find_all_verdicts()
        print(f"🔍 found {len(paths)} verdict files")
    elif args.run:
        paths = [RUNS_DIR / args.run / "verdict.json"]
    elif args.verdict_path:
        paths = [Path(args.verdict_path)]
    else:
        ap.print_help()
        return 1

    ok = 0
    fail = 0
    for p in paths:
        if not p.exists():
            print(f"⚠️  not found: {p}")
            fail += 1
            continue
        if push_verdict(client, p, dry_run=args.dry_run):
            ok += 1
        else:
            fail += 1

    print(f"\nDone — {ok} ok, {fail} failed/skipped")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
