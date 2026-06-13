---
name: ConfidenceOS Industrial Framework
colors:
  surface: '#0c160a'
  surface-dim: '#0c160a'
  surface-bright: '#313c2e'
  surface-container-lowest: '#071106'
  surface-container-low: '#141e12'
  surface-container: '#182216'
  surface-container-high: '#222d20'
  surface-container-highest: '#2d382a'
  on-surface: '#dae6d2'
  on-surface-variant: '#b9ccb2'
  inverse-surface: '#dae6d2'
  inverse-on-surface: '#283326'
  outline: '#84967e'
  outline-variant: '#3b4b37'
  surface-tint: '#00e639'
  primary: '#ebffe2'
  on-primary: '#003907'
  primary-container: '#00ff41'
  on-primary-container: '#007117'
  inverse-primary: '#006e16'
  secondary: '#c5c6cc'
  on-secondary: '#2e3135'
  secondary-container: '#46494e'
  on-secondary-container: '#b6b8be'
  tertiary: '#fff8f4'
  on-tertiary: '#442b10'
  tertiary-container: '#ffd5ae'
  on-tertiary-container: '#7a5b3c'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#72ff70'
  primary-fixed-dim: '#00e639'
  on-primary-fixed: '#002203'
  on-primary-fixed-variant: '#00530e'
  secondary-fixed: '#e1e2e8'
  secondary-fixed-dim: '#c5c6cc'
  on-secondary-fixed: '#191c20'
  on-secondary-fixed-variant: '#44474b'
  tertiary-fixed: '#ffdcbd'
  tertiary-fixed-dim: '#e7bf99'
  on-tertiary-fixed: '#2c1701'
  on-tertiary-fixed-variant: '#5d4124'
  background: '#0c160a'
  on-background: '#dae6d2'
  surface-variant: '#2d382a'
  status-safe: '#00FF41'
  status-caution: '#FFD700'
  status-warning: '#FFA500'
  status-critical: '#FF0000'
  status-disabled: '#4A4A4A'
  surface-base: '#0A0B0D'
  surface-panel: '#141619'
  surface-elevated: '#1C1F23'
  border-subtle: '#2D3139'
  border-strong: '#414752'
  data-mono: '#A0AEC0'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-sm:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-tabular:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.02em
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.06em
  caption-mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
spacing:
  unit: 4px
  gutter: 16px
  margin-mobile: 12px
  margin-desktop: 24px
  panel-gap: 1px
---

## Brand & Style

The design system is engineered for high-stakes industrial environments where clarity is a safety requirement. It adopts a **"Control Room at 2 AM"** aesthetic—a high-density, low-fatigue style that prioritizes data legibility over decorative flair. The brand personality is **Forensic, Authoritative, and Grounded**, positioning itself as a reliable truth-layer for physical infrastructure.

The visual direction follows a **Modern Industrial / Brutalist** hybrid:
- **Minimalism & Precision:** Every pixel must serve a functional purpose. 
- **Rigid Structure:** A strict grid system inspired by hardware rack mounts and technical schematics.
- **High-Contrast Dark Mode:** Deep neutral backgrounds reduce screen glare in low-light environments while allowing semantic alerts to "pop" with extreme urgency.
- **Direct Interaction:** No hidden gestures or "mystery meat" navigation. All controls are explicit and tactile.

## Colors

The palette is strictly functional. Chromatic color is reserved exclusively for status indication and data significance.

- **Backgrounds:** Utilize a "Deep Charcoal" stack. The base layer is near-black to maximize contrast. Panel layers use subtle shifts in value rather than shadows to define hierarchy.
- **Semantic Logic (The Trust Tiers):**
    - **Green (#00FF41):** High Confidence / Nominal Operation.
    - **Amber (#FFD700):** Medium Confidence / Cautionary Drift.
    - **Orange (#FFA500):** Low Confidence / Warning.
    - **Red (#FF0000):** Critical / Physical Inconsistency / Immediate Danger.
- **Auditor Mode:** In specialized reporting views, the semantic palette desaturates to a grayscale/bordered style to ensure a non-biased, professional presentation of data.

## Typography

Typography focuses on **rapid scanning** and **numeric integrity**.

- **Primary Typeface:** **Inter** is used for all UI labels, headings, and prose. It provides excellent legibility at small sizes.
- **Data Typeface:** **JetBrains Mono** (or any high-quality monospace with tabular lining) is mandatory for sensor IDs, timestamps, and raw values. This prevents "jitter" when numbers update live.
- **Scale:** Keep sizes disciplined. Most dashboard data should sit between 12px and 14px. Display sizes are only used for global "Plant Health" scores.
- **Weights:** Avoid stylistic "thin" weights. Use Regular (400) for body, Medium (500) for data, and Semi-Bold/Bold (600/700) for headers.

## Layout & Spacing

This design system uses a **Rigid Grid** model. Layouts should feel like a solid block of physical machinery.

- **Grid:** A 12-column grid for desktop. For "Fleet View" (high-level), use a 3 or 4-column card distribution. For "Forensic Replay," use a "Focus + Sidepanel" layout (80/20 split).
- **The 1px Rule:** Instead of large gutters, panels are often separated by a single `1px` border or a `1px` gap of the background color. This maximizes information density for engineer-level views.
- **Density Tiers:**
    - **Operator:** Standard padding (16px) to reduce cognitive load during active monitoring.
    - **Engineer/Auditor:** Compressed padding (8px or 4px) for deep-dive analysis and multi-sensor correlation.

## Elevation & Depth

In a mission-critical dashboard, shadows create visual "mush" and are strictly forbidden. Depth is communicated through **Tonal Layering** and **Border Logic**:

- **Layer 0 (Base):** Black (#0A0B0D). The "void" on which the system sits.
- **Layer 1 (Panels):** Deep Slate (#141619). The primary surface for data cards and sensor grids.
- **Layer 2 (Interactive/Hover):** Slightly lighter slate (#1C1F23) with a `1px` solid border (#414752).
- **Overlays:** Modals and "Predictive Failure Cards" do not use shadows. Instead, they use a high-contrast border in the primary status color (e.g., a pulsing 2px Red border for critical root-cause analysis).

## Shapes

The shape language is **Sharp (0px)**. 

Curves are perceived as "soft" and consumer-oriented. To maintain an industrial, professional, and serious tone, all UI elements—including buttons, cards, input fields, and chips—must have 90-degree corners. 

*Exception:* Miniature trend indicators or circular status "LED" dots may be used only when representing physical hardware lights.

## Components

- **Industrial Sensor Cards:** Fixed-height containers with a 1px border. They must include: Sensor ID (Mono), Sparkline (Last 1h), Current Value, and Trust Tier Badge.
- **Status Indicators:** Rectangular "LED" badges. Use solid fills for active states and "outline + dim fill" for nominal/inactive states. 
- **Buttons:** 0px radius. Primary buttons use a solid border and uppercase label-caps. Critical actions (e.g., "SHUTDOWN") use a solid Red fill with white text.
- **Mass-Balance Sparklines:** Minimalist line charts without axes. The line color must dynamically change based on the value's relationship to the adaptive threshold envelope.
- **Citation Chips:** Used in AI-generated briefs. Small, monospaced blocks that, when clicked, highlight the specific sensor or time-slice in the forensic replay.
- **Timeline Scrubber:** A full-width component for Forensic Replay. Includes markers for "Incident Start," "Human Intervention," and "AI Detection."
- **Input Fields:** Bottom-border only or 1px full border. No background fill unless focused. Monospaced text for all numeric inputs.