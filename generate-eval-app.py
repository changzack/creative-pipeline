#!/usr/bin/env python3
"""Generate a mobile-first evaluation app for pipeline taste gate.

Reads build artifacts from a run directory and produces a self-contained HTML app
that captures structured per-concept, per-dimension, technique-level feedback.

Usage:
  python generate-eval-app.py --run-dir ../runs/my-run --output /tmp/eval-app.html
"""

import argparse
import json
import re
import html as html_mod
from pathlib import Path


def extract_techniques_from_approach(approach_content: str) -> list:
    """Extract technique names from approach doc's BUILD CONTRACT section."""
    techniques = []
    in_section = False
    for line in approach_content.split("\n"):
        lower = line.lower().strip()
        if "required css" in lower or "required technique" in lower or "technical approach" in lower:
            in_section = True
            continue
        if lower.startswith("###") and in_section:
            in_section = False
        if in_section and (line.strip().startswith("- ") or line.strip().startswith("| ")):
            # Extract technique name
            name = line.strip().lstrip("- |").split(":")[0].split("|")[0].split("(")[0].strip()
            name = re.sub(r'`[^`]*`', '', name).strip()
            if name and len(name) > 3 and len(name) < 60:
                techniques.append(name)
    return techniques[:12]  # Cap at 12


def generate_eval_html(run_dir: Path, builds_base_url: str = "") -> str:
    """Generate the evaluation app HTML."""
    
    builds_dir = run_dir / "builds"
    concepts_dir = run_dir / "concepts"
    
    # Collect build info
    builds = []
    for html_file in sorted(builds_dir.glob("concept-*.html")):
        idx = int(html_file.stem.split("-")[1])
        size_kb = html_file.stat().st_size // 1024
        
        # Try to find approach doc for techniques
        techniques = []
        for approach_file in concepts_dir.glob(f"*APPROACH*"):
            content = approach_file.read_text(errors="ignore")
            techniques = extract_techniques_from_approach(content)
            if techniques:
                break
        
        # Try to detect model from pipeline state or filename
        model = "unknown"
        
        builds.append({
            "index": idx,
            "filename": html_file.name,
            "size_kb": size_kb,
            "techniques": techniques,
            "url": f"{builds_base_url}/builds/{html_file.name}" if builds_base_url else f"builds/{html_file.name}",
        })
    
    # Try to load ranking from pipeline state
    ranking_info = {}
    cost_info = ""
    
    # Check for cost report
    for cost_file in run_dir.glob("cost-report*.json"):
        try:
            cost_data = json.loads(cost_file.read_text())
            cost_info = f"${cost_data.get('total_cost', 0):.2f}"
        except:
            pass
    
    run_name = run_dir.name
    builds_json = json.dumps(builds, indent=2)
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=no">
<title>Evaluate: {run_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  :root {{
    --bg: #0a0a0a; --card: #111; --border: #222; --text: #eee;
    --text-dim: #888; --accent: #4a9eff; --great: #22c55e;
    --ok: #eab308; --bad: #ef4444; --standout: #f59e0b;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', Inter, sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100dvh; overflow-x: hidden;
    padding-bottom: env(safe-area-inset-bottom, 20px);
    -webkit-font-smoothing: antialiased;
  }}
  
  /* Header */
  .header {{
    position: sticky; top: 0; z-index: 100;
    background: rgba(10,10,10,0.95); backdrop-filter: blur(10px);
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }}
  .header h1 {{ font-size: 16px; font-weight: 600; }}
  .header .meta {{ font-size: 12px; color: var(--text-dim); }}
  
  /* Progress dots */
  .progress {{ display: flex; gap: 6px; padding: 8px 16px; }}
  .progress .dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--border); transition: all 0.3s;
  }}
  .progress .dot.active {{ background: var(--accent); transform: scale(1.3); }}
  .progress .dot.rated {{ background: var(--great); }}
  
  /* Concept card */
  .concept {{ display: none; padding: 0 16px 100px; }}
  .concept.active {{ display: block; }}
  
  .build-frame {{
    width: 100%; aspect-ratio: 9/16; max-height: 50vh;
    border: 1px solid var(--border); border-radius: 8px;
    overflow: hidden; margin: 8px 0; position: relative;
    background: #000;
  }}
  .build-frame iframe {{
    width: 100%; height: 100%; border: none;
    transform-origin: top left;
  }}
  .build-frame .expand-btn {{
    position: absolute; bottom: 8px; right: 8px;
    background: rgba(0,0,0,0.7); color: #fff; border: none;
    padding: 6px 12px; border-radius: 4px; font-size: 12px;
    cursor: pointer; z-index: 10;
  }}
  
  .model-tag {{
    display: inline-block; font-size: 11px; padding: 2px 8px;
    border-radius: 4px; background: var(--border); color: var(--text-dim);
    margin: 4px 0;
  }}
  
  /* Quick rating */
  .rating-row {{
    display: flex; gap: 8px; margin: 12px 0;
  }}
  .rating-btn {{
    flex: 1; padding: 14px 8px; border-radius: 8px;
    border: 2px solid var(--border); background: transparent;
    color: var(--text); font-size: 15px; font-weight: 600;
    cursor: pointer; transition: all 0.2s; text-align: center;
  }}
  .rating-btn.selected {{ border-color: var(--accent); background: rgba(74,158,255,0.1); }}
  .rating-btn.great.selected {{ border-color: var(--great); background: rgba(34,197,94,0.1); }}
  .rating-btn.ok.selected {{ border-color: var(--ok); background: rgba(234,179,8,0.1); }}
  .rating-btn.bad.selected {{ border-color: var(--bad); background: rgba(239,68,68,0.1); }}
  
  /* Dimensions */
  .dimensions {{ margin: 16px 0; }}
  .dim-label {{ font-size: 12px; color: var(--text-dim); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .dim-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }}
  .dim-dots {{ display: flex; gap: 6px; }}
  .dim-dot {{
    width: 28px; height: 28px; border-radius: 50%;
    border: 2px solid var(--border); background: transparent;
    cursor: pointer; transition: all 0.2s; display: flex;
    align-items: center; justify-content: center; font-size: 12px;
    color: var(--text-dim);
  }}
  .dim-dot.filled {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  
  /* Technique tags */
  .tech-section {{ margin: 16px 0; }}
  .tech-section h3 {{ font-size: 13px; color: var(--text-dim); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .tech-tag {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 6px 10px; margin: 3px; border-radius: 6px;
    border: 1px solid var(--border); background: transparent;
    color: var(--text); font-size: 13px; cursor: pointer;
    transition: all 0.2s;
  }}
  .tech-tag[data-state="landed"] {{ border-color: var(--great); color: var(--great); }}
  .tech-tag[data-state="standout"] {{ border-color: var(--standout); background: rgba(245,158,11,0.1); color: var(--standout); }}
  .tech-tag[data-state="partial"] {{ border-color: var(--ok); color: var(--ok); }}
  .tech-tag[data-state="missed"] {{ border-color: var(--bad); color: var(--bad); }}
  
  /* Notes */
  .note-field {{
    width: 100%; padding: 12px; margin: 12px 0;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); font-size: 14px;
    resize: vertical; min-height: 60px; font-family: inherit;
  }}
  .note-field::placeholder {{ color: var(--text-dim); }}
  
  /* Navigation */
  .nav-bar {{
    position: fixed; bottom: 0; left: 0; right: 0;
    background: rgba(10,10,10,0.95); backdrop-filter: blur(10px);
    border-top: 1px solid var(--border);
    padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
    display: flex; gap: 8px;
  }}
  .nav-btn {{
    flex: 1; padding: 14px; border-radius: 8px;
    border: none; font-size: 15px; font-weight: 600;
    cursor: pointer; transition: all 0.2s;
  }}
  .nav-btn.primary {{ background: var(--accent); color: #fff; }}
  .nav-btn.secondary {{ background: var(--card); color: var(--text); border: 1px solid var(--border); }}
  .nav-btn:disabled {{ opacity: 0.3; }}
  
  /* Submit screen */
  .submit-screen {{ display: none; padding: 16px 16px 120px; }}
  .submit-screen.active {{ display: block; }}
  .verdict-btn {{
    width: 100%; padding: 18px; margin: 6px 0;
    border-radius: 10px; border: 2px solid var(--border);
    background: transparent; color: var(--text);
    font-size: 17px; font-weight: 600; cursor: pointer;
    transition: all 0.2s; text-align: left; padding-left: 20px;
  }}
  .verdict-btn.selected {{ border-color: var(--accent); background: rgba(74,158,255,0.1); }}
  
  /* Output */
  .output-box {{
    width: 100%; min-height: 120px; padding: 12px;
    background: #000; border: 1px solid var(--border);
    border-radius: 8px; color: var(--great); font-family: monospace;
    font-size: 11px; margin: 12px 0; word-break: break-all;
  }}
  .copy-btn {{
    width: 100%; padding: 16px; border-radius: 10px;
    border: none; background: var(--great); color: #000;
    font-size: 16px; font-weight: 700; cursor: pointer;
  }}
  
  /* Fullscreen overlay */
  .fullscreen-overlay {{
    display: none; position: fixed; inset: 0; z-index: 999;
    background: #000;
  }}
  .fullscreen-overlay.active {{ display: block; }}
  .fullscreen-overlay iframe {{ width: 100%; height: 100%; border: none; }}
  .fullscreen-close {{
    position: fixed; top: 12px; right: 12px; z-index: 1000;
    background: rgba(0,0,0,0.7); color: #fff; border: none;
    width: 40px; height: 40px; border-radius: 50%;
    font-size: 20px; cursor: pointer;
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>🎨 {run_name}</h1>
    <div class="meta">{len(builds)} concepts {f'• {cost_info}' if cost_info else ''}</div>
  </div>
  <div class="progress" id="progress"></div>
</div>

<!-- Concept cards (generated by JS) -->
<div id="concepts-container"></div>

<!-- Submit screen -->
<div class="submit-screen" id="submit-screen">
  <h2 style="margin-bottom:16px">Overall Verdict</h2>
  
  <button class="verdict-btn" onclick="setVerdict('approve')">✅ Approve — ship it</button>
  <button class="verdict-btn" onclick="setVerdict('iterate')">🔄 Iterate — has potential, needs another round</button>
  <button class="verdict-btn" onclick="setVerdict('reject')">❌ Reject — start fresh</button>
  
  <textarea class="note-field" id="overall-note" placeholder="Overall thoughts..." rows="3"></textarea>
  
  <div id="output-section" style="display:none; margin-top:20px">
    <h3 style="margin-bottom:8px; color:var(--text-dim)">Copy this to Telegram:</h3>
    <div class="output-box" id="output-json"></div>
    <button class="copy-btn" onclick="copyOutput()">📋 Copy to Clipboard</button>
    <p style="text-align:center; margin-top:12px; color:var(--text-dim); font-size:13px">
      Paste in Telegram chat with: <code>verdict: [paste]</code>
    </p>
  </div>
</div>

<!-- Nav bar -->
<div class="nav-bar">
  <button class="nav-btn secondary" id="prev-btn" onclick="navigate(-1)" disabled>← Prev</button>
  <button class="nav-btn primary" id="next-btn" onclick="navigate(1)">Next →</button>
</div>

<!-- Fullscreen overlay -->
<div class="fullscreen-overlay" id="fullscreen">
  <button class="fullscreen-close" onclick="closeFullscreen()">✕</button>
  <iframe id="fullscreen-frame"></iframe>
</div>

<script>
const BUILDS = {builds_json};
const RUN_NAME = "{run_name}";
const TECH_STATES = ['', 'landed', 'standout', 'partial', 'missed'];
const TECH_ICONS = {{'': '○', 'landed': '✅', 'standout': '🔥', 'partial': '⚠️', 'missed': '❌'}};
const DIMS = [
  {{ key: 'creative_ambition', label: 'Creative Ambition', weight: '40%' }},
  {{ key: 'ai_slop', label: 'AI Slop Check (5=no slop)', weight: '20%' }},
  {{ key: 'visual_depth', label: 'Visual Depth', weight: '15%' }},
  {{ key: 'typography', label: 'Typography', weight: '10%' }},
  {{ key: 'hierarchy', label: 'Hierarchy', weight: '10%' }},
];

let currentIdx = 0;
let ratings = BUILDS.map(b => ({{
  index: b.index, model: b.model || 'unknown', rating: '',
  dimensions: {{}}, techniques: {{}}, note: ''
}}));
let verdict = '';

function init() {{
  // Build progress dots
  const prog = document.getElementById('progress');
  BUILDS.forEach((b, i) => {{
    const dot = document.createElement('div');
    dot.className = 'dot' + (i === 0 ? ' active' : '');
    dot.id = `dot-${{i}}`;
    prog.appendChild(dot);
  }});
  // Add submit dot
  const sdot = document.createElement('div');
  sdot.className = 'dot'; sdot.id = 'dot-submit';
  prog.appendChild(sdot);
  
  // Build concept cards
  const container = document.getElementById('concepts-container');
  BUILDS.forEach((b, i) => {{
    const div = document.createElement('div');
    div.className = 'concept' + (i === 0 ? ' active' : '');
    div.id = `concept-${{i}}`;
    div.innerHTML = buildConceptHTML(b, i);
    container.appendChild(div);
  }});
}}

function buildConceptHTML(b, i) {{
  let techHTML = '';
  if (b.techniques && b.techniques.length > 0) {{
    techHTML = `<div class="tech-section">
      <h3>Techniques</h3>
      ${{b.techniques.map(t => 
        `<button class="tech-tag" data-concept="${{i}}" data-tech="${{t}}" data-state="" onclick="cycleTech(this)">${{t}}</button>`
      ).join('')}}
    </div>`;
  }}
  
  return `
    <div class="build-frame">
      <iframe src="${{b.url}}" loading="lazy"></iframe>
      <button class="expand-btn" onclick="openFullscreen('${{b.url}}')">⤢ Fullscreen</button>
    </div>
    <span class="model-tag">Concept ${{b.index}} • ${{b.model || '?'}} • ${{b.size_kb}}KB</span>
    
    <div class="rating-row">
      <button class="rating-btn great" onclick="setRating(${{i}},'great',this)">🔥 Great</button>
      <button class="rating-btn ok" onclick="setRating(${{i}},'ok',this)">✅ OK</button>
      <button class="rating-btn bad" onclick="setRating(${{i}},'bad',this)">❌ Bad</button>
    </div>
    
    <div class="dimensions">
      ${{DIMS.map(d => `
        <div class="dim-row">
          <div style="flex:1">
            <div class="dim-label">${{d.label}} <span style="opacity:0.5">${{d.weight}}</span></div>
            <div class="dim-dots">
              ${{[1,2,3,4,5].map(v => 
                `<div class="dim-dot" data-concept="${{i}}" data-dim="${{d.key}}" data-val="${{v}}" onclick="setDim(this)">${{v}}</div>`
              ).join('')}}
            </div>
          </div>
        </div>
      `).join('')}}
    </div>
    
    ${{techHTML}}
    
    <textarea class="note-field" id="note-${{i}}" placeholder="What worked? What didn't?" oninput="ratings[${{i}}].note=this.value"></textarea>
  `;
}}

function setRating(i, val, btn) {{
  ratings[i].rating = val;
  btn.parentElement.querySelectorAll('.rating-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  document.getElementById(`dot-${{i}}`).classList.add('rated');
}}

function setDim(el) {{
  const i = parseInt(el.dataset.concept);
  const dim = el.dataset.dim;
  const val = parseInt(el.dataset.val);
  ratings[i].dimensions[dim] = val;
  
  el.parentElement.querySelectorAll('.dim-dot').forEach(d => {{
    d.classList.toggle('filled', parseInt(d.dataset.val) <= val);
  }});
}}

function cycleTech(el) {{
  const i = parseInt(el.dataset.concept);
  const tech = el.dataset.tech;
  const current = el.dataset.state;
  const nextIdx = (TECH_STATES.indexOf(current) + 1) % TECH_STATES.length;
  const next = TECH_STATES[nextIdx];
  el.dataset.state = next;
  el.textContent = (next ? TECH_ICONS[next] + ' ' : '') + tech;
  if (next) ratings[i].techniques[tech] = next;
  else delete ratings[i].techniques[tech];
}}

function navigate(dir) {{
  const total = BUILDS.length + 1; // +1 for submit screen
  const newIdx = currentIdx + dir;
  if (newIdx < 0 || newIdx >= total) return;
  
  // Hide current
  if (currentIdx < BUILDS.length) {{
    document.getElementById(`concept-${{currentIdx}}`).classList.remove('active');
  }} else {{
    document.getElementById('submit-screen').classList.remove('active');
  }}
  document.getElementById(`dot-${{currentIdx < BUILDS.length ? currentIdx : 'submit'}}`).classList.remove('active');
  
  currentIdx = newIdx;
  
  // Show new
  if (currentIdx < BUILDS.length) {{
    document.getElementById(`concept-${{currentIdx}}`).classList.add('active');
  }} else {{
    document.getElementById('submit-screen').classList.add('active');
  }}
  document.getElementById(`dot-${{currentIdx < BUILDS.length ? currentIdx : 'submit'}}`).classList.add('active');
  
  // Update nav
  document.getElementById('prev-btn').disabled = currentIdx === 0;
  document.getElementById('next-btn').textContent = currentIdx === BUILDS.length - 1 ? 'Submit →' : 'Next →';
  document.getElementById('next-btn').disabled = currentIdx >= total - 1;
  
  window.scrollTo(0, 0);
}}

function setVerdict(v) {{
  verdict = v;
  document.querySelectorAll('.verdict-btn').forEach(b => b.classList.remove('selected'));
  event.target.classList.add('selected');
  generateOutput();
}}

function generateOutput() {{
  if (!verdict) return;
  
  const output = {{
    run: RUN_NAME,
    timestamp: new Date().toISOString(),
    verdict: verdict,
    overall_note: document.getElementById('overall-note').value,
    best_concept: ratings.reduce((best, r, i) => 
      r.rating === 'great' ? i : (best === -1 && r.rating === 'ok' ? i : best), -1),
    concepts: ratings.map(r => ({{
      index: r.index,
      model: r.model,
      rating: r.rating || 'unrated',
      dimensions: r.dimensions,
      techniques: r.techniques,
      note: r.note
    }}))
  }};
  
  document.getElementById('output-json').textContent = JSON.stringify(output);
  document.getElementById('output-section').style.display = 'block';
}}

// Also regenerate on note change
document.addEventListener('input', (e) => {{
  if (e.target.id === 'overall-note' && verdict) generateOutput();
}});

function copyOutput() {{
  const text = 'verdict: ' + document.getElementById('output-json').textContent;
  navigator.clipboard.writeText(text).then(() => {{
    const btn = document.querySelector('.copy-btn');
    btn.textContent = '✅ Copied!';
    setTimeout(() => btn.textContent = '📋 Copy to Clipboard', 2000);
  }});
}}

function openFullscreen(url) {{
  document.getElementById('fullscreen-frame').src = url;
  document.getElementById('fullscreen').classList.add('active');
}}
function closeFullscreen() {{
  document.getElementById('fullscreen').classList.remove('active');
  document.getElementById('fullscreen-frame').src = '';
}}

init();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate evaluation app")
    parser.add_argument("--run-dir", required=True, help="Path to run directory")
    parser.add_argument("--output", default=None, help="Output HTML file path")
    parser.add_argument("--builds-url", default="", help="Base URL for build files (if deployed)")
    args = parser.parse_args()
    
    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}")
        return
    
    html = generate_eval_html(run_dir, args.builds_url)
    
    output = Path(args.output) if args.output else run_dir / "eval-app.html"
    output.write_text(html)
    print(f"Eval app generated: {output} ({len(html)//1024}KB)")


if __name__ == "__main__":
    main()
