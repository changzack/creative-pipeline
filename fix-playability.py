"""Targeted playability fixer for individual builds.

Reads the walk JSON for each build, sends the HTML (with base64 assets stripped)
to a fix model with the walker's specific findings, and re-injects assets.

Usage: python fix-playability.py <run_name> <concept_index> [<concept_index> ...]
"""

import sys
import os
import re
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pipeline import RUNS_DIR, walk_experience, _select_journey_screenshots

# Lazy import: OpenAI client
from openai import OpenAI


def extract_assets(html: str):
    """Replace base64 data URIs with placeholders. Returns (stripped_html, asset_map)."""
    assets = {}
    def _preserve(match):
        key = f"__PRESERVED_ASSET_{len(assets)}__"
        assets[key] = match.group(0)
        return key
    stripped = re.sub(
        r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+",
        _preserve,
        html,
    )
    return stripped, assets


def reinject_assets(html: str, assets: dict) -> str:
    """Re-insert preserved assets by their placeholder keys."""
    out = html
    missing = 0
    for key, value in assets.items():
        if key in out:
            out = out.replace(key, value)
        else:
            missing += 1
    if missing:
        print(f"    ⚠️  {missing} asset placeholders not found in fixed HTML")
    return out


def build_fix_prompt(brief_text: str, walk_summary: dict, concept_id: int) -> tuple[str, str]:
    """Build the system + user prompts for the fix model."""
    interactive = walk_summary.get("interactive_elements_found", 0)
    attempted = walk_summary.get("clicks_attempted", 0)
    changed = walk_summary.get("clicks_that_changed_state", 0)
    states = walk_summary.get("unique_states", 0)
    dead = walk_summary.get("dead_prototype", False)
    inert = walk_summary.get("inert_prototype", False)
    errors = walk_summary.get("console_errors_total", 0)

    # Per-click report
    step_lines = []
    for s in walk_summary.get("steps", []):
        idx = s.get("index")
        label = (s.get("clicked_label") or "<initial>").replace("\n", " ")
        changed_str = s.get("state_changed")
        if idx == 0:
            step_lines.append(f"  step 0: <initial render>")
        else:
            tag = "✓ state changed" if changed_str else "✗ NOTHING HAPPENED"
            step_lines.append(f"  step {idx}: clicked '{label}' → {tag}")
    walk_report = "\n".join(step_lines)

    diagnosis_lines = [
        f"Interactive elements found by automated walker: {interactive}",
        f"Clicks attempted: {attempted}",
        f"Clicks that produced visible state change: {changed}",
        f"Unique states visited: {states}",
        f"Console errors observed: {errors}",
    ]
    if dead:
        diagnosis_lines.append("⚠️ DEAD PROTOTYPE: buttons exist but clicking them does nothing.")
    if inert:
        diagnosis_lines.append("⚠️ INERT PROTOTYPE: no clickable elements at all.")
    diagnosis = "\n".join(diagnosis_lines)

    system = (
        "You are a senior front-end engineer fixing a single-file HTML prototype so it is FULLY PLAYABLE. "
        "The prototype is for a sneaker authentication + arbitrage game (see brief). "
        "You will receive the current HTML source and an automated walker's report describing what is broken. "
        "Your job: make the prototype interactive end-to-end so a user (and an automated click-walker) can progress through the full experience. "
        "\n\nHARD RULES:"
        "\n- Output ONLY the complete fixed HTML file. No markdown code fences. No commentary."
        "\n- Do NOT remove or modify any `data:image/...` URIs, `__PRESERVED_ASSET_N__` placeholders, or asset references — they are real assets we will re-inject."
        "\n- Preserve the visual design, color palette, typography, and layout as much as possible — you are fixing functionality, not redesigning."
        "\n- Every interactive control (button, slider, tap area) must produce a visible state change when clicked."
        "\n- The game must support clicking through ALL 5 rounds of gameplay plus the end-of-game performance reveal."
        "\n- For the counter-offer slider, expose simple click-driven affordances (e.g., +/- buttons or quick-pick price chips) IN ADDITION to any drag/slider — automated walkers cannot drag with precision."
        "\n- Use plain vanilla JS (no build step). The file must work when opened locally."
        "\n- Fix any console errors silently if you can; do not introduce new ones."
    )

    user = f"""## Brief (creative context)
{brief_text[:8000]}

## Automated walker diagnosis for concept-{concept_id}
{diagnosis}

## Per-click walker report
{walk_report}

## What needs to be true after your fix
1. Every visible button/tappable element changes the screen when clicked.
2. The user can progress through all 5 game rounds end-to-end without getting stuck.
3. The end-of-game performance reveal screen is reachable.
4. The counter-offer mechanic has click-driven controls (not only a drag slider).
5. No console errors.

## Current HTML (assets stripped — preserved as __PRESERVED_ASSET_N__ placeholders, DO NOT MODIFY THEM)
```html
{{HTML_PLACEHOLDER}}
```
"""
    return system, user


def fix_one_build(run_name: str, concept_index: int, brief_text: str, model_id: str = "gpt-5.5"):
    run_dir = RUNS_DIR / run_name
    build_path = run_dir / "builds" / f"concept-{concept_index}.html"
    walk_path = run_dir / "walks" / f"concept-{concept_index}-walk.json"

    if not build_path.exists():
        print(f"❌ concept-{concept_index}: build file missing at {build_path}")
        return False
    if not walk_path.exists():
        print(f"❌ concept-{concept_index}: walk report missing at {walk_path}")
        return False

    html = build_path.read_text()
    size_before = len(html)
    walk_summary = json.loads(walk_path.read_text())

    print(f"\n🔧 Fixing concept-{concept_index} (model={model_id}, size={size_before//1024}KB)")
    print(f"   walker: interactive={walk_summary['interactive_elements_found']}, "
          f"clicks_changed_state={walk_summary['clicks_that_changed_state']}, "
          f"dead={walk_summary['dead_prototype']}")

    # Extract assets so we can fit code into context
    stripped, asset_map = extract_assets(html)
    print(f"   preserved {len(asset_map)} base64 assets ({size_before//1024}KB → {len(stripped)//1024}KB)")

    system, user_template = build_fix_prompt(brief_text, walk_summary, concept_index)
    user = user_template.replace("{HTML_PLACEHOLDER}", stripped[:80000])

    # Call OpenAI
    client = OpenAI()
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        max_completion_tokens=100000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    elapsed = time.time() - t0
    fixed = resp.choices[0].message.content or ""
    print(f"   model returned {len(fixed)//1024}KB in {elapsed:.1f}s")

    # Strip markdown fences if present
    if "```html" in fixed:
        fixed = fixed.split("```html", 1)[1].split("```", 1)[0]
    elif fixed.lstrip().startswith("```"):
        fixed = fixed.split("```", 1)[1].split("```", 1)[0]
    fixed = fixed.strip()

    if len(fixed) < 1000:
        print(f"   ❌ fix output too short ({len(fixed)} bytes) — refusing to overwrite")
        return False

    # Re-inject assets
    final = reinject_assets(fixed, asset_map)
    size_after = len(final)
    print(f"   final size: {size_after//1024}KB (asset-injected)")

    if size_after < size_before * 0.5:
        print(f"   ⚠️  fixed build is < 50% of original — may have lost content. Saving as .fix-attempt instead.")
        out_path = build_path.with_suffix(".fix-attempt.html")
        out_path.write_text(final)
        return False

    # Back up original
    backup_path = build_path.with_suffix(f".pre-fix-{int(time.time())}.html")
    backup_path.write_text(html)
    build_path.write_text(final)
    print(f"   ✅ wrote fixed build; original backed up to {backup_path.name}")
    return True


def re_walk_after_fix(run_name: str, concept_index: int):
    """Re-walk a build after fixing and print summary."""
    run_dir = RUNS_DIR / run_name
    build_path = run_dir / "builds" / f"concept-{concept_index}.html"
    walks_dir = run_dir / "walks"
    print(f"\n🚶 Re-walking concept-{concept_index} after fix...")
    walk = walk_experience(build_path, walks_dir, f"concept-{concept_index}-postfix")
    print(f"   interactive={walk['interactive_elements_found']}, "
          f"clicks_attempted={walk['clicks_attempted']}, "
          f"clicks_changed_state={walk['clicks_that_changed_state']}, "
          f"states={walk['unique_states']}, "
          f"dead={walk['dead_prototype']}, inert={walk['inert_prototype']}")
    return walk


def main():
    if len(sys.argv) < 3:
        print("Usage: python fix-playability.py <run_name> <concept_index> [<concept_index> ...]")
        sys.exit(1)

    run_name = sys.argv[1]
    indices = [int(x) for x in sys.argv[2:]]

    # Find brief
    brief_candidates = [
        Path.home() / ".openclaw/workspace/memory/plans/sneaker-game-creative-brief.md",
    ]
    brief_text = ""
    for p in brief_candidates:
        if p.exists():
            brief_text = p.read_text()
            print(f"📄 Using brief: {p}")
            break
    if not brief_text:
        print("⚠️  No brief found — proceeding without it.")

    results = {}
    for idx in indices:
        ok = fix_one_build(run_name, idx, brief_text)
        results[idx] = ok
        if ok:
            re_walk_after_fix(run_name, idx)

    print("\n--- Summary ---")
    for idx, ok in results.items():
        print(f"  concept-{idx}: {'✅ fixed' if ok else '❌ FAILED'}")


if __name__ == "__main__":
    main()
