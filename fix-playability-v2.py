"""Surgical playability fixer — appends a fix script to broken builds.

Approach: send the relevant code chunks + walker diagnosis to Claude Opus, ask
for a single <script> block that PATCHES the bugs by adding missing event
handlers, init calls, or state machines. Append the patch script to the end of
the build right before </body>, so the original file is preserved.

Usage: python fix-playability-v2.py <run_name> <concept_index> [<concept_index> ...]
"""

import sys
import os
import re
import json
import time
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pipeline import RUNS_DIR, walk_experience

from anthropic import Anthropic


def extract_relevant_chunks(html: str, max_chars: int = 50000) -> str:
    """Pull out the JS-relevant parts of the HTML for context.

    Strategy: keep the <body>'s opening structure (buttons / interactive markup)
    and ALL <script> blocks. Strip base64 data URIs. Truncate gracefully.
    """
    # Strip base64 data URIs (they're huge and irrelevant)
    stripped = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "data:image/png;base64,[ASSET]", html)

    parts = []
    # Find all <script>...</script> blocks
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", stripped, re.DOTALL):
        parts.append(("SCRIPT", m.group(0)))
    # Find interactive markup (buttons, divs with click handlers)
    button_blocks = re.findall(r"<button[^>]*>[^<]{0,200}</button>", stripped)
    for b in button_blocks[:40]:
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
        # Keep first half + last half
        half = max_chars // 2
        out = out[:half] + "\n\n// ... [middle truncated] ...\n\n" + out[-half:]
    return out


def build_patch_prompt(brief_text: str, walk_summary: dict, concept_id: int,
                       code_context: str) -> tuple[str, str]:
    interactive = walk_summary.get("interactive_elements_found", 0)
    changed = walk_summary.get("clicks_that_changed_state", 0)
    dead = walk_summary.get("dead_prototype", False)
    inert = walk_summary.get("inert_prototype", False)
    errors = walk_summary.get("console_errors_total", 0)

    step_lines = []
    for s in walk_summary.get("steps", []):
        idx = s.get("index")
        label = (s.get("clicked_label") or "<initial>").replace("\n", " ")
        if idx == 0:
            step_lines.append(f"  step 0: <initial render>")
        else:
            tag = "✓ state changed" if s.get("state_changed") else "✗ NO STATE CHANGE"
            step_lines.append(f"  step {idx}: clicked '{label}' (selector: {s.get('clicked_selector','?')}) → {tag}")
    walk_report = "\n".join(step_lines)

    system = (
        "You are a senior front-end engineer doing surgical patches on a single-file HTML game prototype. "
        "You will receive: (1) the brief, (2) an automated walker's diagnosis, (3) the relevant CODE CHUNKS from the build. "
        "Your job: output a SINGLE <script> block that, when appended to the end of the file, makes the prototype FULLY PLAYABLE. "
        "\n\nWHAT YOUR PATCH SCRIPT MUST DO:"
        "\n1. Wire up any visible buttons/tappable elements that currently have no click handler."
        "\n2. Trigger the game's intro/start sequence on page load (call existing functions like playIntro/startGame/runSequence if defined)."
        "\n3. Make sure the user can progress through all 5 rounds and reach the end-of-game performance reveal."
        "\n4. If the build is a 'demo reel' that auto-plays without user input, convert it into a per-step click-driven flow."
        "\n5. Fix any console errors silently."
        "\n6. Preserve all existing visual design, animations, and styles."
        "\n\nHARD RULES:"
        "\n- Output ONLY a single <script>...</script> block. No markdown fences. No explanation. No <html>/<body>/<head>."
        "\n- Your script will be APPENDED to the existing HTML right before </body>. It runs AFTER all existing code."
        "\n- Reference functions/variables that EXIST in the provided code (don't invent them)."
        "\n- If existing functions are missing or broken, define replacements inline in your patch."
        "\n- Use vanilla JS only. No frameworks. No imports."
        "\n- Guard with `document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init()`."
    )

    user = f"""## BRIEF
{brief_text[:6000]}

## WALKER DIAGNOSIS
Interactive elements found: {interactive}
Clicks that changed state: {changed}
Console errors: {errors}
Dead prototype: {dead}
Inert prototype: {inert}

## WALKER STEP-BY-STEP
{walk_report}

## RELEVANT CODE CHUNKS FROM THIS BUILD (concept-{concept_id})
{code_context}

## YOUR TASK
Write a single <script> block that fixes playability. It will be appended at the very end of the file, right before </body>. Reference existing functions where they exist; otherwise define new ones. Make the game playable end-to-end (intro → 5 rounds → performance reveal).
"""
    return system, user


def patch_one_build(run_name: str, concept_index: int, brief_text: str):
    run_dir = RUNS_DIR / run_name
    build_path = run_dir / "builds" / f"concept-{concept_index}.html"
    walk_path = run_dir / "walks" / f"concept-{concept_index}-walk.json"

    if not build_path.exists() or not walk_path.exists():
        print(f"❌ concept-{concept_index}: missing build or walk report")
        return False

    html = build_path.read_text()
    size_before = len(html)
    walk_summary = json.loads(walk_path.read_text())

    print(f"\n🔧 Patching concept-{concept_index} (size={size_before//1024}KB)")
    print(f"   walker: interactive={walk_summary['interactive_elements_found']}, "
          f"changed_state={walk_summary['clicks_that_changed_state']}, "
          f"dead={walk_summary['dead_prototype']}")

    code_ctx = extract_relevant_chunks(html, max_chars=80000)
    print(f"   code context: {len(code_ctx)//1024}KB")

    system, user = build_patch_prompt(brief_text, walk_summary, concept_index, code_ctx)

    client = Anthropic()
    t0 = time.time()
    patch_text_parts = []
    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=128000,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for chunk in stream.text_stream:
            patch_text_parts.append(chunk)
    patch_text = "".join(patch_text_parts)
    elapsed = time.time() - t0
    print(f"   model returned {len(patch_text)//1024}KB in {elapsed:.1f}s")

    # Strip any markdown fences
    if "```html" in patch_text:
        patch_text = patch_text.split("```html", 1)[1].split("```", 1)[0]
    elif "```" in patch_text:
        # Remove all triple-backtick fences
        patch_text = re.sub(r"```[a-zA-Z]*\n?", "", patch_text)
        patch_text = patch_text.replace("```", "")

    patch_text = patch_text.strip()

    if "<script" not in patch_text.lower():
        # Wrap it
        patch_text = f"<script>\n{patch_text}\n</script>"

    if len(patch_text) < 200:
        print(f"   ❌ patch too short ({len(patch_text)} bytes)")
        return False

    # Append patch right before </body>
    if "</body>" in html:
        patched_html = html.replace("</body>", f"\n<!-- AUTO-PATCH: playability fix -->\n{patch_text}\n</body>", 1)
    else:
        patched_html = html + f"\n<!-- AUTO-PATCH: playability fix -->\n{patch_text}\n"

    # Back up
    backup_path = build_path.with_suffix(f".pre-patch-{int(time.time())}.html")
    shutil.copy(build_path, backup_path)
    build_path.write_text(patched_html)
    print(f"   ✅ wrote patched build (+{(len(patched_html) - size_before)//1024}KB); backup: {backup_path.name}")
    return True


def re_walk(run_name: str, concept_index: int):
    run_dir = RUNS_DIR / run_name
    build_path = run_dir / "builds" / f"concept-{concept_index}.html"
    walks_dir = run_dir / "walks"
    print(f"\n🚶 Re-walking concept-{concept_index} after patch...")
    walk = walk_experience(build_path, walks_dir, f"concept-{concept_index}-postpatch")
    print(f"   interactive={walk['interactive_elements_found']}, "
          f"clicks_attempted={walk['clicks_attempted']}, "
          f"clicks_changed_state={walk['clicks_that_changed_state']}, "
          f"states={walk['unique_states']}, "
          f"dead={walk['dead_prototype']}, inert={walk['inert_prototype']}")
    return walk


def main():
    if len(sys.argv) < 3:
        print("Usage: python fix-playability-v2.py <run_name> <concept_index> [<concept_index> ...]")
        sys.exit(1)
    run_name = sys.argv[1]
    indices = [int(x) for x in sys.argv[2:]]

    brief_path = Path.home() / ".openclaw/workspace/memory/plans/sneaker-game-creative-brief.md"
    brief_text = brief_path.read_text() if brief_path.exists() else ""
    if brief_text:
        print(f"📄 Using brief: {brief_path}")

    results = {}
    for idx in indices:
        ok = patch_one_build(run_name, idx, brief_text)
        results[idx] = ok
        if ok:
            re_walk(run_name, idx)

    print("\n--- Summary ---")
    for idx, ok in results.items():
        print(f"  concept-{idx}: {'✅ patched' if ok else '❌ FAILED'}")


if __name__ == "__main__":
    main()
