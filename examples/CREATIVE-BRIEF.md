# Creative Brief: Rerank Share Card Reimagination

## Context

Complex's "Rerank" feature lets users reorder curated lists (Top 10 Sneakers, Best Albums, etc.). After locking in their ranking, users get a share card — a visual summary of their list that they can share on social media.

**The current share card is utilitarian:** static image, numbered list with tiny 64px thumbnails, geometric background template. Every item treated equally. It works, but it's not something users would be proud to share.

## The Challenge

Reimagine the Rerank share card as something **worth sharing** — a visual artifact that makes people want to post it, that sparks conversation, that looks like it belongs on a curated Instagram story.

## Share Surfaces
- **Instagram Stories** (primary) — 1080×1920px, 9:16
- **iMessage** — preview card, flexible dimensions

## What We're Designing

A share card that visualizes a user's ranked list of 10 items. Each item has:
- Rank position (1-10)
- Name (text, up to ~30 chars)
- Thumbnail image (product shot — sneakers, albums, etc.)
- The list has a headline (e.g., "Top 10 Sneakers of 2025")
- Username of the person who ranked it

## Design Principles

1. **Visual hierarchy matters.** #1 should feel dramatically more important than #10. The current design treats all 10 items identically — this is the biggest opportunity.
2. **Make the top items hero.** Consider featuring the top 3 (or even just #1) prominently with large imagery, and treating the rest as a supporting list.
3. **It should feel like YOUR list.** The share card should feel personal and opinionated — this is someone's taste, their ranking, their statement.
4. **Think about the reveal.** This could be animated — items appearing one-by-one, building anticipation. Think Strava route replay or Spotify Wrapped reveals. How does the static version hint at that motion?
5. **Own visual identity.** This is NOT Complex.com editorial — it's a social-native share artifact. It should have its own bold, distinctive visual language.
6. **Readability on mobile.** This will be viewed on phones in Instagram Stories and iMessage. Text must be legible. Don't sacrifice readability for aesthetics.

## Current Design Reference

The current share card uses:
- 1080×1920 static image via Cloudinary URL transforms
- 3 template backgrounds (blue, red, orange geometric patterns on black)
- Rerank logo, headline, "Reranked By @username", numbered list, footer
- All 10 items shown identically: rank number + 64px thumbnail + name
- "MADE ON COMPLEX.COM" footer

## What Items Look Like

Real examples of list content:
- "Top 10 Sneakers of 2025" → Air Jordan 1, Yeezy 350, Nike Dunk, etc.
- "Best Hip-Hop Albums" → album covers + titles
- "Greatest NBA Players" → player photos + names

The imagery is always product/person shots — square-ish, high quality, from the Complex CMS.

## Outcome Requirements

1. **Static share card** that could be saved/screenshotted as an image (IG Stories format)
2. **Animated variant concept** — how this card could be revealed as a short video/GIF (items appearing, building tension toward #1)
3. The #1 item should be unmistakably the hero
4. The card should include: headline, user attribution, all 10 items (visually differentiated by importance), Complex/Rerank branding
5. Must work for ANY list topic (sneakers, albums, players, food, etc.)

## Sample Data (use this exact content in your prototype)

```
Headline: "Top 10 Sneakers of 2025"
User: "@derpchang"

1. Air Jordan 1 Retro High OG "Chicago"
2. Nike Dunk Low "Panda"
3. New Balance 550 "White Green"
4. adidas Samba OG
5. Nike Air Force 1 Low
6. ASICS Gel-Kayano 14 "Silver"
7. Air Jordan 4 Retro "Military Black"
8. Nike Air Max 1 "Obsidian"
9. New Balance 2002R "Protection Pack"
10. Salomon XT-6 "Black"
```

Use product names as-is. Thumbnail images can be placeholder colored rectangles — the visual system matters more than real photos at this stage.

## What NOT to Do

- Don't just reskin the current numbered list with a prettier background
- Don't make it look like a generic social media template
- Don't sacrifice the list readability for pure aesthetics
- Don't ignore the bottom half of the list (#6-10 still matter, just less)
- Don't build a Spotify Wrapped or music streaming recap — this is a ranked list of items, not a personal stats summary
- Don't use vintage boxing/fight card aesthetics — this has been done in 3+ past runs and always converges to the same output
- Don't use cream/newsprint backgrounds with red accents — overused in past runs
- Don't make a retro/vintage poster — explore modern, experimental, or futuristic directions instead

## Deliverables

**Approach doc only.** Do NOT build anything. Output:
- Color palette (exact hex values)
- Layout strategy (how the 10 items are arranged, what's hero'd)
- Typography choices
- Animation concept (how the reveal would work)
- One-paragraph description of the opening moment
- How visual hierarchy is achieved across all 10 items
- Mood/reference touchpoints
