# Creative Patterns by Content Type

Reference catalog of award-winning patterns organized by the type of experience being built. Use as inspiration and starting points, not templates.

## Table of Contents

1. [Editorial / Long-Form Content](#editorial)
2. [Product Launch / Drop Page](#product-launch)
3. [Brand Campaign / Microsite](#brand-campaign)
4. [Interactive Storytelling](#interactive-storytelling)
5. [Data Visualization / Infographic](#data-visualization)

---

## Editorial / Long-Form Content {#editorial}

**The goal**: Transform articles from walls of text into scroll-driven narratives where content unfolds cinematically.

### Pattern: Scroll-Driven Documentary
- Full-viewport sections that pin and transform as user scrolls
- Media (video, image, 3D) takes center stage; text overlays with timed reveals
- Progress indicator shows position in narrative
- **Key tech**: GSAP ScrollTrigger (pinning + scrub), Lenis smooth scroll
- **Reference vibes**: NYT "Snow Fall," Apple product pages, Bloomberg visual stories

### Pattern: Parallax Editorial
- Multiple depth layers (background image, midground text, foreground elements)
- Elements move at different scroll speeds creating natural depth
- Text blocks float over full-bleed imagery
- Pull quotes animate in from edges with stagger
- **Key tech**: GSAP ScrollTrigger with scrub, CSS transforms

### Pattern: Magazine Grid with Reveals
- Masonry or bento-grid layout where items animate in on scroll intersection
- Each card has unique hover behavior (image zoom, color shift, text reveal)
- Category/tag filtering with layout animation (FLIP technique)
- Oversized featured items break the grid
- **Key tech**: Framer Motion layout animations, GSAP Flip, CSS Grid

### Pattern: Immersive Media Story
- Alternating sections: full-screen media → text → full-screen media
- Video sections autoplay (muted) with scroll-controlled playback
- Text sections use kinetic typography — words reveal as you scroll
- Ambient sound option (user-initiated)
- **Key tech**: ScrollTrigger + HTML5 Video currentTime scrub, SplitText

## Product Launch / Drop Page {#product-launch}

**The goal**: Make the product the hero. Create desire, anticipation, and a sense of premium quality.

### Pattern: 3D Product Showcase
- Product model (shoe, bottle, gadget) floating in 3D space, rotatable
- Scroll controls rotation/angle, revealing features at key angles
- Annotation hotspots appear at specific rotation points
- Background shifts color/atmosphere with each feature
- **Key tech**: React Three Fiber, @react-three/drei (OrbitControls, Environment, ContactShadows), GSAP

### Pattern: The Cinematic Reveal
- Page opens dark/minimal, product gradually revealed through animation
- Particle/smoke/light effects as "curtain" dissolving
- Camera movement (zoom, orbit) creates cinematic tension
- Product details cascade in after reveal with staggered text
- **Key tech**: R3F postprocessing (bloom, vignette), custom shaders, GSAP timeline

### Pattern: Speed Scroll
- Ultra-long page with rapid scroll-synced content: specs, images, features fly by
- Numbers count up, stats animate, comparison bars fill
- Strategic "pause" sections with pinned deep-dives
- Creates a sense of abundance and excitement
- **Key tech**: GSAP ScrollTrigger scrub, pinning, counter animations

### Pattern: Countdown/Hype
- Pre-launch page with live countdown, animated
- Interactive elements (scratch to reveal, shake to unlock)
- Social proof (live counter of signups, waitlist position)
- Email capture with satisfying confirmation animation
- **Key tech**: Framer Motion, Canvas/WebGL effects, real-time data

## Brand Campaign / Microsite {#brand-campaign}

**The goal**: The site IS the campaign. Every pixel communicates the brand's energy, values, and vibe.

### Pattern: Full-Screen Takeover
- Each section is a full-viewport "slide" with distinct visual identity
- Transitions between sections are dramatic (wipe, morph, dissolve, 3D flip)
- Navigation is unconventional (horizontal scroll, drag, or scroll-hijacked)
- Heavy use of brand typography at massive scale
- **Key tech**: GSAP ScrollTrigger horizontal scroll, page transitions, CSS clip-path

### Pattern: Interactive Playground
- User makes choices that affect the visual output
- Generative art responds to user input (mouse, keyboard, device sensors)
- Personalized result or visual at the end (shareable)
- **Key tech**: Canvas 2D / WebGL, device APIs (gyroscope, microphone), R3F

### Pattern: Mixed Media Collage
- Overlapping images, video, text, and illustrations in organic layout
- Elements slightly rotate, overlap, and break alignment intentionally
- Sticker/cutout aesthetic with drop shadows and paper textures
- Mouse-reactive: elements shift slightly with cursor position
- **Key tech**: CSS transforms + perspective, mousemove parallax, clip-path, mix-blend-mode

## Interactive Storytelling {#interactive-storytelling}

**The goal**: User is a participant, not just a viewer. Choices, exploration, and discovery drive the experience.

### Pattern: Branching Narrative
- User choices fork the story into different visual/content paths
- Each path has distinct visual treatment (color palette, typography, animation style)
- Transitions between choices are dramatic (page morphs, environment shifts)
- **Key tech**: React state management, Framer Motion AnimatePresence, GSAP

### Pattern: Explorable Map/Space
- Non-linear content arranged spatially (map, universe, room)
- User navigates by clicking, dragging, or scrolling through space
- Content nodes reveal details on interaction
- Ambient animation keeps the space feeling alive
- **Key tech**: R3F for 3D spaces, Canvas for 2D maps, GSAP Draggable

### Pattern: Sequential Reveal
- Content is gated behind micro-interactions (click, type, drag, shake)
- Each interaction reveals the next piece of the story
- Gamification elements (progress, easter eggs, hidden content)
- **Key tech**: Framer Motion gestures, device APIs, custom interaction handlers

## Data Visualization / Infographic {#data-visualization}

### Pattern: Scroll-Driven Data Story
- Data builds progressively as user scrolls
- Charts/graphs animate in: bars grow, lines draw, numbers count
- Annotations appear at key data points
- Strategic pinned sections for complex data exploration
- **Key tech**: D3.js or Recharts + GSAP ScrollTrigger, counter animations

### Pattern: Interactive Explorer
- User controls the data view (filters, time ranges, categories)
- Transitions between data states are animated (morphing bars, flowing particles)
- Hover reveals contextual details with smooth tooltips
- **Key tech**: D3.js transitions, Framer Motion, Canvas for large datasets

### Pattern: Living Infographic
- Infographic elements are animated, not static
- Icons and illustrations are Lottie or SVG animations
- Numbers are live/dynamic
- Scroll position reveals sections of the infographic progressively
- **Key tech**: Lottie, SVG animation (GSAP), ScrollTrigger
