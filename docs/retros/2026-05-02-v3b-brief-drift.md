# Retro: V3b Brief Drift — "Spotify Wrapped" instead of "Rerank Sharecard"
**Date:** 2026-05-02
**Run:** sharecard-v3b
**Verdict:** Visually much stronger (taste calibration worked!), but wrong product

## What Happened

The builds created Spotify Wrapped-style music cards (tracks, artists, songs) instead of Rerank Sharecards (sneakers, albums, ranked lists of 10 items with thumbnails).

## Root Cause Analysis

### 1. Research Phase Anchored on Spotify Wrapped
The research agent's moodboard is almost entirely Spotify Wrapped screenshots:
- `01-spotify-wrapped-2024-newsroom.png`
- `02-spotify-wrapped-2024-cards.png`
- `03-spotify-wrapped-2023-vucko-project.png`
- `05-spotify-decade-wrapped-share-cards.png`
- `06-spotify-decade-wrapped-seasonal-cards.png`

The brief mentions "Think Strava route replay or Spotify Wrapped reveals" as ONE reference for animation style. The researcher latched onto this and made it the ENTIRE moodboard.

### 2. Approach Docs Were Actually Correct
Ironically, the designer approach docs (Fight Card, Extra Extra, The Back Page) are all about Rerank-style ranked lists. They reference sneakers, ranked items, #1-10 hierarchy. The designers READ the brief correctly.

### 3. Builders Ignored the Approach Docs' Content, Used Moodboard as Template
The builders saw the moodboard (all Spotify Wrapped) and the approach doc (Rerank sharecard). When building, they defaulted to what they SAW (Spotify Wrapped visual patterns) rather than what they READ (Rerank ranked list of items). The moodboard images dominated over the text specs.

This is the same problem as the v1 spec drift, but at the content layer instead of the style layer.

### 4. No Sample Data in the Brief
The brief describes what items look like ("sneakers, albums, players") but doesn't provide ACTUAL sample data. The builders invented data, and with the Spotify moodboard as context, they invented music data.

## Fixes

### Fix 1: Add Sample Data to Brief (high impact, easy)
Include actual sample data in the brief:
```
## Sample Data (use this exact data in your prototype)
Headline: "Top 10 Sneakers of 2025"
User: "@derpchang"
1. Air Jordan 1 Retro High OG "Chicago"
2. Nike Dunk Low "Panda"
3. New Balance 550
...
```
This removes ambiguity about what the card shows.

### Fix 2: Curate the Moodboard (medium impact)
The research node currently searches freely. It should be guided to:
- NOT screenshot Spotify Wrapped (it's a reference for animation, not visual design)
- Focus on ranked list / leaderboard / editorial list designs
- Or: skip auto-moodboard and provide curated references

### Fix 3: Builder Content Validation (medium impact)
Add a content check: does the built HTML contain keywords from the brief's sample data? If the brief says "sneakers" and the build says "tracks/artists" — flag it.

### Fix 4: Separate Animation Reference from Visual Reference
The brief should distinguish:
- "For VISUAL DESIGN inspiration, look at: [editorial lists, fight cards, magazine layouts]"
- "For ANIMATION TIMING inspiration, look at: [Spotify Wrapped reveals, Strava replays]"

## Lessons
1. Moodboard images have MORE influence on builders than text specs — visual context dominates
2. Brief must include concrete sample data, not just descriptions of what data looks like
3. "Think Spotify Wrapped" in a brief = builders will make Spotify Wrapped
4. The taste calibration WORKED — visually much stronger output. The system just built the wrong product.

## Action Items
- [ ] Add sample data block to the sharecard brief
- [ ] Add "DO NOT make a Spotify Wrapped clone" to anti-patterns
- [ ] Consider curating moodboard manually or adding research constraints
