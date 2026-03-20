# Complex Design System

Status: synthesized from the SMPLX prototype design-system document plus live production patterns in `complex-ui`, `components`, and `complex-hydrogen`.

Purpose: this file is both a design-system summary and an agent prompt guide. It describes not just tokens, but the actual Complex visual language as it appears in production.

## Source Hierarchy

When sources conflict, use this order:

1. `PRODUCTION/components`
   This is the strongest source of truth for shared tokens, grid behavior, semantic colors, typography utilities, buttons, product cards, and navigation primitives.
2. `PRODUCTION/complex-ui`
   This defines the editorial expression: hero behavior, feed rhythm, article body width, cover-story treatment, and the broader Complex.com content experience.
3. `PRODUCTION/complex-hydrogen`
   This defines the commerce expression: PDP and PLP utility typography, mono metadata, filters, product modules, footer, and shop-specific layout behavior.
4. `complex-prototype/DESIGN-SYSTEM.md`
   Treat this as conceptual intent and Figma mapping, not the final production source of truth.

## Complex In Words

Complex is a black-and-white-first editorial system with a commerce engine inside it.

It should feel:

- image-led, not UI-led
- hard-edged, not soft
- bold, not loud for the sake of loudness
- modular, not ornamental
- contemporary magazine first, storefront second
- premium through restraint, not through luxury tropes

The default Complex surface is a white field with black type, hairline borders, uppercase labels, and assertive imagery. Black is used as a high-contrast event surface for heroes, footers, live states, overlays, and immersive modules. Color is supporting, not the lead voice.

## Brand Principles

### 1. Hierarchy comes from layout first

Complex pages do not rely on decorative color shifts or oversized effects to create hierarchy. They use:

- strong image crops
- clear module boundaries
- decisive typography
- shifts between full-bleed and contained sections
- contrast between portrait cards, feed cards, and hero treatments

### 2. Uppercase is for framing, not for everything

Uppercase is heavily used for:

- navigation
- labels
- tags
- metadata
- buttons
- filter controls
- utility UI

Headlines are usually title case or sentence case, not all caps.

### 3. Borders matter more than shadows

Complex uses:

- border separators
- hairlines
- crisp containment
- black/white inversion

It generally avoids:

- soft card shadows
- floating glass surfaces
- blurred pastel backgrounds
- rounded app-like shells

### 4. Editorial and commerce share a visual language

The shop is not a separate brand. Commerce should still feel like Complex:

- same high-contrast palette
- same uppercase UI language
- same 4:5 product imagery and hard-edged controls
- more utility typography, more mono, more structured metadata

## Core Visual Language

### Palette

The canonical shared palette is semantic and neutral-heavy.

#### Canonical semantic colors

- `Text-Primary`: `#000000`
- `Text-Secondary`: `#40444A`
- `Text-Tertiary`: `#8F959D`
- `Text-Primary-Inverse`: `#FFFFFF`
- `Text-Secondary-Inverse`: `#9EA3AA`
- `Text-Tertiary-Inverse`: `#5A6069`
- `Background-B1`: `#FFFFFF`
- `Background-B2`: `#F8F8F8`
- `Background-B3`: `#F0F1F2`
- `Background-B1-Inverse`: `#000000`
- `Border-Primary`: `#E1E3E5`
- `Border-Secondary`: `#ADB1B7`
- `Border-Primary-Inverse`: `#303338`
- `Brand-Background-Black`: `#000000`
- `Brand-Stroke-Black`: `#202225`

#### Production support colors that appear frequently

These are live in production and should be treated as approved support values:

- `#666666` for muted body/support copy
- `#999999` for secondary utility copy
- `#E6E6E6` for borders and separators
- `#333333` and `#131313` for deep neutral surfaces
- `#DB1C1C` as live/accent/error red in newer shared components
- `#F03C3C` as legacy red in older editorial surfaces

### Color behavior

- Default page chrome is white.
- Use black as the major contrast surface, not as constant background wallpaper.
- Red is a signal color, not a brand fill color.
- Avoid introducing new accent palettes unless a campaign explicitly requires them.
- If a surface feels like it needs more color to work, the layout is probably weak.

## Typography

### Type families

There are three real production type roles:

1. `Inter`
   The default system font for headlines, labels, body, and the semantic typography utilities.
2. `Neue Haas Unica`
   Used in parts of commerce, editorial callouts, modules, and some elevated UI where a slightly more designed sans is needed.
3. `Roboto Mono`
   Used for utility metadata, filters, prices, timestamps, cart summaries, legal support text, and other mechanical UI moments.

There are campaign and special-use fonts in `complex-ui`, but they are not part of the default design language.

### Practical typography rules

- Use `Inter` for most page-level work unless the component already uses `Neue Haas Unica` or `Roboto Mono`.
- Use `Roboto Mono` sparingly for utility data, not as the main editorial voice.
- Use uppercase labels above headlines.
- Keep headline line-height tight.
- Keep body copy roomy and readable.

### Two typography utility systems are live

Production contains two overlapping utility families:

1. Newer semantic token classes from shared components
   Examples: `headings-28-semi-bold`, `tags-labels-12-bold`, `text-14-regular`, `color-text-primary`

2. Older web design system utility classes
   Examples: `text-h1`, `text-h2`, `text-sh1`, `text-l3-caps`, `text-body3`

Do not invent a third system. When editing an existing file, keep the utility family already used in that file.

### Common live text roles

- Page hero headline: large, bold or semibold, tight line-height
- Section title: `20px` mobile, `28px` desktop is a common production pattern
- Channel/tag label: `10px` to `14px`, uppercase, bold or semibold
- Body copy: typically `16px` with generous line-height
- Utility/legal/meta: `10px` to `12px`, often mono or uppercase

## Grid And Layout

### Production grid source of truth

The live shared grid in `components/src/tailwindConfig.ts` is:

- Mobile: `390px` breakpoint, `4` columns, `16px` outer margin, `8px` gutter
- Tablet: `744px` breakpoint, `8` columns, `20px` outer margin, `12px` gutter
- Desktop: `1440px` breakpoint, `12` columns, `40px` outer margin, `16px` gutter

Related spacing tokens:

- `--grid-margin`
- `--grid-padding`
- `--grid-spacing`

### Layout primitive

Use `grid-container` as the default layout primitive in shared/components-based work.

This is the key mental model:

- Full-bleed modules: the root should be full width; nest `grid-container` inside the module for contained content.
- Contained modules: `grid-container` can live on the root.

### Safe width behavior

- The main content system centers around a `1440px` max width.
- Some shop landing surfaces expand beyond that, but the content still reads as a centered editorial/commercial stage.
- Article body copy is much narrower than the site grid: standard article text is usually constrained to `720px` max width.

### Spacing rhythm

Complex likes clean vertical rhythm:

- consistent module stacks
- strong section breaks
- borders to close modules
- more breathing room on desktop than mobile

Avoid irregular spacing that makes each block feel like a standalone startup card.

## Imagery And Aspect Ratios

### Working ratio system

Across the source doc and production, the live pattern is:

- `4:5`: primary portrait/editorial card ratio and primary product card ratio
- `3:2`: feed/news/article card ratio
- `16:9`: hero/video/billboard ratio on larger screens
- `1:1`: utility and occasional mobile hero fallback

### Use these ratios like this

- Cover story / large hero:
  Mobile should feel tall and immersive.
  Desktop should feel billboard-like.
  `4:5` mobile and `16:9` desktop is the safest prompt default.
- Editorial cards:
  Use `4:5` for curated, image-forward modules.
- Feed cards:
  Use `3:2` for latest stories, horizontal feeds, and scannable story lists.
- Product cards:
  Use `4:5`.
- Mega menu and supporting nav imagery:
  Use `4:5`.

### Image behavior

- Images should do real narrative work.
- Use strong crops and `object-cover`.
- Hover behavior is subtle: saturation increase or light emphasis, not zoom theatrics.
- Overlay text should remain readable through white chips or dark translucent backing, not heavy gradients everywhere.

## Surface Treatments

There are a few recurring Complex treatments:

### 1. White chip on image

Used for:

- navigation cards
- CTA labels
- image overlays
- certain commerce promos

This is a crisp white text box or chip that can invert to black on hover.

### 2. Black translucent blur chip

Used for:

- hero labels
- elevated banner text
- over-image framing when white would be too harsh

### 3. Black stage

Used for:

- footer
- immersive hero moments
- live/timeline/video modules
- modals and overlays

When a module goes black, typography flips fully and metadata moves to inverse grays.

## Component Grammar

### Header And Navigation

Complex navigation is one of the clearest brand markers.

It is:

- white by default
- bordered on the bottom
- uppercase at level 1
- logo-left, utilities-right
- supported by optional promo bars and live indicators
- paired with a hard-edged mega menu that often uses `4:5` imagery

Desktop header rhythm:

- promo/event bar above
- main white nav band
- bold uppercase links
- search, wishlist, account, cart to the right

Mobile header rhythm:

- compact white bar
- small black logo lockup or custom brand mark
- dropdown/explore behavior
- icons plus hamburger

### Section Headers

The section header pattern is stable:

- left-aligned section title
- optional right-aligned `SEE ALL`
- mobile title around `20px`
- desktop title around `28px`
- semibold or bold
- minimal decoration

### Buttons

Complex buttons are functional and direct.

Defaults:

- uppercase
- bold
- black/white inversion
- square or near-square edges
- border-first styling

Live button patterns:

- black fill / white text for primary
- white fill / black text with hover inversion
- outlined white or black variants
- some shared components use `4px` radius
- many shop CTAs are effectively square-cornered

Guidance:

- Use pill buttons only for actual pill/quick-link UI.
- Do not use large soft rounded rectangles for primary CTAs.

### Pills And Quick Links

Quick-link pills are:

- compact
- rounded-full
- uppercase
- `29px` high in shared components
- black when active
- white with gray border when inactive

### Editorial Cards

Editorial cards usually include:

- a small uppercase channel or tag label
- a semibold/bold headline
- optional short dek
- optional byline/date
- a border-bottom separator in feeds

Common live card types:

- full hero card
- lead-plus-supporting cards
- stacked feed cards
- horizontal image-left cards

### Product Cards

The product-card system is one of the strongest production patterns.

Characteristics:

- `4:5` image ratio
- black/white base
- top-left badge or label
- wishlist/quick-add affordances
- utility metadata near price and variants
- stronger use of mono and uppercase
- more explicit border treatments than editorial cards

### Footer

The footer is a black information block with dense structure.

Rules:

- black background
- white logo
- uppercase link group headings
- small mono/legal support text
- generous but not luxurious spacing
- newsletter form integrated as content, not as a floating ad

## Editorial System

### Homepage rhythm

The prototype doc is directionally right here, and production supports it:

- hero first
- curated portrait/image-led modules next
- then more repeatable feed structures
- then shop/newsletter/supporting modules

Avoid pages where every module has the same card count, same ratio, same section treatment, and same CTA position. Complex pages should feel modular but not repetitive.

### Module differentiation

If two adjacent editorial modules both use `4:5` cards, differentiate them through:

- lead-card behavior
- equal-grid vs lead-and-supporting structure
- metadata density
- section-header treatment
- CTA placement

Do not rely on changing colors just to distinguish modules.

### Article pages

The standard article body in `complex-ui` is clear:

- text width around `720px`
- `16px` body text
- strong headline scale
- simple black text on white
- blockquotes with a black left rule

This is not a maximalist magazine layout by default. It is clean, readable, and lets embedded modules do the expressive work.

## Commerce System

### Shop is sharper and more utilitarian

Compared to editorial, commerce adds:

- more mono
- more uppercase tracking
- more persistent filter and sorting chrome
- more explicit button states
- more price and variant information

### Typical commerce patterns

- sticky utility/filter bars
- `4:5` product cards
- black/white CTA inversion
- horizontal product metadata rows
- mono for quantity, totals, warnings, and legal small print
- large banner modules that still live inside the same black/white brand world

### Commerce should not become generic DTC

Avoid:

- beige lifestyle minimalism
- oversized rounded cards
- soft gradient backgrounds
- muted luxury palettes

Complex commerce should feel like a media brand selling products, not a generic Shopify theme.

## Motion

Complex motion is restrained and purposeful.

Common live patterns:

- `200ms` to `300ms` transitions
- slide-up
- slide-in-right
- marquee
- pulse/live indicators
- hover underline
- hover image saturation shift

Use motion to support:

- navigation reveal
- search/filter panels
- live states
- carousel movement
- button inversion

Do not use:

- bouncy spring-heavy motion
- exaggerated parallax
- decorative floating animation on core UI

## Shape, Borders, And Effects

### Radius

Use:

- `0` or visually square corners by default
- `4px` as the main small radius when needed
- full radius only for pills/chips

Avoid:

- `12px` to `24px` card radii for standard layout blocks

### Borders

Use borders aggressively and intentionally:

- section separators
- product controls
- quiet button states
- filter bars
- footer dividers

### Shadows

Minimal use. If a component needs a heavy shadow to read, it is probably not aligned with the system.

## On-Brand Prompt Rules For Agents

Use this section when prompting an agent to build a Complex-style interface.

### What to say

Include most of these constraints:

- Use a black/white/gray editorial palette with red only as a signal color.
- Use a `4`/`8`/`12` responsive grid with contained and full-bleed modules.
- Use `Inter` for most typography, `Neue Haas Unica` for elevated UI moments, and `Roboto Mono` for utility metadata.
- Keep nav, labels, and CTAs uppercase.
- Use `4:5` for curated/editorial and product cards, `3:2` for feed cards, `16:9` for desktop heroes and video.
- Prefer borders and inversion over shadows and decorative fills.
- Keep corners square or `4px`; reserve pills for actual pills.
- Make the page feel like a modern magazine, not a SaaS dashboard and not a generic DTC storefront.

### What not to say yes to

Reject or override these defaults:

- purple gradients
- glassmorphism
- pastel dashboards
- giant rounded cards
- center-stacked marketing-site hero cliches
- soft shadow-based hierarchy
- icon-heavy app chrome
- luxury beige ecommerce

### Prompt starter: editorial

Use this as a starting point:

```text
Design a Complex-style editorial page. Use a white background with black type and hairline borders, a full-bleed hero that is 4:5 on mobile and 16:9 on desktop, uppercase labels and navigation, 4:5 curated cards, 3:2 feed cards, Inter for core type, and a restrained black/white visual language. Keep the layout modular, image-led, and high-contrast. Use borders and inversion instead of heavy shadows or decorative gradients.
```

### Prompt starter: commerce

```text
Design a Complex-style commerce page. Keep the editorial black/white brand language, use 4:5 product cards, uppercase utility labels, mono metadata for filters/prices/totals, sharp bordered controls, and a strong grid-based layout. It should feel like Complex commerce, not a generic Shopify storefront: harder edges, stronger hierarchy, more utility type, and minimal decorative color.
```

## Implementation Rules For Engineers

### Preferred production primitives

- Use `grid-container` for layout in shared/components-based work.
- Use shared semantic color utilities such as `color-text-primary`, `color-background-b1`, and `color-border-primary`.
- Reuse existing typography utility families rather than creating one-off classes.
- Reuse product-card and module-header patterns when possible.

### When working in legacy `complex-ui`

- Expect older utility classes like `text-h1`, `text-body3`, and custom Tailwind values.
- Expect some legacy color values such as `#666`, `#999`, `#e6e6e6`, and `#f03c3c`.
- Preserve the local style system if the component is already consistent with itself.

### When working in `complex-hydrogen`

- Preserve the stronger utility/mono flavor.
- Keep controls crisp and dense.
- Maintain black footer, mono metadata, and hard-edged CTA behavior.

## Anti-Patterns

If a design has several of these, it is probably off-brand:

- large soft-radius cards everywhere
- colorful gradients as the main identity layer
- too much empty center alignment
- shadow-driven hierarchy
- overly playful iconography
- body copy or labels set too large
- no uppercase framing language
- every module using the same ratio and the same layout
- commerce that looks detached from editorial

## Quick Audit Checklist

Before shipping a new UI, check:

- Does it read as black/white first?
- Is there a clear hero/feed/module rhythm?
- Are labels and utility controls uppercase where expected?
- Are the image ratios aligned to the live card system?
- Are borders doing more work than shadows?
- Does the page feel modular and editorial, not generic?
- If it is commerce, does it still look like Complex?

## Reference Files

Useful files behind this synthesis:

- `/Users/zackchang/Documents/Work Projects/complex-prototype/DESIGN-SYSTEM.md`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/components/src/tokens/semanticColors.ts`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/components/src/tokens/semanticTypography.ts`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/components/src/tailwindConfig.ts`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/components/src/components/TopMenuNavigation/TopMenuNavigation.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/components/src/components/CoverStoryModule/CoverStoryModule.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/components/src/components/ProductCard/ProductCard.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/complex-ui/src/components/channel/HeroArticle/index.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/complex-ui/src/components/global/MegaFeedCard/index.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/complex-ui/src/components/article/portable-text/portableTextOverrideFactory.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/complex-ui/src/components/global/SiteFooter/index.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/complex-hydrogen/app/components/Layout.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/complex-hydrogen/app/components/Footer.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/complex-hydrogen/app/components/PageModules/ShopNowModule.tsx`
- `/Users/zackchang/Documents/Work Projects/PRODUCTION/complex-hydrogen/app/components/Search/ShopContainer.tsx`

