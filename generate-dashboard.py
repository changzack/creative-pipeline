#!/usr/bin/env python3
"""Generate a self-contained pipeline dashboard HTML from a run directory."""

import argparse
import base64
import io
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install it or activate the pipeline venv.", file=sys.stderr)
    sys.exit(1)


def resize_image_b64(path: Path, max_width: int, fmt: str = "JPEG", quality: int = 75) -> Tuple[str, str]:
    """Resize an image to max_width and return (base64_data, mime_type)."""
    img = Image.open(path)
    if img.mode == "RGBA" and fmt == "JPEG":
        bg = Image.new("RGB", img.size, (10, 10, 10))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB" and fmt == "JPEG":
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        mime = "image/jpeg"
    else:
        img.save(buf, format="PNG", optimize=True)
        mime = "image/png"
    return base64.b64encode(buf.getvalue()).decode("ascii"), mime


def render_markdown(text: str) -> str:
    """Minimal markdown to HTML: headers, bold, bullets, paragraphs."""
    lines = text.split("\n")
    html_lines = []  # type: List[str]
    in_ul = False

    for line in lines:
        stripped = line.strip()

        # Headers
        header_match = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if header_match:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            level = min(len(header_match.group(1)) + 2, 6)  # # -> h3, ## -> h4, etc.
            content = _inline_format(header_match.group(2))
            html_lines.append(f"<h{level}>{content}</h{level}>")
            continue

        # Bullet points
        bullet_match = re.match(r"^[-*]\s+(.*)", stripped)
        if bullet_match:
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{_inline_format(bullet_match.group(1))}</li>")
            continue

        # Close list if we hit a non-bullet
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False

        # Empty line
        if not stripped:
            continue

        # Regular paragraph
        html_lines.append(f"<p>{_inline_format(stripped)}</p>")

    if in_ul:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def _inline_format(text: str) -> str:
    """Handle **bold** and `code` inline."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def load_pairwise(run_dir: Path) -> Tuple[List[dict], List[dict]]:
    """Load pairwise results. Returns (pairs, ranking)."""
    path = run_dir / "reviews" / "pairwise-results.json"
    if not path.exists():
        return [], []
    data = json.loads(path.read_text())
    return data.get("pairs", []), data.get("ranking", [])


def load_approach(run_dir: Path, index: int) -> Optional[str]:
    """Load approach doc for a concept."""
    path = run_dir / "concepts" / f"designer-{index}-APPROACH.md"
    if path.exists():
        return path.read_text()
    return None


def get_run_metadata(run_dir: Path) -> Dict[str, str]:
    """Extract run name and try to find phase/iteration info."""
    meta = {"name": run_dir.name, "phase": "—", "iteration": "—"}
    # Try to find state from pipeline db or state file
    state_file = run_dir / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            meta["phase"] = state.get("phase", meta["phase"])
            meta["iteration"] = str(state.get("iteration", meta["iteration"]))
        except (json.JSONDecodeError, KeyError):
            pass
    return meta


def build_concept_card(index: int, rank_info: Optional[dict], screenshot_b64: Optional[str], screenshot_mime: str, is_winner: bool) -> str:
    """Build HTML for a single concept card."""
    rank = rank_info["rank"] if rank_info else "?"
    wins = rank_info["wins"] if rank_info else 0

    rank_colors = {1: "#FFD700", 2: "#C0C0C0", 3: "#CD7F32"}
    rank_color = rank_colors.get(rank, "#666")
    rank_label = {1: "1st", 2: "2nd", 3: "3rd"}.get(rank, f"#{rank}")

    winner_class = "winner" if is_winner else ""

    screenshot_html = ""
    if screenshot_b64:
        screenshot_html = f'<img src="data:{screenshot_mime};base64,{screenshot_b64}" alt="Concept {index} screenshot" class="screenshot">'
    else:
        screenshot_html = '<div class="screenshot-placeholder">No screenshot</div>'

    return f'''
    <div class="concept-card {winner_class}">
        <div class="rank-badge" style="background:{rank_color}">{rank_label}</div>
        {screenshot_html}
        <div class="card-info">
            <h3>Concept {index}</h3>
            <span class="wins">{wins} win{"s" if wins != 1 else ""}</span>
        </div>
        <a href="builds/concept-{index}.html" class="open-build" target="_blank">Open Build ↗</a>
    </div>'''


def build_pairwise_section(pairs: List[dict]) -> str:
    """Build the pairwise results section."""
    if not pairs:
        return '<p class="muted">No pairwise results available.</p>'

    rows = []
    for p in pairs:
        a, b = p["pair"]
        fwd = p.get("forward", "?")
        rev = p.get("reverse", "?")
        agreed = p.get("agreed", False)
        winner = p.get("winner")

        if agreed:
            status_class = "agreed"
            status_icon = "✓ AGREED"
            outcome = f"→ concept {winner}" if winner is not None else "→ tie"
        else:
            status_class = "disagreed"
            status_icon = "⚠ DISAGREED"
            outcome = "→ no winner"

        fwd_reasoning = escape_html(p.get("fwd_reasoning", "No reasoning provided."))
        rev_reasoning = escape_html(p.get("rev_reasoning", "No reasoning provided."))

        rows.append(f'''
        <div class="pair-row {status_class}">
            <div class="pair-summary">
                <span class="pair-label">{a} vs {b}</span>
                <span class="pair-votes">fwd={fwd} rev={rev}</span>
                <span class="pair-status {status_class}">{status_icon}</span>
                <span class="pair-outcome">{outcome}</span>
            </div>
            <details class="pair-reasoning">
                <summary>Show reasoning</summary>
                <div class="reasoning-block">
                    <div class="reasoning-col">
                        <h4>Forward ({a} as A, {b} as B)</h4>
                        <p>{fwd_reasoning}</p>
                    </div>
                    <div class="reasoning-col">
                        <h4>Reverse ({b} as A, {a} as B)</h4>
                        <p>{rev_reasoning}</p>
                    </div>
                </div>
            </details>
        </div>''')

    return "\n".join(rows)


def build_approach_section(run_dir: Path, num_concepts: int) -> str:
    """Build collapsible approach docs."""
    sections = []
    for i in range(num_concepts):
        content = load_approach(run_dir, i)
        if content is None:
            continue
        # Extract first heading or first line as summary
        first_line = ""
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                first_line = stripped[:100]
                break
            elif stripped.startswith("#"):
                first_line = re.sub(r"^#+\s*", "", stripped)[:100]
                break

        rendered = render_markdown(content)
        sections.append(f'''
        <details class="approach-doc">
            <summary>Concept {i}: {escape_html(first_line)}</summary>
            <div class="approach-content">{rendered}</div>
        </details>''')

    return "\n".join(sections) if sections else '<p class="muted">No approach docs found.</p>'


def build_moodboard(run_dir: Path) -> str:
    """Build moodboard image grid."""
    moodboard_dir = run_dir / "moodboard"
    if not moodboard_dir.exists():
        return '<p class="muted">No moodboard images found.</p>'

    images = sorted(moodboard_dir.glob("*.png"))
    if not images:
        return '<p class="muted">No moodboard images found.</p>'

    items = []
    for img_path in images:
        try:
            b64, mime = resize_image_b64(img_path, 300, quality=60)
            name = img_path.stem.replace("-", " ").replace("_", " ")
            items.append(f'<img src="data:{mime};base64,{b64}" alt="{escape_html(name)}" title="{escape_html(name)}">')
        except Exception as e:
            print(f"Warning: Could not process moodboard image {img_path}: {e}", file=sys.stderr)

    return "\n".join(items) if items else '<p class="muted">No moodboard images found.</p>'


CSS = '''
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0a0a0a; color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6; padding: 24px;
}
.container { max-width: 1440px; margin: 0 auto; }

/* Header */
.header {
    border-bottom: 1px solid #222; padding-bottom: 20px; margin-bottom: 32px;
}
.header h1 {
    font-size: 14px; text-transform: uppercase; letter-spacing: 3px;
    color: #666; margin-bottom: 8px;
}
.header .meta {
    display: flex; gap: 24px; font-size: 15px; color: #999;
}
.header .meta span { display: flex; align-items: center; gap: 6px; }
.header .meta strong { color: #e0e0e0; }

/* Section titles */
.section-title {
    font-size: 12px; text-transform: uppercase; letter-spacing: 2px;
    color: #555; margin: 40px 0 16px; padding-bottom: 8px;
    border-bottom: 1px solid #1a1a1a;
}

/* Concept cards grid */
.concepts-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 20px; margin-bottom: 20px;
}
.concept-card {
    background: #111; border: 1px solid #222; border-radius: 12px;
    overflow: hidden; position: relative; transition: border-color 0.3s;
}
.concept-card:hover { border-color: #333; }
.concept-card.winner {
    border-color: #FFD70055;
    box-shadow: 0 0 20px rgba(255, 215, 0, 0.08), 0 0 40px rgba(255, 215, 0, 0.04);
}
.rank-badge {
    position: absolute; top: 12px; right: 12px; z-index: 2;
    width: 36px; height: 36px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: #000;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
.screenshot {
    width: 100%; max-height: 560px; object-fit: cover; object-position: top;
    display: block; border-bottom: 1px solid #222;
}
.screenshot-placeholder {
    width: 100%; height: 300px; display: flex;
    align-items: center; justify-content: center;
    background: #0d0d0d; color: #444; font-size: 14px;
}
.card-info {
    padding: 16px; display: flex; justify-content: space-between; align-items: center;
}
.card-info h3 { font-size: 16px; font-weight: 600; }
.wins { font-size: 13px; color: #666; }
.open-build {
    display: block; text-align: center; padding: 12px;
    background: #1a1a1a; color: #aaa; text-decoration: none;
    font-size: 13px; font-weight: 500; letter-spacing: 0.5px;
    transition: background 0.2s, color 0.2s;
    border-top: 1px solid #222;
}
.open-build:hover { background: #222; color: #fff; }

/* Pairwise results */
.pairwise-section { background: #111; border: 1px solid #222; border-radius: 12px; overflow: hidden; }
.pair-row { padding: 16px 20px; border-bottom: 1px solid #1a1a1a; }
.pair-row:last-child { border-bottom: none; }
.pair-summary {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}
.pair-label { font-weight: 600; font-size: 15px; min-width: 60px; }
.pair-votes { color: #888; font-size: 13px; font-family: monospace; }
.pair-status { font-size: 13px; font-weight: 600; }
.pair-status.agreed { color: #4ade80; }
.pair-status.disagreed { color: #fbbf24; }
.pair-outcome { color: #999; font-size: 13px; }

.pair-reasoning { margin-top: 12px; }
.pair-reasoning summary {
    cursor: pointer; font-size: 12px; color: #555;
    text-transform: uppercase; letter-spacing: 1px;
}
.pair-reasoning summary:hover { color: #888; }
.reasoning-block {
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
    margin-top: 12px; padding-top: 12px; border-top: 1px solid #1a1a1a;
}
.reasoning-col h4 { font-size: 12px; color: #666; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
.reasoning-col p { font-size: 13px; color: #aaa; line-height: 1.7; }

/* Approach docs */
.approach-doc {
    background: #111; border: 1px solid #222; border-radius: 8px;
    margin-bottom: 8px; overflow: hidden;
}
.approach-doc summary {
    padding: 14px 20px; cursor: pointer; font-size: 14px;
    color: #ccc; font-weight: 500;
}
.approach-doc summary:hover { background: #1a1a1a; }
.approach-content {
    padding: 8px 20px 20px; font-size: 13px; color: #aaa;
    max-height: 400px; overflow-y: auto;
}
.approach-content h3, .approach-content h4, .approach-content h5, .approach-content h6 {
    color: #ddd; margin: 16px 0 8px; font-size: 14px;
}
.approach-content p { margin: 6px 0; line-height: 1.6; }
.approach-content ul { margin: 6px 0 6px 20px; }
.approach-content li { margin: 3px 0; }
.approach-content code {
    background: #1a1a1a; padding: 2px 6px; border-radius: 3px;
    font-size: 12px; color: #e0e0e0;
}
.approach-content strong { color: #ddd; }

/* Moodboard */
.moodboard-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 8px;
}
.moodboard-grid img {
    width: 100%; border-radius: 6px; border: 1px solid #222;
    transition: border-color 0.2s;
}
.moodboard-grid img:hover { border-color: #444; }

.muted { color: #444; font-style: italic; }

/* Responsive */
@media (max-width: 900px) {
    .concepts-grid { grid-template-columns: 1fr; }
    .reasoning-block { grid-template-columns: 1fr; }
    .header .meta { flex-direction: column; gap: 8px; }
}
@media (max-width: 600px) {
    body { padding: 12px; }
    .moodboard-grid { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); }
}
'''


def generate_dashboard(run_dir: Path, output_path: Optional[Path] = None) -> Path:
    """Generate the dashboard HTML."""
    if output_path is None:
        output_path = run_dir / "dashboard.html"

    meta = get_run_metadata(run_dir)
    pairs, ranking = load_pairwise(run_dir)

    # Build rank lookup: index -> {rank, wins}
    rank_map = {}  # type: Dict[int, dict]
    for r in ranking:
        rank_map[r["index"]] = r

    # Detect number of concepts
    num_concepts = len(ranking) if ranking else 3

    # Build screenshot cards
    cards = []
    for i in range(num_concepts):
        screenshot_path = run_dir / "screenshots" / f"concept-{i}.png"
        screenshot_b64 = None
        screenshot_mime = "image/jpeg"
        if screenshot_path.exists():
            try:
                screenshot_b64, screenshot_mime = resize_image_b64(screenshot_path, 540)
            except Exception as e:
                print(f"Warning: Could not process screenshot {screenshot_path}: {e}", file=sys.stderr)

        rank_info = rank_map.get(i)
        is_winner = rank_info is not None and rank_info.get("rank") == 1
        cards.append(build_concept_card(i, rank_info, screenshot_b64, screenshot_mime, is_winner))

    concepts_html = "\n".join(cards)
    pairwise_html = build_pairwise_section(pairs)
    approach_html = build_approach_section(run_dir, num_concepts)
    moodboard_html = build_moodboard(run_dir)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Dashboard — {escape_html(meta["name"])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>Pipeline Dashboard</h1>
    <div class="meta">
        <span>Run: <strong>{escape_html(meta["name"])}</strong></span>
        <span>Phase: <strong>{escape_html(meta["phase"])}</strong></span>
        <span>Iteration: <strong>{escape_html(meta["iteration"])}</strong></span>
    </div>
</div>

<div class="section-title">Concepts</div>
<div class="concepts-grid">
{concepts_html}
</div>

<div class="section-title">Pairwise Results</div>
<div class="pairwise-section">
{pairwise_html}
</div>

<div class="section-title">Approach Docs</div>
{approach_html}

<div class="section-title">Moodboard</div>
<div class="moodboard-grid">
{moodboard_html}
</div>

</div>
</body>
</html>'''

    output_path.write_text(html)
    return output_path


def is_valid_run(d: Path) -> bool:
    """Check if a directory is a valid pipeline run (has builds/ with at least one .html)."""
    builds_dir = d / "builds"
    if not builds_dir.is_dir():
        return False
    return any(builds_dir.glob("*.html"))


def infer_phase(run_dir: Path) -> str:
    """Infer the current phase of a run from its file structure."""
    # Check cost-report.json first for explicit phase
    cost_report = run_dir / "cost-report.json"
    if cost_report.exists():
        try:
            data = json.loads(cost_report.read_text())
            if "phase" in data:
                return data["phase"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Check state.json
    state_file = run_dir / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            if "phase" in state:
                return state["phase"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Infer from file structure
    if (run_dir / "reviews" / "pairwise-results.json").exists():
        return "human_gate"
    if any((run_dir / "builds").glob("*.html")):
        has_reviews = (run_dir / "reviews").is_dir() and any((run_dir / "reviews").iterdir())
        if has_reviews:
            return "reviewed"
        return "building"
    if (run_dir / "concepts").is_dir() and any((run_dir / "concepts").glob("*.md")):
        return "designing"
    if (run_dir / "moodboard").is_dir():
        return "researching"
    return "unknown"


def get_run_cost(run_dir: Path) -> Optional[float]:
    """Extract total cost from cost-report.json if available."""
    cost_report = run_dir / "cost-report.json"
    if not cost_report.exists():
        return None
    try:
        data = json.loads(cost_report.read_text())
        return data.get("total_cost") or data.get("totalCost") or data.get("cost")
    except (json.JSONDecodeError, KeyError):
        return None


def get_run_iteration(run_dir: Path) -> int:
    """Get iteration count from state.json."""
    state_file = run_dir / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            return state.get("iteration", 0)
        except (json.JSONDecodeError, KeyError):
            pass
    # Try cost-report.json
    cost_report = run_dir / "cost-report.json"
    if cost_report.exists():
        try:
            data = json.loads(cost_report.read_text())
            return data.get("iteration", 0)
        except (json.JSONDecodeError, KeyError):
            pass
    return 0


def get_pairwise_stats(run_dir: Path) -> dict:
    """Extract winner and agreement stats from pairwise results."""
    result = {"winner": None, "winner_index": None, "agreed": 0, "disagreed": 0}
    path = run_dir / "reviews" / "pairwise-results.json"
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text())
        ranking = data.get("ranking", [])
        pairs = data.get("pairs", [])
        if ranking:
            top = ranking[0]
            result["winner_index"] = top.get("index")
            result["winner"] = f"Concept {top['index']}"
        for p in pairs:
            if p.get("agreed"):
                result["agreed"] += 1
            else:
                result["disagreed"] += 1
    except (json.JSONDecodeError, KeyError):
        pass
    return result


def get_thumbnails_b64(run_dir: Path, max_count: int = 3) -> List[Tuple[str, str]]:
    """Get base64 thumbnails from screenshots/concept-{i}.png, resized to 180px wide JPEG q50."""
    thumbnails = []
    screenshots_dir = run_dir / "screenshots"
    if not screenshots_dir.is_dir():
        return thumbnails
    for i in range(max_count):
        path = screenshots_dir / f"concept-{i}.png"
        if path.exists():
            try:
                b64, mime = resize_image_b64(path, 180, fmt="JPEG", quality=50)
                thumbnails.append((b64, mime))
            except Exception:
                pass
    return thumbnails


def format_date(ts: float) -> str:
    """Format a timestamp to a human-friendly date string."""
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%b %-d, %Y  %-I:%M%p").replace("AM", "a").replace("PM", "p")


def build_run_card(run_dir: Path, dashboard_filename: str) -> str:
    """Build an HTML card for a single run in the index view."""
    import os
    name = run_dir.name
    mtime = os.path.getmtime(str(run_dir))
    date_str = format_date(mtime)
    phase = infer_phase(run_dir)
    cost = get_run_cost(run_dir)
    iteration = get_run_iteration(run_dir)
    pairwise = get_pairwise_stats(run_dir)
    thumbnails = get_thumbnails_b64(run_dir)

    cost_str = f"${cost:.2f}" if cost is not None else "N/A"

    # Phase badge colors
    phase_colors = {
        "human_gate": "#fbbf24",
        "approved": "#4ade80",
        "rejected": "#f87171",
        "building": "#60a5fa",
        "designing": "#a78bfa",
        "researching": "#f472b6",
        "reviewed": "#38bdf8",
        "unknown": "#666",
    }
    phase_color = phase_colors.get(phase, "#666")

    # Thumbnails HTML
    thumbs_html = ""
    if thumbnails:
        thumb_items = []
        for b64, mime in thumbnails:
            thumb_items.append(
                f'<img src="data:{mime};base64,{b64}" class="run-thumb">'
            )
        thumbs_html = '<div class="run-thumbs">' + "".join(thumb_items) + '</div>'

    # Winner / pairwise info
    winner_html = ""
    if pairwise["winner"]:
        agreed = pairwise["agreed"]
        disagreed = pairwise["disagreed"]
        winner_html = f'''<div class="run-winner">
            <div class="winner-label">Winner: <strong>{escape_html(pairwise["winner"])}</strong></div>
            <div class="judge-stats">{agreed} agreed, {disagreed} disagreed</div>
        </div>'''

    return f'''
    <div class="run-card">
        <div class="run-header">
            <div class="run-name">{escape_html(name)}</div>
            <div class="run-date">{escape_html(date_str)}</div>
        </div>
        <div class="run-meta">
            <span class="phase-badge" style="color:{phase_color};border-color:{phase_color}33;background:{phase_color}11">{escape_html(phase)}</span>
            <span class="run-stat">Iter: {iteration}</span>
            <span class="run-stat">Cost: {escape_html(cost_str)}</span>
        </div>
        <div class="run-body">
            {thumbs_html}
            {winner_html}
        </div>
        <a href="{escape_html(dashboard_filename)}" class="open-dashboard" target="_blank">Open Dashboard →</a>
    </div>'''


INDEX_CSS = '''
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0a0a0a; color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6; padding: 24px;
}
.container { max-width: 960px; margin: 0 auto; }

.index-header {
    border-bottom: 1px solid #222; padding-bottom: 20px; margin-bottom: 32px;
}
.index-header h1 {
    font-size: 14px; text-transform: uppercase; letter-spacing: 3px;
    color: #666; margin-bottom: 4px;
}
.index-header h1 span { color: #fbbf24; }
.index-header .subtitle {
    font-size: 22px; font-weight: 300; color: #aaa;
}

/* Run cards */
.run-card {
    background: #111; border: 1px solid #222; border-radius: 12px;
    margin-bottom: 16px; overflow: hidden;
    transition: border-color 0.2s;
}
.run-card:hover { border-color: #333; }
.run-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 20px 0;
}
.run-name { font-size: 18px; font-weight: 600; color: #e0e0e0; }
.run-date { font-size: 13px; color: #666; }
.run-meta {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 20px 12px; flex-wrap: wrap;
}
.phase-badge {
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1px; padding: 3px 10px; border-radius: 4px;
    border: 1px solid;
}
.run-stat { font-size: 13px; color: #888; }
.run-body {
    display: flex; align-items: flex-start; gap: 20px;
    padding: 0 20px 16px;
}
.run-thumbs { display: flex; gap: 8px; flex-shrink: 0; }
.run-thumb {
    width: 120px; height: 80px; object-fit: cover; object-position: top;
    border-radius: 6px; border: 1px solid #222;
}
.run-winner { font-size: 13px; color: #aaa; }
.run-winner .winner-label { margin-bottom: 2px; }
.run-winner .winner-label strong { color: #fbbf24; }
.run-winner .judge-stats { color: #666; font-size: 12px; }
.open-dashboard {
    display: block; text-align: center; padding: 12px;
    background: #1a1a1a; color: #aaa; text-decoration: none;
    font-size: 13px; font-weight: 500; letter-spacing: 0.5px;
    transition: background 0.2s, color 0.2s;
    border-top: 1px solid #222;
}
.open-dashboard:hover { background: #222; color: #fff; }

/* Stats footer */
.stats-footer {
    margin-top: 32px; padding: 20px;
    background: #111; border: 1px solid #222; border-radius: 12px;
}
.stats-footer h2 {
    font-size: 11px; text-transform: uppercase; letter-spacing: 2px;
    color: #555; margin-bottom: 12px;
}
.stats-grid {
    display: flex; gap: 32px; flex-wrap: wrap;
}
.stat-item { }
.stat-value { font-size: 20px; font-weight: 600; color: #e0e0e0; }
.stat-label { font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 1px; }

@media (max-width: 600px) {
    body { padding: 12px; }
    .run-body { flex-direction: column; }
    .run-thumb { width: 100px; height: 66px; }
    .stats-grid { gap: 16px; }
}
'''


def generate_index(runs_dir: Path, output_path: Path) -> List[Path]:
    """Generate index page and per-run dashboards. Returns list of generated files."""
    import os

    generated = []
    output_dir = output_path.parent

    # Find valid runs
    runs = []
    for d in sorted(runs_dir.iterdir()):
        if d.is_dir() and is_valid_run(d):
            mtime = os.path.getmtime(str(d))
            runs.append((d, mtime))

    # Sort by date descending
    runs.sort(key=lambda x: x[1], reverse=True)

    if not runs:
        print("No valid pipeline runs found.", file=sys.stderr)
        sys.exit(1)

    # Generate per-run dashboards and build cards
    cards_html = []
    total_cost = 0.0
    cost_count = 0
    phase_counts = {}  # type: Dict[str, int]

    for run_dir, _mtime in runs:
        run_name = run_dir.name
        dashboard_filename = f"dashboard-{run_name}.html"
        dashboard_path = output_dir / dashboard_filename

        # Generate per-run dashboard
        try:
            generate_dashboard(run_dir, dashboard_path)
            generated.append(dashboard_path)
            print(f"  Generated: {dashboard_path.name} ({dashboard_path.stat().st_size / 1024:.0f} KB)")
        except Exception as e:
            print(f"  Warning: Failed to generate dashboard for {run_name}: {e}", file=sys.stderr)
            continue

        # Build card
        card_html = build_run_card(run_dir, dashboard_filename)
        cards_html.append(card_html)

        # Accumulate stats
        phase = infer_phase(run_dir)
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        cost = get_run_cost(run_dir)
        if cost is not None:
            total_cost += cost
            cost_count += 1

    # Stats
    total_runs = len(runs)
    approved = phase_counts.get("approved", 0)
    rejected = phase_counts.get("rejected", 0)
    avg_cost = total_cost / cost_count if cost_count > 0 else 0

    # Phase breakdown items
    phase_items = ""
    for phase, count in sorted(phase_counts.items()):
        phase_items += f'<div class="stat-item"><div class="stat-value">{count}</div><div class="stat-label">{escape_html(phase)}</div></div>\n'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚡ Creative Pipeline — All Runs</title>
<style>{INDEX_CSS}</style>
</head>
<body>
<div class="container">

<div class="index-header">
    <h1><span>⚡</span> Creative Pipeline</h1>
    <div class="subtitle">All Runs</div>
</div>

{"".join(cards_html)}

<div class="stats-footer">
    <h2>Stats</h2>
    <div class="stats-grid">
        <div class="stat-item"><div class="stat-value">{total_runs}</div><div class="stat-label">Total Runs</div></div>
        <div class="stat-item"><div class="stat-value">{approved}</div><div class="stat-label">Approved</div></div>
        <div class="stat-item"><div class="stat-value">{rejected}</div><div class="stat-label">Rejected</div></div>
        <div class="stat-item"><div class="stat-value">${total_cost:.2f}</div><div class="stat-label">Total Cost</div></div>
        <div class="stat-item"><div class="stat-value">${avg_cost:.2f}</div><div class="stat-label">Avg Cost/Run</div></div>
    </div>
    <div class="stats-grid" style="margin-top:16px;padding-top:12px;border-top:1px solid #1a1a1a">
        {phase_items}
    </div>
</div>

</div>
</body>
</html>'''

    output_path.write_text(html)
    generated.insert(0, output_path)
    return generated


def main():
    parser = argparse.ArgumentParser(description="Generate pipeline dashboard HTML")
    parser.add_argument("--run-dir", default=None, help="Path to the pipeline run directory")
    parser.add_argument("--index", action="store_true", help="Generate multi-run index page")
    parser.add_argument("--runs-dir", default=None, help="Directory containing run subdirectories (for --index)")
    parser.add_argument("--output", default=None, help="Output HTML path")
    args = parser.parse_args()

    if args.index:
        # Index mode
        runs_dir = Path(args.runs_dir).resolve() if args.runs_dir else Path("../overnight-runs").resolve()
        if not runs_dir.is_dir():
            print(f"ERROR: Runs directory not found: {runs_dir}", file=sys.stderr)
            sys.exit(1)
        output_path = Path(args.output).resolve() if args.output else (runs_dir / "index.html")
        print(f"Scanning runs in: {runs_dir}")
        generated = generate_index(runs_dir, output_path)
        print(f"\nGenerated {len(generated)} files:")
        for f in generated:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name}: {size_kb:.1f} KB")
    elif args.run_dir:
        # Single-run mode (original behavior)
        run_dir = Path(args.run_dir).resolve()
        if not run_dir.is_dir():
            print(f"ERROR: Run directory not found: {run_dir}", file=sys.stderr)
            sys.exit(1)
        output_path = Path(args.output).resolve() if args.output else None
        result = generate_dashboard(run_dir, output_path)
        size_mb = result.stat().st_size / (1024 * 1024)
        print(f"Dashboard generated: {result}")
        print(f"Size: {size_mb:.2f} MB")
    else:
        parser.error("Either --run-dir or --index is required")


if __name__ == "__main__":
    main()
