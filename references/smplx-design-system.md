# SMPLX Design System — Extracted Tokens & Components

Source: [SMPLX Design System (Figma)](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System)

---

## Font Family

| Token | Value |
|---|---|
| `Family/Primary` | `Inter` |

Weights available: Regular (400), Medium (500), Semi Bold (600), Bold (700)

---

## Color Tokens

### Semantic Colors

| Token | Hex | Usage |
|---|---|---|
| `Text/Primary` | `#000000` | Primary text color |
| `Text/Primary Inverse` | `#ffffff` | Text on dark backgrounds |
| `Text/Secondary` | `#40444a` | Secondary/supporting text |
| `Text/Tertiary` | `#8f959d` | Tertiary/muted text (e.g., labels) |
| `Text/Tertiary Inverse` | `#5a6069` | Tertiary text on dark backgrounds |
| `Background/B1` | `#ffffff` | Primary background (white) |
| `Background/B1 Inverse` | `#000000` | Inverse background (black) |
| `Background/B3` | `#f0f1f2` | Tertiary background (light gray) |
| `Border/Primary` | `#e1e3e5` | Primary border color |
| `Border/Primary Inverse` | `#303338` | Border on dark backgrounds |
| `Border/Secondary` | `#adb1b7` | Secondary border color |
| `Icons/Primary` | `#000000` | Primary icon color |
| `Icons/Primary Inverse` | `#ffffff` | Icons on dark backgrounds |
| `Icons/Primary White` | `#ffffff` | White icon variant |
| `Icons/Error` | `#db1c1c` | Error/notification icon color (red) |
| `Opacity/O1` | `rgba(255,255,255,0.2)` | 20% white overlay |
| `Brand/Background/Black` | `#000000` | Brand logo background |
| `Brand/Stroke/Black` | `#202225` | Brand logo border |
| `Primary/Default/Black` | `#000000` | Primary default black |

### Additional Color Scales (from Color page)
The full color page includes:
- **Neutrals**: Full grayscale spectrum with named stops and hex values
- **Opacity/Black%**: Black at various opacity levels (S1–S9)
- **Opacity/White%**: White at various opacity levels (S1–S9)
- **Red**: Red palette with multiple stops

These can be extracted in detail from Figma node `3:76` when needed.

---

## Typography Scale

All typography uses the `Inter` font family.

### Headings

| Style | Size | Line-Height | Letter-Spacing | Weights |
|---|---|---|---|---|
| `Heading/72pt` | 72px | 86px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/64pt` | 64px | 78px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/56pt` | 56px | 66px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/48pt` | 48px | 58px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/44pt` | 44px | 52px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/32pt` | 32px | 38px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/28pt` | 28px | 34px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/24pt` | 24px | 34px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/20pt` | 20px | 24px | 0px | Regular, Medium, Semi Bold, Bold |
| `Heading/18pt` | 18px | 28px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/16pt` | 16px | 22px | -1px | Regular, Medium, Semi Bold, Bold |
| `Heading/14pt` | 14px | 18px | 0px | Regular, Medium, Semi Bold, Bold |
| `Heading/12pt` | 12px | 14px | 0px | Regular, Medium, Semi Bold, Bold |
| `Heading/11pt` | 11px | 14px | -1px | Regular, Medium, Semi Bold, Bold |

### Tags & Labels

| Style | Size | Weight | Line-Height | Letter-Spacing | Transform |
|---|---|---|---|---|---|
| `Tags & Labels/12pt/Medium` | 12px | 500 | 14px | 0px | UPPERCASE |
| `Tags & Labels/12pt/Semi Bold` | 12px | 600 | 14px | 0px | UPPERCASE |
| `Tags & Labels/12pt/Bold` | 12px | 700 | 14px | 0px | UPPERCASE |
| `Tags & Labels/14pt/Semi Bold` | 14px | 600 | 18px | 0px | UPPERCASE |
| `Tags & Labels/14pt/Bold` | 14px | 700 | 18px | 0px | UPPERCASE |
| `Tags & Labels/16pt/Bold` | 16px | 700 | 20px | 0px | UPPERCASE |

### Body Text

| Style | Size | Weight | Line-Height | Letter-Spacing |
|---|---|---|---|---|
| `Text/14pt/Regular` | 14px | 400 | 22px | 0px |
| `Text/12pt/Medium` | 12px | 500 | 20px | 0px |

---

## Spacing Tokens

| Token | Value |
|---|---|
| `Spacing/None` | 0px |
| `Spacing/4` | 4px |
| `Spacing/8` | 8px |
| `Spacing/12` | 12px |
| `Spacing/16` | 16px |
| `Spacing/20` | 20px |
| `Spacing/24` | 24px |
| `Spacing/32` | 32px |
| `Spacing/38` | 38px |
| `Spacing/44` | 44px |

### Border Radius

| Token | Value |
|---|---|
| `Border-Radius/4` | 4px |

---

## Grid System

Source: [Grids 2.0 (Figma)](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=1800-10794)

| Breakpoint | Width Range | Columns | Col Width | Gutter | Margin | Safe Area |
|---|---|---|---|---|---|---|
| `xs` | 390px | 4 | 84px (flex) | 8px | 16px | 358px |
| `sm` | 640–767px | 4 | Flex | 8px | 16px | Flex |
| `md` | 768–1023px | 12 | Flex | 12px | 20px | Flex |
| `lg` | 1024–1279px | 12 | Flex | 12px | 20px | Flex |
| `xl` | 1280–1535px | 12 | Flex → 100px | 12px → 16px | 20px → 32px (FLEX) | Flex → 1376px fixed |
| `2xl` | 1536px+ | 12 | 100px | 16px | 32px (FLEX) | 1376px fixed & centered |

**Safe area lock:** Within the `xl` range, once the viewport reaches 1440px (32px × 2 + 1376px), the safe area locks to 1376px and margins grow flexibly. At `2xl` (1536px+) the 1376px safe area is always fixed and centered.

### Container Behavior Rules

- **Simple rule:** All content modules follow this grid unless they are product tiles. Parent container for product tiles will abide by the grid; tiles within will follow flex.
- **Navigation:** Fills all available horizontal space (full-width, edge-to-edge).
- **Container Type 1 (Editorial/Full-bleed):** Parent container's BACKGROUND will "FILL" all available space (edge-to-edge). Content within will always be bound by the grid limits (1376px safe area).
  - *Used for:* Navigation, Cover Story, Web Banner (Hero), Footer
- **Container Type 2 (Product/Card grids):** Parent container will respect the bounds of the grid with "FIXED" width. For Shop modules, the product tiles will have "FLEX" behavior.
  - *Used for:* Product tile grids, Trending Videos / carousels

### Implementation

- **One container for all pages:** `max-w-[1376px] mx-auto px-[var(--spacing-16)] md:px-[var(--spacing-20)] xl:px-[var(--spacing-32)]`
- There is no separate "homepage" container. The SMPLX grid (1376px safe area) is the single canonical grid for all pages.
- Use design system spacing tokens (`--spacing-16`, `--spacing-20`, `--spacing-32`) — not arbitrary `px-4`, `px-8`.
- Use standard Tailwind breakpoints (`sm:`, `md:`, `lg:`, `xl:`, `2xl:`) aligned to the breakpoints above.

---

## Aspect Ratio System

### Design Rationale

The aspect ratio system is a **visual hierarchy tool**, not just an image sizing spec. The system uses **two levers** to communicate editorial importance: **ratio** (shape of the image) and **size** (physical dimensions / column width). On mobile, ratio controls viewport fill percentage — the most powerful hierarchy signal. On desktop, column span does the heavy lifting.

**Core principles:**
1. **Ratio communicates content type** (portrait editorial vs. landscape news). **Size communicates importance within a type** (lead card = wide column, supporting cards = narrow columns).
2. **The same ratio at different sizes creates clear hierarchy** without requiring multiple portrait ratios. A 4:5 card at 680px wide reads as dramatically more important than a 4:5 card at 340px wide.
3. **Aspect ratio varies by placement context**, not by content. The same article renders at different ratios depending on the module it appears in.

### Ratio Palette

| Ratio | CSS Value | Mobile Height (full-width, 390px) | Viewport Fill (~844px) | Role |
|---|---|---|---|---|
| **4:5** | `aspect-ratio: 4/5` | 488px (full-width) / 325px (carousel card ~260px wide) | ~58% / ~38% | **Portrait tier** — all editorial module cards (leads and secondaries). Hierarchy expressed through size. |
| **16:9** | `aspect-ratio: 16/9` | 219px | ~26% | **Landscape tier** — feed cards, news grids, compact/secondary placements. Maximum scannability. |
| **1:1** | `aspect-ratio: 1/1` | 390px | ~46% | **Utility** — square content (album art, profile images, product shots). Not a tier assignment. |

**Why two ratios, not three:**
The previous 3-tier system used 3:4 (Showcase), 4:5 (Feature), and 16:9 (Standard). The 3:4 → 4:5 difference is only **6.25% in height** at any given width (e.g., 28px at 340px wide). This is not perceptible to users. Industry editorial design (NYT, The Atlantic, Pitchfork) universally uses a single portrait ratio and expresses hierarchy through column width. Collapsing to one portrait ratio (4:5) simplifies the system: one CMS crop target for portrait content, fewer design decisions per component, and hierarchy that's MORE legible through physical size difference rather than subtle shape change.

**Perceptual step between tiers (mobile):**
- Portrait (4:5 full-width, 488px) → Landscape (16:9, 219px): **~269px drop** — dramatic, unmistakable contrast
- Portrait carousel card (4:5 at ~260px wide, 325px) → Landscape (16:9, 219px): **~106px drop** — clear distinction

### Hero Treatment (Outside the Ratio System)

The Cover Story hero is **not a card** — it's a page-level event. It lives outside the ratio system and is defined by its **treatment** (full-bleed, viewport-filling, text overlay), not by a card ratio class.

| Breakpoint | Treatment | Notes |
|---|---|---|
| Mobile (390px) | Full-width, viewport-filling (~80-100vh) | Image crops to viewport. 9:16 is the approximate native proportion but is not enforced as a fixed ratio. |
| Tablet (1024px) | Full-width billboard | Same as desktop |
| Desktop (1440px) | Full-width billboard, 16:9 proportions | Full-bleed edge-to-edge, text overlay |

- **Frequency:** Single instance at top of page. Only one hero per page.
- **Content:** Cover stories, lead editorial, breaking news.
- **Why the hero isn't in the ratio system:** If the hero used 9:16 as a formal tier, any module that also used 9:16 would dilute the hero's supremacy. By keeping the hero as a special treatment (defined by position + full-bleed + overlay, not by ratio), nothing competes with it. The hero is supreme because of WHERE it is and HOW it's treated, not because of its shape.
- **Image requirement:** Separate mobile crop (`mobileImageUrl`) recommended for portrait framing. Source images must be >= 1200px wide (Google Discover).

### Visual Hierarchy Tiers

#### Portrait Tier (4:5)
**Purpose:** "This is curated." Editorial content with strong visual presence. Used for all module cards — hierarchy within modules is expressed through **column width**, not ratio change.

| Breakpoint | Ratio | Module Type | Cards Visible | Behavior |
|---|---|---|---|---|
| Mobile (390px) | **4:5** | Horizontal carousel | ~1.4 cards (card width ~65% viewport + peek) | Swipe horizontally, peek of next card visible |
| Tablet (1024px) | **4:5** | 3-up grid | 3 cards | Static grid, no scroll |
| Desktop (1440px) | **4:5** | Lead + grid (5 articles) or equal grid | 5 cards | Static grid, no scroll |

- **Frequency:** Repeatable. Each channel/vertical can have its own module.
- **Content:** Channel highlights, editorial picks, curated selections, Lists, Features.
- **Ratio is constant across all breakpoints.** 4:5 is the portrait tier's visual identity. Module shape changes (carousel → grid), but ratio does not.
- **Size-based hierarchy within modules:**
  - **Lead card:** Wide column (~6 cols on desktop). Largest image = most important story in the module.
  - **Supporting cards:** Narrow columns (~3 cols each). Smaller images = secondary stories.
  - The lead card reads as dramatically more important than supporting cards through physical size alone — no ratio change needed.
- **Mobile carousel specs:**
  - Card width: ~65-70% of viewport (~250-270px)
  - Gap between cards: `var(--spacing-8)` (8px)
  - Peek of next card must be visible (minimum 40px of next card showing)
  - Headline + metadata below each card image
- **Desktop/Tablet grid specs:**
  - Cards placed within the 12-column grid
  - Desktop: Lead card spans 6 cols, supporting cards fill remaining cols
  - Tablet: 3 cols per card (3-up)
  - Gap: `var(--spacing-16)` (16px)

#### Landscape Tier (16:9)
**Purpose:** "Here's more." The workhorse format for feeds, news grids, and secondary placements. Maximum scannability — the reader's eye goes to the headline, not the image.

| Breakpoint | Ratio | Module Type | Behavior |
|---|---|---|---|
| Mobile (390px) | **16:9** | Vertical feed (image-above-text or image-beside-text) | Vertical scroll |
| Tablet (1024px) | **16:9** | Vertical feed | Vertical scroll |
| Desktop (1440px) | **16:9** | Horizontal cards (image-left, text-right) or grid | Vertical scroll |

- **Frequency:** Repeatable. Used for Latest Stories feed, Top Stories secondary grid, category page feeds.
- **Content:** Latest stories, all-channel feed, filtered content, Top Stories secondary cards.
- **16:9 is the existing workflow standard.** No migration cost — CMS, image pipeline, and editorial muscle memory are already built around this ratio.
- **Appropriate for news-driven modules** where scannability matters more than visual presence (Top Stories, Latest Stories Feed).

### Module Differentiation Strategy

Lists and Features modules MUST use different **layout structures** to prevent module monotony. Differentiation comes from card arrangement, typography weight, metadata density, and grid composition — not from aspect ratio.

| Module | Layout Pattern | Differentiator |
|---|---|---|
| **Latest Features** | Lead card (wide) + supporting grid | Editorial hierarchy — one story dominates |
| **Latest Lists** | Equal-width cards or numbered items | Democratic/ranked — content is the hierarchy |

The specific layout patterns for each module are defined during implementation, but the constraint is firm: consecutive modules must be visually distinguishable at a glance.

### Adjacency Rules

- **Recommended page rhythm:** Hero → Portrait modules → Landscape feed, with Portrait modules forming a browsable zone
- The hero is unique — only one per page, always at top
- **Consecutive Portrait (4:5) modules are acceptable** when they form a cohesive channel browsing zone (e.g., Lists → Features → Music → Style → Sneakers). Section headers and layout structure differences provide visual separation.
- **Module separators** (hairline rules) should be used between modules for visual closure, especially when modules have different internal heights.
- The "highs and lows" rhythm is achieved by the contrast between the hero treatment, Portrait editorial modules, and Landscape feed — not by varying ratios within the Portrait tier.

### Utility Ratios (Non-Tier)

These ratios are available for specific non-editorial content needs but are not tier assignments:

| Ratio | Usage | Notes |
|---|---|---|
| 1:1 | Square content (album art, profile images, specific product shots) | Content-specific, not a hierarchy signal |
| 9:16 | Video/story content (Trending Videos) | Not used for article card imagery |
| 4:5 (product) | Product tiles in shop modules | Existing shop usage; Portrait tier adoption creates visual consistency between editorial and commerce |

---

## Components

### Button

**Sizes:**
| Size | Height |
|---|---|
| Large (L) | 44px |
| Medium (M) | 36px |
| Small (S) | 32px |

**Types:**
| Type | Description |
|---|---|
| Loud | Filled black background, white text |
| Soft | Gray background (`Background/B3`), dark text |
| Quiet | White background, border (`Border/Primary`) |
| Outline | Transparent background, border only |
| Ghost | Transparent, no border |
| Link | Text only, no background or border |

**Shared Properties:**
- Border radius: `4px`
- Horizontal padding: `Spacing/16` (16px)
- Vertical padding: `Spacing/12` (12px)
- Text: `Tags & Labels/12pt/Bold` (12px, Bold 700, uppercase)
- Icon size: 24px
- Icon-to-text gap: 8px
- States: Default, Disabled
- Inverse variants available (for dark backgrounds)

### Section Header

**Desktop (Platform=Desktop):**
- Width: 1376px (full safe area)
- Layout: Flexbox, space-between alignment
- Title: `Heading/28pt/Semi Bold` (28px, weight 600, line-height 34px)
- Subtitle: `Heading/14pt/Medium` (14px, weight 500, line-height 18px, color `Text/Secondary`)
- Optional feature tag: `Tags & Labels/12pt/Semi Bold`, color `Text/Tertiary`, uppercase
- Optional "SEE ALL" button (Soft type)
- Optional carousel arrows (Quiet type buttons with chevron icons)
- Gap between title and subtitle: `Spacing/16` (16px)

**Mobile (Platform=Mobile):**
- Title: `Heading/20pt/Semi Bold` (20px, weight 600, line-height 24px)
- Subtitle: `Heading/12pt/Medium` (12px, weight 500, line-height 14px)

**Props:**
- `featureTag`: boolean (show channel label above title)
- `showArrows`: boolean (show carousel navigation)
- `showButton`: boolean (show SEE ALL button)
- `showInteractions`: boolean (show button + arrows area)
- `subheading`: boolean (show subtitle text)

### Tags & Labels
- **Channel labels**: e.g., "COMPLEX NEWS" — small uppercase text
- **Brand name labels**: e.g., "[BRAND NAME]" — bordered tag
- **Status labels**: e.g., "[STATUS]" — includes red accent variant

### Article Tiles
Multiple layout variants available:
- Various sizes with image + title combinations
- Text positioned below or beside image
- Channel label optional above title

### Article Modules
Full article page components including:
- Hero images (full-width and split layouts)
- Content blocks with bylines and dates
- Pull quotes
- Product carousels
- Related content sections
- Story cards (vertical scrolling)

### Icon System

- **Family**: Sharp Line via Streamline
- **Stroke weight**: 1.5px
- **Sizes**: 16px, 24px, 32px
- **Source**: [Icons (Figma)](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=3-79)

**Only the icons listed below are approved for use.** To add a new icon, it must first be added to the Figma file and this list.

#### Chevrons
| Icon name | Figma node |
|---|---|
| `Icon/24/chevron-up` | `84:6955` |
| `Icon/24/chevron-down` | `84:6958` |
| `Icon/24/chevron-left` | `84:6956` |
| `Icon/24/chevron-right` | `84:6957` |

#### Arrows
| Icon name | Figma node |
|---|---|
| `Icon/24/top-up-arrow` | `299:45257` |
| `Icon/24/down-arrow` | `299:45256` |
| `Icon/24/left-arrow` | `299:45258` |
| `Icon/24/right-arrow` | `299:45255` |

#### Actions
| Icon name | Figma node |
|---|---|
| `Icon/24/plus-add` | `138:30578` |
| `Icon/24/close-cross` | `482:3124` |
| `Icon/24/check-tick` | `488:4728` |
| `Icon/24/dash-line-minus` | `1302:59153` |
| `Icon/24/setting-filter` | `1297:7908` |

#### Commerce
| Icon name | Figma node |
|---|---|
| `Icon/24/heart` | `138:30582` |
| `Icon/24/cart` | `196:28868` |
| `Icon/24/cart-active` | `254:36851` |

#### Media
| Icon name | Figma node |
|---|---|
| `Icon/24/play` | `206:33864` |
| `Icon/24/volume-loud` | `480:3964` |

#### Navigation & UI
| Icon name | Figma node |
|---|---|
| `Icon/24/search` | `254:36827` |
| `Icon/24/account-user-login` | `254:36842` |
| `Icon/24/menu-hamburger` | `287:37267` |
| `Icon/24/circle` | `134:25919` |

#### Calendar & Events
| Icon name | Figma node |
|---|---|
| `Icon/24/calendar` | `592:49773` |
| `Icon/24/calendar-check-rsvpd` | `1012:14894` |

#### Notifications & Status
| Icon name | Figma node |
|---|---|
| `Icon/24/bell-notification-default` | `1012:11202` |
| `Icon/24/bell-notification-check` | `1012:11203` |
| `Icon/24/check-circle` | `1221:809` |
| `Icon/24/check-circle-fill` | `1221:988` |

#### Social / User
| Icon name | Figma node |
|---|---|
| `Icon/24/user-add-follow` | `2075:534` |
| `Icon/24/user-check-following` | `2075:535` |

### Brand Elements

**Channel Logos (Vertical):**
- Style, Music, Sneakers, Pop Culture, Sports, Life, Shows
- Available in: circular filled (black bg), circular outlined, pill-shaped, text-only

**Complex Logos (DP):**
- Complex, Complex News, Pop Culture, Music, Sports, Sneakers, Style
- Available in: dark and light variants, circular and square formats

**Main Logos:**
- "COMPLEX" wordmark
- Stacked "COM/PLEX" variants (dark and light)

---

## CSS Custom Property Naming Convention

The design system uses CSS custom properties with this naming pattern:
```
--token-category/token-name
```

Examples:
```css
var(--text/primary, #000000)
var(--background/b1, #ffffff)
var(--border/primary, #e1e3e5)
var(--spacing/16, 16px)
var(--family/primary, 'Inter', sans-serif)
var(--tags-&-labels/12pt/bold/size, 12px)
var(--headings/14pt/medium/size, 14px)
```

---

## Page Context (from Complex.com Homepage)

Source: [SMPLX Handoff (Figma)](https://www.figma.com/design/7Rr2fIeqJjXOP18rLIsQe7/SMPLX-Handoff?node-id=5-73)

### Top Main Navigation — Desktop
- **Promo Banner** (optional):
  - Background: `Background/B3` (#f0f1f2)
  - Border bottom: `Border/Primary` (#e1e3e5)
  - Height: 36px
  - Padding: 24px horizontal, 12px vertical
  - Text: 12pt Regular promo text + 12pt Bold underlined uppercase CTA
  - Chevron arrows left/right
- **Nav Header**:
  - Background: `Background/B1` (white)
  - Border bottom: `Border/Primary` (#e1e3e5)
  - Height: 72px
  - Padding: 32px horizontal (logo area), 24px (links area), 38px (icons area)
  - Left: COMPLEX wordmark logo (95.248px × 24px)
  - Center: Nav links — `Tags & Labels/16pt/Bold`, uppercase, 32px gap
    - Active: `Text/Primary` (black) + 1px black underline
    - Default: `Text/Tertiary` (#8f959d)
  - Right: Icon buttons (search, heart, user, cart) — 24px icons, 24px gap

### Top Main Navigation — Mobile
- **Promo Banner**:
  - Same as desktop but narrower, centered text
  - Text: 10pt Regular + 10pt Bold underlined
- **Nav Header**:
  - Height: 48px
  - Padding: 16px horizontal
  - Left: COMPLEX stacked logo (72×72px square, black bg)
  - Center: "EXPLORE" dropdown — `Tags & Labels/14pt/Semi Bold`, uppercase + chevron-down
  - Right: Icons (search, heart, user, cart, hamburger menu) — 24px, 16px gap

### Footer — Mobile
- Background: `Background/B1 Inverse` (black)
- Padding: 32px top, 44px bottom, 16px horizontal
- Gap: 24px between sections
- **Logo**: COMPLEX wordmark (white, 95.248px × 24px)
- **Social links**: Facebook, X, WhatsApp, Instagram, YouTube, Snapchat, TikTok — 24px icons, 32px gap
- **Link sections** (separated by dividers):
  - Discover: Style, Music, Sneakers, Pop Culture, Sport, Life, Shows, ComplexCON, Family style
  - Shop: Shop, Drops, Support, Shipping Policy, Refund Policy
  - Work With Us: Careers, Advertise, Contact Us
  - Section titles: `Heading/14pt/Bold`, white, 176px width
  - Link text: `Text/14pt/Regular`, `Text/Tertiary` (#8f959d)
- **Newsletter**: Email input (48px height, `Opacity/O1` bg) + "GET NOTIFIED" button (Quiet type)
- **Country selector**: Dropdown, `Opacity/O1` bg, 40px height
- **Legal links**: `Text/12pt/Medium`, `Text/Tertiary`, 2-column grid (176px each)
- **Copyright**: `Heading/12pt/Regular`, `Text/Tertiary`
- **Accessibility button**: Icon + "ACCESSIBILITY" label

---

## Figma Node References

| Section | Node ID | URL |
|---|---|---|
| Components (page) | `41:6688` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=41-6688) |
| Button | `41:6689` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=41-6689) |
| Logos | `465:58813` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=465-58813) |
| Color | `3:76` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=3-76) |
| Type | `3:77` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=3-77) |
| Grid | `3:78` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=3-78) |
| Icon | `3:79` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=3-79) |
| Brand | `87:10728` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=87-10728) |
| Image Ratio | `84:114` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=84-114) |
| Top Main Navigation | `136:30342` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=136-30342) |
| Tags & Labels | `84:34` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=84-34) |
| Article Tiles | `82:9897` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=82-9897) |
| Article Modules | `471:57964` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=471-57964) |
| Section Header | `397:38660` | [Link](https://www.figma.com/design/1Op9CRCbOrgAt4yzR2yGWe/SMPLX-Design-System?node-id=397-38660) |

### SMPLX Handoff (Homepage Reference)

| Section | Node ID | URL |
|---|---|---|
| Homepage (page) | `5:73` | [Link](https://www.figma.com/design/7Rr2fIeqJjXOP18rLIsQe7/SMPLX-Handoff?node-id=5-73) |
| Desktop Homepage | `108:4117` | "New Drop- Hero- Desktop" (1440×9244) |
| Mobile Homepage | `108:4807` | "New Drop- Hero- Mobile" (390×7475) |
| Desktop Nav | `108:4118` | Top Main Navigation (Desktop) |
| Mobile Nav | `108:4844` | Top Main Navigation (Mobile) |
| Mobile Footer | `108:4991` | Footer (Mobile) |

### Homepage Redesign (Oct 25)

| Section | Node ID | URL |
|---|---|---|
| Desktop Homepage | `1218:6776` | [Link](https://www.figma.com/design/RLMxhgbXlbPRiYUUCVufeK/Homepage-Redesign---Oct-25?node-id=1218-6776) |
| Mobile Homepage | `1284:3222` | [Link](https://www.figma.com/design/RLMxhgbXlbPRiYUUCVufeK/Homepage-Redesign---Oct-25?node-id=1284-3222) |

---

## Homepage Token Mapping (Homepage Redesign → SMPLX Design System)

The Homepage Redesign Figma file uses a different naming convention than the SMPLX Design System. This mapping table shows correspondences. **When building, use SMPLX token names as the canonical reference; homepage names are for cross-referencing the Figma source.**

### Typography Mapping

| Homepage Token | Size/Weight/LH | SMPLX Equivalent | Notes |
|---|---|---|---|
| `Header/H1-TC` | 32/600/44, ls:-2% | `Heading/32pt/Semi Bold` | Exact match on size/weight. SMPLX: ls:-1px, LH:38px. **Homepage LH is 44px** |
| `Header/H2-TC-SB` | 28/600/36, ls:-2% | `Heading/28pt/Semi Bold` | SMPLX: LH:34px, ls:-1px. **Homepage LH is 36px** |
| `Header/H2-TC-M` | 28/500/100, ls:-2% | `Heading/28pt/Medium` | SMPLX: LH:34px. **Homepage uses auto/100** |
| `Header/H3-TC` | 20/700/28 | `Heading/20pt/Bold` | SMPLX: LH:24px. **Homepage LH is 28px** |
| `Header/H3-TC-M` | 20/500/28 | `Heading/20pt/Medium` | SMPLX: LH:24px. **Homepage LH is 28px** |
| `Header/H3-TC-SB` | 20/600/26, ls:-2% | `Heading/20pt/Semi Bold` | Mobile section headers. SMPLX: LH:24px. **Homepage LH is 26px** |
| `Subheader/SH2-TC-SB` | 16/600/20 | `Heading/16pt/Semi Bold` | SMPLX: LH:22px. **Homepage LH is 20px** |
| `Subheader/SH3-AC` | 14/900/20, ls:-1, UC | — (no SMPLX match) | **NEW**: Black 900 weight, uppercase. Footer section headers |
| `Label/L1-AC` | 16/600/auto, UC | `Tags & Labels/16pt/Bold` | Weight differs: Homepage 600 vs SMPLX 700 |
| `Label/L2-AC-B` | 14/700/14, UC | `Tags & Labels/14pt/Bold` | Exact match. SMPLX: LH:18px. **Homepage LH is 14px** |
| `Label/L2-AC-SB` | 14/600/20, UC | `Tags & Labels/14pt/Semi Bold` | Exact match. SMPLX: LH:18px. **Homepage LH is 20px** |
| `Label/L3-AC-B` | 12/700/14, UC | `Tags & Labels/12pt/Bold` | Match |
| `Label/L3-AC-SB` | 12/600/16, UC | `Tags & Labels/12pt/Semi Bold` | SMPLX: LH:14px. **Homepage LH is 16px** |
| `Label/L3-TC-M` | 12/500/16 | `Text/12pt/Medium` | SMPLX: LH:20px. **Homepage LH is 16px** |
| `Label/L4` | 12/400/16, ls:-1, UC | — (no SMPLX match) | **NEW**: Regular weight label, footer legal links |
| `Label/L4-AC-M` | 10/500/12, ls:-1, UC | — (no SMPLX match) | **NEW**: AD label |
| `Label/L4-AC-SB` | 10/600/16, ls:-4%, UC | — (no SMPLX match) | **NEW**: Mobile category tags |
| `Body/Body 1` | 20/400/28 | — (no SMPLX match) | **NEW**: Event descriptions, drop titles |
| `Body/Body 3` | 14/400/20 | `Text/14pt/Regular` | SMPLX: LH:22px. **Homepage LH is 20px** |
| `Body/Body 4` | 12/400/16 | — (no SMPLX match) | **NEW**: Cover story descriptions, email placeholder |

### Color Mapping

| Homepage Token | Value | SMPLX Equivalent | Notes |
|---|---|---|---|
| `--primary/default/black` | `#000000` | `Text/Primary` / `Background/B1 Inverse` | Match |
| `--primary/default/white` | `#FFFFFF` | `Text/Primary Inverse` / `Background/B1` | Match |
| `--secondary/grey-1` | `#666666` | — (no match) | **NEW**: Between Text/Secondary (#40444a) and Text/Tertiary (#8f959d) |
| `--secondary/grey-2` | `#999999` | `Text/Tertiary` (#8f959d) | **Different value**: Homepage #999 vs SMPLX #8f959d |
| `--secondary/grey-3` | `#E6E6E6` | `Border/Primary` (#e1e3e5) | **Different value**: Homepage #E6E6E6 vs SMPLX #e1e3e5 |
| `--error` | `red` | `Icons/Error` (#db1c1c) | **Different value**: Homepage pure red vs SMPLX #db1c1c |
| `--brand/neutrals/09` | `#818181` | — (no match) | **NEW**: Footer legal text |
| `--brand/neutrals/08` | `#8F8F8F` | — (no match) | **NEW**: Placeholder text |
| `--brand/neutrals/03` | `#D5D5D5` | — (no match) | **NEW**: Field borders |
| `--brand/neutrals/02` | `#E3E3E3` | — (no match) | **NEW**: Footer input placeholder text |
| `--logo/border` | `#131313` | `Brand/Stroke/Black` (#202225) | **Different value** |

---

## Homepage-Specific Tokens (Not in SMPLX Design System)

### Additional Colors

| Token | Value | Usage |
|---|---|---|
| `--secondary/grey-1` | `#666666` | Body text, article dek, event descriptions |
| `--fill/general/solid/fill-inverse-1` | `#0A0A0A` | Near-black fill (event location bar) |
| `--color/neutrals-2/39` | `#0B0B0D` | Near-black text (product card headline) |
| `#968E8E` | `#968E8E` | Placeholder image backgrounds |
| `#F2F2F2` | `#F2F2F2` | Event date/location tab bar background |
| `#8B8B8B` | `#8B8B8B` | Footer legal text, copyright |

### Additional Overlay / Transparency Values

| Value | Usage |
|---|---|
| `rgba(0,0,0,0.1)` | Navigation bar shadow |
| `rgba(255,255,255,0.1)` | Footer email input background |
| `rgba(255,255,255,0.5)` | Footer email input border |
| `rgba(255,255,255,0.8)` | Date badge frosted glass overlay |
| `rgba(255,255,255,0.95)` | Mobile sub-nav background |

### Effects

| Name | Value | Usage |
|---|---|---|
| `Shadow Level - Down` | `0 4px 16.1px 0 rgba(0,0,0,0.1)` | Navigation bar drop shadow |
| `Blurs/Blur 200` | `backdrop-filter: blur(15px)` | Mobile frosted glass (status bar, date badge) |
| Event gradient | `linear-gradient(179deg, #000 5%, transparent 15%), linear-gradient(179deg, transparent 76%, #000 99%)` | Top+bottom fade on event hero image |

### Homepage Layout (Desktop)

| Property | Value | Notes |
|---|---|---|
| Frame width | `1440px` | Matches SMPLX grid |
| Content padding | `32px` each side | Per canonical SMPLX grid (32px FLEX margin) |
| Content area | `1376px` | SMPLX safe area |
| Section gap | `88px` | Between major sections |
| Footer padding | `80px` top/bottom, `32px` horizontal | Per SMPLX grid margin |

### Homepage Layout (Mobile)

| Property | Value | Notes |
|---|---|---|
| Frame width | `390px` | Matches SMPLX grid |
| Content padding | `16px` each side | Matches SMPLX mobile margin |
| Header height | `52px` | SMPLX: 48px. **Homepage is 52px** |
| Sub-nav height | `40px` | |
| Section gap | `28px` | Between major sections |
| Button height (standard) | `36px` | SMPLX: 36px (Medium). Match |
| Button height (compact) | `28px` | Smaller than SMPLX Small (32px) |
| Footer padding | `24px` horizontal, `24px` top, `44px` bottom | |

---

## Homepage Component Patterns

### Navigation (Desktop — Tabbed)
- **Structure:** Top row of 3 tabs (Explore / Shop / Events) + center COMPLEX wordmark + search/wishlist/account/cart icons
- **Tab dimensions:** `124px × 60px`
- **Active tab:** Black bg, white text (`Label/L1-AC`)
- **Inactive tab:** White bg, black text, right border `#E6E6E6`
- **Sub-nav:** Category links in horizontal row, `34px` gap
  - Active: Inter Extra Bold (800), black
  - Inactive: Inter Semi Bold (600), `#666`
- **Shadow:** `0 4px 16.1px rgba(0,0,0,0.1)`
- **Total height:** `116px` (60px tabs + 56px sub-nav)

### Navigation (Mobile — Simplified)
- **Header:** `52px` height, white bg
- **Left:** COMPLEX wordmark (79.37 × 20px)
- **Right:** Search, Wishlist, Bag (20×20), Hamburger — 24px icons, `12px` padding each
- **Sub-nav:** 2 tabs (Explore / Shop), each `flex-1`, `40px` tall
  - Font: Inter Bold 14px, uppercase
  - Active: underlined
  - Border bottom: `1px solid #E6E6E6`

### Hero Module (Desktop)
- **Layout:** 2-column within `1017px` left block: featured article (`327px`) + featured drop (`328px`)
- **Right sidebar:** Additional drop card
- **Article content:** Category tag (`Label/L2-AC-SB`) + Headline (`Header/H1-TC`, 32px) + Dek (14px Regular, `#666`)
- **CTA buttons:** "READ" and "SHOP" (Outline style)

### Hero Module (Mobile)
- **Full-width 1:1 image slot**
- **Below:** Category tag (10px SemiBold, `#999`) + Headline (20px SemiBold) + Dek (12px, `#666`, 3-line truncate)
- **Small article card:** 169px image + text, `8px` gap

### Section Header
- **Desktop:** `Header/H2-TC-SB` (28px SemiBold), left-aligned, optional CTA/arrows on right
- **Mobile:** `Header/H3-TC-SB` (20px SemiBold, ls:-0.4px), `16px` horizontal padding, `24px` bottom padding

### Article Card — Horizontal (Latest Stories)
- **Desktop:** Image (left) + text (right, `443px`), `16px` gap
  - Category: `Label/L2-AC-SB` (14px SemiBold, `#999`, uppercase)
  - Headline: `Header/H3-TC-M` (20px Medium, black)
  - Gap between tag/headline: `12px`
  - Divider: `1px #E6E6E6`
- **Mobile:** Image `169×95px` + text `181px`, `8px` gap
  - Category: `Label/L4-AC-SB` (10px SemiBold, `#999`, uppercase)
  - Headline: `Label/L3-TC-M` (12px Medium, black, 2-3 line clamp)

### Article Card — Vertical (Highlights)
- **Desktop only:** 3-column, `441px` each, `16px` gap
- **Image ratio:** 4:5 (1080×1350)
- **Gap image→text:** `32px`
- **Text:** Same tag+headline pattern as horizontal cards

### Drop/Event Card (Shop Latest Drops)
- **Desktop:** 2-up cards with 16:9 product images
- **Mobile:** 2-up at `191px` wide, `239px` image height
- **Status badges:** "LIVE" (red bg) or "UPCOMING" (black bg), `8px` text, uppercase
- **Date badge:** Frosted glass overlay, month+day
- **CTA:** "SHOP NOW" or "NOTIFY ME" (Outline button)

### Cover Story Module
- **Desktop:** Black bg, `40px` padding, `523px` height
  - Left (`557px`): Title (28px Medium, white) + Desc (12px, white) + 2 CTA buttons
  - Right: 9:16 image
- **Mobile:** Section header on white, full-width hero image (~437px), content on black
  - Headline: 16px SemiBold, white
  - Body: 12px Regular, white
  - 2 buttons side by side, `28px` tall, `#999` border

### Event Module (Upcoming Event)
- **Desktop:** 2-column — image left, details right
  - Date/Location tabs: grey (`#999`) + black, `51px` tall
  - Content: Title (28px Medium) + description (20px Regular, `#666`) + CTA
- **Mobile:** Full-width image with gradient overlay, bordered detail row below

### Trending Videos
- **Desktop:** Horizontal scroll, `213.75 × 353.16px` cards, `5.24px` radius, `15.63px` gap
- **Mobile:** Horizontal scroll, `163 × 270px` cards, `8px` gap

### "Read More On" Channel Avatars
- **Desktop:** `118.22px` circles, black bg, `0.59px` border `#131313`, `17.73px` gap
- **Mobile:** `75px` circles, `5.26px` gap

### Shop By Interest Pills
- **Desktop:** `308 × 59px`, black bg, white text (16px SemiBold), 3×2 grid, `4px` gap
- **Mobile:** flex-wrap, `28px` tall, black bg, `14px` Bold white text, `4px` gap

### Footer
- **Background:** Black
- **Desktop padding:** `40px` horizontal, `80px` vertical
- **Mobile padding:** `24px` horizontal, `24px` top, `44px` bottom
- **Social icons:** `20px`, `32px` gap
- **Newsletter:** Email input (`48px`, translucent bg) + "GET NOTIFIED" button (`132px × 48px`, white bg)
- **Section headers:** Inter Black 16px (mobile) / `Subheader/SH3-AC` 14px Black 900 (desktop)
- **Link text:** Inter Black 16px, white, line-height 1.7
- **Legal links:** Inter Regular 12px, `#8B8B8B`

### App Download Banner (Mobile Only)
- **Height:** `148px`, background image
- **Headline:** "Stay ahead on [rotating word]" — Inter Medium 20px + Inter Medium Italic
- **Subtext:** 14px Regular, white
- **App Store badge:** `125 × 37px`

### Button Variants (Homepage-Specific)

| Variant | Height | Border | Text | Usage |
|---|---|---|---|---|
| Outline (Desktop) | `42px` | `1px #E6E6E6`, `4px` radius | `Label/L2-AC-B` (14px Bold, uppercase) | READ, SHOP, SEE ALL, LOAD MORE, VIEW EVENT |
| Outline (Mobile Standard) | `36px` | `1px #E6E6E6`, `4px` radius | `Label/L3-AC-B` (12px Bold, uppercase) | SEE ALL, VIEW EVENT, LOAD MORE |
| Outline (Mobile Compact) | `28px` | `1px #E6E6E6`, `4px` radius | `Label/L3-AC-B` (12px Bold, uppercase) | READ, SHOP, SHOP NOW, NOTIFY ME |
| Dark Outline | `28px` | `1px #999`, `4px` radius | 12px Bold, white, uppercase | Cover Story CTAs on black bg |
| Arrow Nav | `32px × 32px` | `1px #E6E6E6`, `4px` radius | Chevron icon (20px) | Carousel arrows |

### Ad Placements
- **Desktop inline:** `902px × 116px`, centered, "AD" label (10px Medium, `#999`), top/bottom dividers
- **Mobile:** `300×250` standard IAB, or full-width × ~400px
- **Dividers:** `1px #E6E6E6`
