# Phase 4.5 Implementation Plan: Knowledge-Grounded Pipeline

**Date:** 2026-05-01
**Context:** Smoke test forensics revealed builders ignore approach doc specs. Root cause: no curated design knowledge injected, specs embedded in prose, no compliance verification.

---

## Architecture Principles Applied (from Deep Research)

### 1. Context Boundaries, Not Role Labels
The deep research (Dwivedi article) says: "Design around context boundaries, not roles." Each node should receive ONLY what it needs — not a 56KB reference dump, but the relevant subset.

### 2. Orchestrator Owns Assembly, Workers Own Execution
LangGraph graph is the orchestrator. It assembles context per node (selects which references, how much of each). Workers (Hermes jobs) execute within that assembled context. Workers never pick their own references.

### 3. State Must Survive Failures
Every node's output is validated before the graph advances. Missing approach doc → retry. Missing BUILD CONTRACT → retry. Bad spec compliance → retry with specific error. LangGraph checkpoint captures state after each successful node.

### 4. Knowledge is Infrastructure, Not Prompt Decoration
Reference docs aren't "nice to have in the prompt." They're the curated knowledge layer (Layer 5 in the 9-layer architecture). The pipeline should fail differently without them — not just produce worse output, but actively flag "missing knowledge dependency."

---

## What Changes, Where, and Why

### 1. RESEARCH NODE — Gets Quality Lens

**File:** `pipeline.py` → `research_node()`

**Before:** "Search for 5-8 reference sites relevant to this brief"
**After:** Gets `art-direction-rubric.md` and `creative-patterns.md` injected.

**How:**
```python
# Load knowledge layer
rubric = load_reference("art-direction-rubric.md", max_chars=4000)
patterns = load_reference("creative-patterns.md", max_chars=3000)
```

**What this changes:**
- Researcher evaluates references against the rubric (not just "looks cool")
- Research output LABELS patterns found ("This reference uses a trophy-case display pattern")
- Moodboard screenshots are filtered — only references that score well on the rubric get captured

**Resilience:** If rubric file is missing, research still runs but logs a warning. The rubric is an enhancement, not a hard dependency.

**Context budget:** ~7KB added to research prompt (rubric 4KB + patterns 3KB). Research prompt was ~2KB before → ~9KB total. Well within limits.

---

### 2. DESIGNER NODE — Gets Technique Menu + Output Format

**File:** `pipeline.py` → `designer_node()`

**Before:** Freeform approach doc. Designer invents techniques from model prior.
**After:** Gets `enhancement-tactics.md`, `advanced-techniques.md` (summary), and `design-contract-template.md` as output format.

**How:**
```python
# Load technique menu — summarized, not raw 56KB dump
tactics = load_reference("enhancement-tactics.md", max_chars=5000)
techniques_summary = load_reference("advanced-techniques.md", max_chars=4000, 
                                      section="## Technique Index")  # Just the index, not full docs
contract_template = load_reference("design-contract-template.md")  # ~4KB, full
```

**What this changes:**
- Designer picks from a PROVEN technique menu instead of inventing from scratch
- Output follows design-contract-template with Non-Negotiables + Acceptance Criteria
- Techniques reference actual CSS properties/values from the tactics doc
- "FORBIDDEN" section explicitly blocks other concepts' palettes/fonts (populated by the orchestrator based on what other designers pick — requires approach gate to enforce)

**Resilience:**
- If tactics file is missing → designer still writes a spec, just without the menu
- If template is missing → falls back to the BUILD CONTRACT format we already have
- advanced-techniques.md is 56KB — ONLY inject the technique index (table of contents), not the full doc. Designer can reference specific sections by name in the approach doc; builder gets the relevant section extracted.

**Context budget:** ~13KB added (tactics 5KB + techniques index 4KB + template 4KB). Designer prompt was ~35KB (persona + brief + research). Total ~48KB — heavy but within Opus context. The research content should be summarized to ~3KB to compensate.

---

### 3. APPROACH GATE — Gets Cross-Concept Verification

**File:** `pipeline.py` → `approach_gate_node()`

**Before:** Checks for convergence in prose.
**After:** Also verifies design contracts are valid and non-overlapping.

**How:**
```python
# Extract concrete specs from each design contract
for approach in approaches:
    contract = extract_build_contract(approach['content'])
    fonts = extract_fonts(contract)
    colors = extract_colors(contract)
    
    # Check: do any two concepts share fonts?
    # Check: do any two concepts share primary colors?
    # If overlap found → flag for designer revision
```

**What this changes:**
- Convergence detection is MECHANICAL, not LLM-judged
- Can detect "Designer 0 and Designer 2 both spec'd Oswald" before any building happens
- Gate populates FORBIDDEN sections: "Designer 1 is using Oswald and #E63B2E, so your FORBIDDEN list must include those"

**Resilience:** If a design contract is malformed (no clear font/color section), the gate flags it and the designer reruns with a more specific prompt about the template format.

---

### 4. BUILDER NODE — Gets Recipes + Contract-First Prompt

**File:** `pipeline.py` → `builder_node()`

**Before:** Full approach doc (33KB of prose) + persona. Builder picks what to implement.
**After:** Extracted design contract (Non-Negotiables only, ~3KB) + relevant recipes from `recipes.md` + creative narrative as background context.

**How:**
```python
# Extract the contract — this is what the builder MUST follow
contract = extract_build_contract(approach_content)

# Find relevant recipes based on techniques in the contract
relevant_techniques = extract_technique_names(contract)
recipes = load_relevant_recipes("recipes.md", relevant_techniques, max_chars=6000)

# Creative narrative is context, not instructions
narrative = approach_content.split("## BUILD CONTRACT")[0][:3000]  # Truncated
```

**What this changes:**
- Builder gets a SHORT, grep-able contract first (3KB, not 33KB)
- Relevant code recipes are injected: "Here's a working grain overlay implementation"
- Creative narrative is background reading, clearly separated from hard requirements
- The prompt says: "Your output will be verified against the Acceptance Criteria section"

**Resilience:**
- If recipes.md is missing → builder still has the contract specs
- If contract extraction fails → falls back to full approach doc (current behavior)
- Recipe matching is keyword-based (grep for "grain", "halftone", "stagger") — no LLM needed

**Context budget:** Contract 3KB + recipes 6KB + narrative 3KB + persona 5KB = ~17KB. DOWN from ~38KB (full approach doc). Less context, more signal.

---

### 5. SPEC COMPLIANCE CHECK — New Automated Node

**File:** `pipeline.py` → `spec_compliance_node()` (NEW)

**Placed:** Between builder output and judge. Not a graph node — a function called inside builder_node before returning.

**How:**
```python
def check_spec_compliance(html_path: Path, contract: str) -> dict:
    """Grep-based compliance check. No LLM needed."""
    html = html_path.read_text()
    results = {"pass": True, "failures": []}
    
    # Extract required fonts from contract
    for font in extract_required_fonts(contract):
        if font.lower() not in html.lower():
            results["failures"].append(f"MISSING REQUIRED FONT: {font}")
            results["pass"] = False
    
    # Extract forbidden fonts
    for font in extract_forbidden_fonts(contract):
        if font.lower() in html.lower():
            results["failures"].append(f"CONTAINS FORBIDDEN FONT: {font}")
            results["pass"] = False
    
    # Extract required colors
    for color in extract_required_colors(contract):
        if color.lower() not in html.lower():
            results["failures"].append(f"MISSING REQUIRED COLOR: {color}")
            results["pass"] = False
    
    # Extract required techniques
    for technique, css_check in extract_required_techniques(contract):
        if css_check.lower() not in html.lower():
            results["failures"].append(f"MISSING TECHNIQUE: {technique} ({css_check})")
            results["pass"] = False
    
    return results
```

**On failure:** Re-run builder with a VERY short prompt:
```
Your build failed spec compliance:
- MISSING REQUIRED FONT: Playfair Display (you used Bebas Neue instead)
- CONTAINS FORBIDDEN FONT: Bebas Neue
- MISSING REQUIRED COLOR: #0F1419

Fix ONLY these issues. Do not change anything else.
```

**Max 2 retries.** After 2 failures, log and advance to judge anyway (with compliance failures noted in the judge context).

**Resilience:** Pure grep — no API calls, no cost, deterministic. Runs in <1 second.

---

## Utility Function: Reference Loader

```python
def load_reference(filename: str, max_chars: int = None, section: str = None) -> str:
    """Load a reference doc from the skills directory. 
    Respects context budget with max_chars truncation.
    Can extract a specific section by heading."""
    path = WORKSPACE / f"skills/creative-technologist/references/{filename}"
    if not path.exists():
        print(f"  ⚠️  Reference missing: {filename}")
        return ""
    content = path.read_text()
    if section:
        # Extract just the named section
        if section in content:
            start = content.index(section)
            next_heading = content.find("\n## ", start + len(section))
            content = content[start:next_heading] if next_heading > 0 else content[start:]
    if max_chars:
        content = content[:max_chars]
    return content
```

---

## Summary of Resilience Improvements

| Failure Mode | Before | After |
|---|---|---|
| Approach doc missing | Builder gets "Approach not generated", improvises | Retry with file read wait, fail loudly if still missing |
| Approach doc has no concrete specs | Builder guesses from prose | Design contract template enforces structured output; gate validates |
| Builder uses wrong fonts/colors | Undetected until human review | Automated grep check, retry with specific error |
| Two concepts converge on same palette | Detected by LLM gate (unreliable) | Mechanical extraction + comparison (deterministic) |
| Reference docs missing | Pipeline doesn't know they exist | Warning logged, fallback to current behavior |
| Builder overwhelmed by context | 38KB input, triages and misses specs | 17KB input — contract first, recipes for implementation, narrative as background |
| Same technique specced but not implemented | Hope the builder follows through | Acceptance criteria are literal grep commands; compliance check runs them |

---

## Implementation Order

1. `load_reference()` utility function
2. Research node — inject rubric + patterns (~30 min)
3. Designer node — inject tactics + template + techniques index (~30 min)
4. `extract_build_contract()` + `check_spec_compliance()` functions (~1 hour)
5. Approach gate — mechanical convergence detection (~30 min)
6. Builder node — contract-first prompt restructure (~30 min)
7. Smoke test: run one pipeline with new prompts (~3 hours for full run)

**Total estimated implementation: ~3 hours coding + 3 hours smoke test**
