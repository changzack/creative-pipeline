"""Auto-iterate playability fixes until the build is end-to-end playable.

For each concept, we loop:
  1. Walk the build (with patient stabilize).
  2. Score it against game-completion signals (reaches round 2+, hits perf reveal,
     shows share card).
  3. If complete → stop, mark ✅.
  4. If not complete and iteration budget left → generate a targeted patch with
     Claude Opus 4.7 (frontier), append as a <script> patch, re-walk.
  5. Stop on success or hitting MAX_ITERATIONS.

Strategy notes:
- We use Anthropic SDK direct (not Hermes) for speed and large output budget.
- We extract relevant script blocks + button markup (not the whole 15MB file with
  assets) so the model sees what matters.
- We always APPEND patches — never rewrite the file — so we never destroy
  existing visuals or truncate.
"""

import sys
import os
import re
import json
import time
import shutil
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pipeline import RUNS_DIR, walk_experience, max_output_for, resolve_model

from anthropic import Anthropic


MAX_ITERATIONS = 4
MIN_ROUNDS_TO_HIT = 5  # Brief says 5 rounds


# ── Code-context extraction (avoids shipping 15MB asset blobs) ──────────

def extract_relevant_chunks(html: str, max_chars: int = 90000) -> str:
    """Pull <script> blocks + button markup, stripping base64 assets."""
    stripped = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "data:image/png;base64,[ASSET]", html)
    parts = []
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", stripped, re.DOTALL):
        parts.append(("SCRIPT", m.group(0)))
    button_blocks = re.findall(r"<button[^>]*>[^<]{0,200}</button>", stripped)
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


# ── End-to-end completion scoring ─────────────────────────────────────

# Markers we look for in screenshots' OCR-friendly proxy: the walker doesn't
# have OCR, but it captures DOM text via state hash. We re-extract DOM text on
# the final state by re-loading the build and reading visible text via JS.

def scan_state_for_signals(html_path: Path) -> dict:
    """Quick check: re-render the build and scan visible text for completion signals.

    Returns dict with booleans for: reaches_round_n, has_performance_screen,
    has_share_card, has_dialogue_loop, console_errors.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    signals = {
        "max_round_seen": 0,
        "reaches_performance": False,
        "reaches_share_card": False,
        "console_errors": [],
        "walked_states": 0,
        "playable_path_len": 0,
    }

    PERF_REGEX = re.compile(r"(total profit|performance|final score|p&?l|net flip|game over|results)", re.I)
    SHARE_REGEX = re.compile(r"(share|copy.*link|share card|tweet|social|instagram)", re.I)
    ROUND_REGEX = re.compile(r"(?:round|customer)\s*([0-9]+)\s*(?:/|of)\s*5", re.I)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))

            try:
                page.goto(f"file://{html_path.resolve()}", wait_until="networkidle", timeout=15000)
            except PWTimeout:
                page.goto(f"file://{html_path.resolve()}", wait_until="load", timeout=10000)
            page.wait_for_timeout(2500)

            # Walk: keep clicking the most prominent interactive element until no
            # progress or 40 steps.
            visited_hashes = set()
            for step in range(40):
                visible_text = page.evaluate("() => (document.body && document.body.innerText) || ''")
                # Round detection
                m = ROUND_REGEX.search(visible_text)
                if m:
                    signals["max_round_seen"] = max(signals["max_round_seen"], int(m.group(1)))
                if PERF_REGEX.search(visible_text):
                    signals["reaches_performance"] = True
                if SHARE_REGEX.search(visible_text):
                    signals["reaches_share_card"] = True

                # State hash check
                import hashlib
                h = hashlib.sha256(visible_text.encode("utf-8")).hexdigest()[:12]
                visited_hashes.add(h)

                # Find the most prominent interactive element
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
                # Try first element. If clicking doesn't change state, try next.
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
            browser.close()
    except Exception as e:
        signals["scan_error"] = str(e)

    signals["playable_path_len"] = signals["walked_states"]
    return signals


def is_complete(signals: dict) -> bool:
    """End-to-end gameplay is complete when we reach 5 rounds AND the performance reveal AND share card."""
    return (
        signals.get("max_round_seen", 0) >= MIN_ROUNDS_TO_HIT
        and signals.get("reaches_performance", False)
        and signals.get("reaches_share_card", False)
    )


def gap_summary(signals: dict) -> str:
    gaps = []
    rounds = signals.get("max_round_seen", 0)
    if rounds < MIN_ROUNDS_TO_HIT:
        gaps.append(f"Only reaches round {rounds}/{MIN_ROUNDS_TO_HIT}.")
    if not signals.get("reaches_performance"):
        gaps.append("Never reaches the end-of-game PERFORMANCE REVEAL screen (no 'total profit'/'P&L'/'results' text found).")
    if not signals.get("reaches_share_card"):
        gaps.append("Never reaches the SHARE CARD screen (no 'share'/'copy link' text found).")
    if signals.get("console_errors"):
        gaps.append(f"Console errors present: {signals['console_errors'][:3]}")
    if not gaps:
        gaps.append("Build is end-to-end complete.")
    return " ".join(gaps)


# ── Patch generation ──────────────────────────────────────────────────

def build_patch_prompt(brief_text: str, signals: dict, concept_id: int,
                       code_context: str, iteration: int) -> tuple[str, str]:
    gaps = gap_summary(signals)

    system = (
        "You are a senior front-end engineer making a single-file HTML game prototype END-TO-END PLAYABLE. "
        "You will receive: (1) the brief, (2) a diagnosis of what is currently broken or missing, (3) the existing CODE CHUNKS. "
        "Your job: output a SINGLE <script> block that, appended at the end of the file, makes the game playable through ALL 5 ROUNDS plus the end-of-game PERFORMANCE REVEAL plus the SHARE CARD screen."
        "\n\nHARD RULES:"
        "\n- Output ONLY a single <script>...</script> block. No markdown fences. No explanation. No <html>/<body>/<head>."
        "\n- Your patch is APPENDED to the file. It runs AFTER all existing code."
        "\n- Reference existing functions/variables where they exist. If they don't, DEFINE them in your patch."
        "\n- The complete game must include: intro → 5 rounds (each: customer dialogue → real/fake decision → counter-offer slider with quick-pick buttons → buy/pass) → performance reveal (showing per-round profit/loss, total, accuracy, rank, streak) → shareable card (with a 'Share' or 'Copy Link' button)."
        "\n- Each round MUST use a DIFFERENT customer / shoe / dialogue. Hardcode 5 distinct rounds in your patch if needed."
        "\n- Add a CLEAR round counter (e.g. 'CUSTOMER 1/5') visible at all times."
        "\n- The performance reveal screen MUST contain the text 'TOTAL PROFIT' or 'P&L' or 'PERFORMANCE' so it's detectable."
        "\n- The share card screen MUST contain a 'Share' or 'Copy Link' or 'Share Result' button."
        "\n- Use vanilla JS only. No frameworks. No imports."
        "\n- Guard with DOMContentLoaded so it runs even if the file has script-loading bugs."
        "\n- If previous patches have already been applied (look for `<!-- AUTO-PATCH:` comments), your new patch must SUPERSEDE them, not duplicate handlers. Wrap your logic in a unique namespace and remove old listeners first."
        "\n- It is OK to hide pre-existing broken UI elements and replace them with your own simpler controls if needed to make the flow work. Functionality > preserving every visual."
    )

    user = f"""## BRIEF
{brief_text[:6000]}

## ITERATION {iteration}/{MAX_ITERATIONS}

## CURRENT DIAGNOSIS (what's still missing/broken)
{gaps}

Walker telemetry:
- max round seen: {signals.get('max_round_seen', 0)}/{MIN_ROUNDS_TO_HIT}
- reaches performance reveal: {signals.get('reaches_performance', False)}
- reaches share card: {signals.get('reaches_share_card', False)}
- distinct visible states reached: {signals.get('walked_states', 0)}
- console errors: {signals.get('console_errors', [])}

## EXISTING CODE (concept-{concept_id})
{code_context}

## YOUR TASK
Write a single <script> block that closes the gaps above. The end goal is a user can click from the intro through all 5 rounds, see their performance reveal, and reach the share card with a working Share button.
"""
    return system, user


def apply_patch(html: str, patch_text: str) -> str:
    """Append a patch script right before </body>."""
    patch = patch_text.strip()
    if "```html" in patch:
        patch = patch.split("```html", 1)[1].split("```", 1)[0]
    elif "```" in patch:
        patch = re.sub(r"```[a-zA-Z]*\n?", "", patch)
        patch = patch.replace("```", "")
    patch = patch.strip()
    if "<script" not in patch.lower():
        patch = f"<script>\n{patch}\n</script>"

    marker = f"\n<!-- AUTO-PATCH: iter {time.strftime('%H:%M:%S')} -->\n"
    if "</body>" in html:
        return html.replace("</body>", f"{marker}{patch}\n</body>", 1)
    return html + f"{marker}{patch}\n"


def iterate_one(run_name: str, concept_index: int, brief_text: str,
                client: Anthropic, model_id: str) -> dict:
    """Iterate patches on a single concept until end-to-end complete or budget out."""
    run_dir = RUNS_DIR / run_name
    build_path = run_dir / "builds" / f"concept-{concept_index}.html"
    iter_log = run_dir / "iter-logs"
    iter_log.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"🎮 Iterating concept-{concept_index}")
    print(f"{'='*60}")

    log = {"concept": concept_index, "iterations": []}
    for it in range(1, MAX_ITERATIONS + 1):
        print(f"\n— Iteration {it}/{MAX_ITERATIONS} —")
        signals = scan_state_for_signals(build_path)
        print(f"  rounds={signals.get('max_round_seen')}/{MIN_ROUNDS_TO_HIT}, "
              f"perf={signals.get('reaches_performance')}, "
              f"share={signals.get('reaches_share_card')}, "
              f"states={signals.get('walked_states')}, "
              f"errors={len(signals.get('console_errors',[]))}")
        log["iterations"].append({"iter": it, "signals": signals})

        if is_complete(signals):
            print(f"  ✅ End-to-end complete on iteration {it}")
            log["final_status"] = "complete"
            log["final_iteration"] = it
            (iter_log / f"concept-{concept_index}-iterlog.json").write_text(json.dumps(log, indent=2))
            return {"concept": concept_index, "complete": True, "iterations": it}

        print(f"  diagnosis: {gap_summary(signals)}")

        html = build_path.read_text()
        code_ctx = extract_relevant_chunks(html, max_chars=90000)
        system, user = build_patch_prompt(brief_text, signals, concept_index, code_ctx, it)

        try:
            t0 = time.time()
            patch_text_parts = []
            with client.messages.stream(
                model=model_id,
                max_tokens=max_output_for(model_id),
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                for chunk in stream.text_stream:
                    patch_text_parts.append(chunk)
            patch_text = "".join(patch_text_parts)
            elapsed = time.time() - t0
            print(f"  patch returned {len(patch_text)//1024}KB in {elapsed:.1f}s")
        except Exception as e:
            print(f"  ❌ patch generation failed: {e}")
            log["iterations"][-1]["error"] = str(e)
            break

        if len(patch_text) < 500:
            print(f"  ❌ patch too short ({len(patch_text)} bytes)")
            break

        patched = apply_patch(html, patch_text)
        backup = build_path.with_suffix(f".pre-iter{it}-{int(time.time())}.html")
        shutil.copy(build_path, backup)
        build_path.write_text(patched)
        print(f"  ✅ patch applied (size {len(patched)//1024}KB, backup: {backup.name})")

    (iter_log / f"concept-{concept_index}-iterlog.json").write_text(json.dumps(log, indent=2))
    final = scan_state_for_signals(build_path)
    log["iterations"].append({"iter": "final", "signals": final})
    (iter_log / f"concept-{concept_index}-iterlog.json").write_text(json.dumps(log, indent=2))
    return {"concept": concept_index, "complete": is_complete(final), "iterations": MAX_ITERATIONS, "final": final}


def main():
    global MAX_ITERATIONS
    parser = argparse.ArgumentParser()
    parser.add_argument("run_name")
    parser.add_argument("concepts", nargs="+", type=int)
    parser.add_argument("--max-iter", type=int, default=MAX_ITERATIONS)
    args = parser.parse_args()
    MAX_ITERATIONS = args.max_iter

    brief_path = Path.home() / ".openclaw/workspace/memory/plans/sneaker-game-creative-brief.md"
    brief_text = brief_path.read_text() if brief_path.exists() else ""

    model_id = resolve_model("claude-opus")
    print(f"📄 Brief: {brief_path.name}")
    print(f"🤖 Patch model: {model_id} (output cap: {max_output_for(model_id):,} tokens)")
    print(f"🔁 Max iterations per concept: {MAX_ITERATIONS}")

    client = Anthropic()
    results = []
    for idx in args.concepts:
        result = iterate_one(args.run_name, idx, brief_text, client, model_id)
        results.append(result)

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for r in results:
        status = "✅ COMPLETE" if r["complete"] else "⚠️ INCOMPLETE"
        print(f"  concept-{r['concept']}: {status} (iters={r.get('iterations')})")
        if not r["complete"] and r.get("final"):
            print(f"    final state: {gap_summary(r['final'])}")

    # Sync eval app
    run_dir = RUNS_DIR / args.run_name
    eval_builds = run_dir / "eval" / "builds"
    if eval_builds.exists():
        for idx in args.concepts:
            src = run_dir / "builds" / f"concept-{idx}.html"
            dst = eval_builds / f"concept-{idx}.html"
            if src.exists():
                shutil.copy(src, dst)
        print("\n📁 Eval app builds synced.")


if __name__ == "__main__":
    main()
