# Feedback Loop: Review Panel → Skill Learning

## Overview
After every review panel + iteration cycle, extract universal lessons and propose skill amendments. This closes the loop so the skill compounds in quality over time.

## Pipeline Step: `learn-from-reviews`

### When It Runs
- After iteration cycles complete (either hit 9.0+ target or exhausted max cycles)
- Before the final summary is delivered to the user

### What It Does

#### 1. Extract Patterns
Read all reviewer files and categorize feedback into:

- **UNIVERSAL** — same issue flagged by 3+ reviewers across multiple concepts
  → High-confidence skill amendment
- **RECURRING** — same issue in 2+ concepts but not all reviewers caught it
  → Medium-confidence, review before applying
- **ONE-OFF** — single concept, single reviewer
  → Project-specific, don't amend skill

#### 2. Classify by Skill Section

| Feedback Type | Maps To |
|--------------|---------|
| "Every concept used legacy ReactDOM.render()" | **Anti-Slop Rules** → add rule |
| "No GSAP cleanup anywhere" | **Anti-Slop Rules** → add rule |
| "SMPLX grounding universally poor" | **Core Principles** → strengthen principle |
| "Hover states too subtle" | **Enhancement Tactics** → add tactic |
| "Streak mechanic was best UX pattern" | **Recipes** → add or refine recipe |
| "Random values in render cause bugs" | **Anti-Slop Rules** → add rule |
| "No share artifact for social" | **Enhancement Tactics** → add tactic |

#### 3. Write Amendment Proposal
Output: `memory/skill-amendments/[date]-[project].md`

Format:
```markdown
# Skill Amendment Proposal — [Project Name]
Date: YYYY-MM-DD
Source: [N] reviewers across [M] concepts, [K] iteration cycles

## High Confidence (3+ reviewers, universal)
### Amendment 1: [Section] → [Change]
- Evidence: [quotes from reviewers]
- Current skill text: [what it says now]
- Proposed change: [what it should say]

## Medium Confidence (recurring but not universal)
### Amendment 2: ...

## Rejected (project-specific, not skill-level)
- [list of feedback that doesn't generalize]
```

#### 4. Review Gate
- Opus reviews the proposal
- Applies high-confidence amendments automatically
- Flags medium-confidence for human review
- Logs everything to skill-evolution

#### 5. Validate
After amendments are applied, run a quick sanity check:
- Does the skill still read coherently?
- Are new rules contradicting existing ones?
- Is the skill getting bloated? (If >5000 words, need to compress)

## Evidence Threshold

| Confidence | Criteria | Action |
|-----------|----------|--------|
| High | 3+ reviewers flagged it + appeared in 3+ concepts | Auto-apply |
| Medium | 2 reviewers OR 2+ concepts | Propose, wait for review |
| Low | 1 reviewer, 1 concept | Log only, don't amend |

## Anti-Bloat Rule
The skill must stay lean. For every new rule added, check if an existing rule can be:
- Merged (two rules about the same thing)
- Promoted (from detailed → concise principle)
- Retired (no longer relevant)

Target: SKILL.md stays under 3000 words. Detailed reference goes in `references/`.

## Compounding Effect
- Project 1: Skill produces ~6/10 first builds
- Project 2: After learning, ~7/10 first builds
- Project 3: ~7.5/10 first builds
- Project N: Approaching 8.5+ first builds, needing fewer iteration cycles

The goal is NOT to get the skill to produce perfect output — it's to raise the floor so iteration starts from a better place each time.
