# DESIGN-CONTRACT.md — Template

One per concept. Written after Stitch designs are approved, before build phase starts. This is the source of truth for what the builder can and cannot change.

```markdown
# Design Contract: {concept-name}
Date: {date}
Stitch Project: {project-id}
Aesthetic Direction: {direction from menu}

## Screen Map
| Screen | Stitch Screen ID | Description | State |
|--------|-----------------|-------------|-------|
| Cover | {id} | Landing/hero with CTA | Static → animates on load |
| Question | {id} | Active quiz question | Transitions per question |
| Feedback | {id} | Answer confirmation | 1-2 second transition state |
| Results | {id} | Final result/personality | Static with share CTA |
| Share | {id} | Social share moment | Screenshot-optimized |

## State Map
```
Cover → [Start] → Question 1 → [Answer] → Question 2 → ... → Question N → [Calculate] → Results → [Restart] → Cover
                                                                                          → [Share] → Share
```

### State Variables
| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| currentScreen | enum | "cover" | cover, question, calculating, results |
| currentQuestion | number | 0 | Index of active question |
| answers | array | [] | User's selected answers |
| score/type | varies | null | Calculated result |

## Non-Negotiables (FROZEN — builder must not change)
- [ ] Color palette: {list exact hex values from Stitch}
- [ ] Typography: {font, sizes, weights — exact values}
- [ ] Layout composition: {describe the spatial arrangement}
- [ ] Key visual elements: {hero image treatment, background style, etc.}
- [ ] SMPLX tokens: {which design system values are used}

## Allowed Interpretation Zones (builder has creative freedom here)
- [ ] Entrance animations: {how elements appear — timing, easing, stagger}
- [ ] Screen transitions: {how screens change — crossfade, slide, morph, etc.}
- [ ] Hover/click micro-interactions: {button responses, card effects}
- [ ] Loading states: {what happens during calculation/transition delays}
- [ ] Scroll behavior: {if applicable — parallax depth, reveal timing}

## Motion Notes
| Moment | Intent | Suggested Approach | Priority |
|--------|--------|-------------------|----------|
| Page load | Set the tone | {e.g., "staggered fade-in, hero first, then UI"} | Must-have |
| Start quiz | Energy shift | {e.g., "cover dissolves, question slides up"} | Must-have |
| Answer selection | Confirmation | {e.g., "selected option scales + color shift"} | Must-have |
| Question transition | Flow | {e.g., "current question exits left, next enters right"} | Must-have |
| Results reveal | Payoff moment | {e.g., "dramatic — calculating state → big reveal"} | Must-have |
| Hover states | Responsiveness | {e.g., "magnetic pull on CTA, subtle lift on options"} | Nice-to-have |

## Responsive Rules
| Breakpoint | What Changes | What Stays |
|-----------|-------------|-----------|
| Desktop (>1024px) | {full layout as designed in Stitch} | — |
| Tablet (768-1024px) | {specific adaptations} | {what's preserved} |
| Mobile (<768px) | {specific adaptations} | {what's preserved} |

## Asset List
| Asset | Source | Status | Fallback |
|-------|--------|--------|----------|
| Hero image | Stitch-generated | ✅ In design | {fallback if needed} |
| Background texture | Stitch-generated | ✅ In design | CSS grain overlay |
| Icons | {source} | {status} | {fallback} |

## Acceptance Criteria
The build passes when:
1. Side-by-side screenshot comparison with Stitch design shows <10% drift on non-negotiables
2. All states in the state map are reachable and render correctly
3. All motion notes marked "must-have" are implemented
4. Non-negotiable values match exactly (color hex, font sizes, spacing)
5. Responsive rules are followed at all breakpoints
```
