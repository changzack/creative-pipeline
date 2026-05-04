# Build Lessons: Mobile Viewport

## The Scale Bug (V3i)

### Problem
Cards designed at 1080×1920 use `transform: scale()` to fit smaller viewports. But `transform` does NOT change the element's layout box — it still occupies 1080×1920 in flow. On a 390px-wide phone with `overflow: hidden`, the content is invisible.

### Solution
Use CSS `zoom` instead of `transform: scale()`. `zoom` actually resizes the layout box.

```css
/* BAD — layout box stays 1080×1920 */
.card {
  width: 1080px;
  height: 1920px;
  transform: scale(0.36);  /* visually smaller but still 1080×1920 in flow */
}

/* GOOD — layout box actually shrinks */
.card {
  width: 1080px;
  height: 1920px;
  zoom: 0.36;  /* layout box becomes ~389×691 */
}
```

### GSAP autoAlpha:0 Issue
Builds that start with all items hidden (for reveal animation) render blank on mobile because:
1. GSAP sets `autoAlpha: 0` (visibility: hidden + opacity: 0)
2. If animation doesn't play, items stay invisible
3. Mobile users see nothing

**Rule:** Default state = ALL items visible. Animation starts from visible state.
Force-set visible on DOMContentLoaded as fallback.

### QA Check
Pipeline QA tests at both 1080×1920 AND 390×844 (iPhone). Checks:
- Items in viewport
- Scroll height vs viewport height
- Content reachability

Added in commit `76d3122`.
