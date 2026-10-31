# PULSE frontend design system: "Clinical Aurora"

Light theme with dark frames: a night-navy sidebar and heroes, bright clinical cards, electric-blue to sky accents,
an ECG-line motif and huge tabular numbers. Tokens live in `src/index.css` (`@theme`); components use the semantic
names only (`bg-surface`, `text-ink-muted`, `border-line`...), never raw hex.

## Colour semantics (non-negotiable)

- **Red = alarm only** (`emergency`, `alarm-1/2/3`, `level-severe`, `danger`).
- **Violet dashed = simulated** (`sim`), **indigo dashed = ML estimate** (`ml`), **teal = wearable** (`wear`).
- Decoration (glows, blobs, gradients, chips) never uses an alert, sim, ML or wearable colour: use `brand`, `glow`,
  `night`. `glow` is decorative only and never carries a meaning.
- Colour is never the only signal: every level, origin or state also has a text label (and usually an icon).

## Tokens

| Token | Value | Use |
|---|---|---|
| `canvas` | #f3f6fb | page background (+ a fixed aurora mesh on `body::before`) |
| `surface` / `surface-muted` | #fff / #eef2f6 | cards / wells, chips |
| `line` / `line-strong` | #d9e0e8 / #9aa7b5 | borders |
| `ink` / `ink-muted` / `ink-subtle` | #14202b / #4a5866 / #5f6b78 | text (15.3 / 6.7 / 5.0 :1 on canvas) |
| `brand` / `brand-hover` / `brand-soft` | #1d4ed8 / #1e40af / #e0eaff | actions, links, chips |
| `focus` | #1f7ae0 | focus ring (3.9:1 on canvas, ≥ 3:1) |
| `night` / `night-2` | #050b1a / #0a1630 | sidebar, heroes, night cards |
| `glow` | #38bdf8 | decorative accent on night |
| `alarm-1/2/3` | #5c0a0a / #8e1212 / #b71c1c | full-screen alarm (white text 14.0 / 9.4 / 6.6 :1) |
| `navy`, `navy-soft` | unchanged | legacy, prefer `night` |
| levels, `sim`, `wear`, `ml`, `success`, `warning`, `danger`, `chart-*` | unchanged | see `index.css` |
| shadows | `shadow-card`, `shadow-lift`, `shadow-glow-brand`, `shadow-glow-alarm` | |
| easings | `ease-(--ease-out-expo)`, `ease-(--ease-spring)` | |

Contrast pairs checked: white on brand 6.7, brand on brand-soft 5.6, sim on sim-soft 7.7, white on emergency 5.6,
white on night 19.6. Body text ≥ 4.5:1, large text and focus/graphics ≥ 3:1.

Inside a `card-night` scope (night `Card`, night `StatTile`) the `ink*`, `line` and `surface-muted` tokens flip to
white tints, so `text-ink`, `text-ink-muted` and `border-line` stay readable on the dark background.

## Motion (CSS only, no JS animation)

`animate-fade-up` (420 ms), `animate-page-in` (route change, 320 ms), `animate-fade-in`, `animate-scale-in` (240 ms),
`animate-drawer-in`, `animate-shimmer` (skeleton), `animate-pulse-ring` (2 s), `animate-heartbeat` (1.6 s),
`animate-ecg` (2.4 s, needs `pathLength="100"` + `stroke-dasharray="100"`), `animate-float` (18 s aurora blob),
`animate-breathe` (2.4 s alarm layer, never a flash), `animate-reveal` (blur + fade); `stagger` on a parent fades its
children in, 60 ms apart.

Rules: the base style is the visible resting state; hidden states exist only in `from` keyframes with a `backwards`
fill, so nothing stays hidden when motion is off and no transform is left on an ancestor (a transform, filter or
`backdrop-filter` makes an element the containing block of `position: fixed` children; never put a fixed element
inside `glass`, a transformed or an animated wrapper: portal it to `document.body`). Only transform, opacity, filter
and stroke-dashoffset are animated. No count-up on blood-pressure values (it would show values nobody measured);
Recharts animation stays off. `prefers-reduced-motion: reduce` turns off every animation, transition and smooth
scroll on all elements and pseudo-elements.

## Utilities

`glass` / `glass-night` (blur panels, solid fallback without backdrop-filter), `field` (inputs, selects, textareas:
44 px, rounded, brand focus outline, `aria-invalid` turns the border red), `text-gradient`, `bg-alarm` (radial red),
`btn-shine` (hover sweep, hover-capable devices only), `tnum` (tabular numbers), `card-night` (token flip).
`.alarm` scopes a white focus ring. `html:has(.alarm-bar)` adds the alarm bar to `scroll-padding-top`;
`--header-h` is 4rem (0 at `lg`). In `forced-colors` mode `.card`, `.badge` and `[role=alertdialog]` get borders.

## z-index scale

| Layer | z |
|---|---|
| alarm bar (sticky) | 10 |
| mobile header | 20 |
| sidebar | 30 |
| drawer | 40 |
| skip link | 50 |
| alarm overlay | 60 |

## Primitives (`src/components/ui`)

- `Card({ as = "section", variant = "plain" | "glass" | "elevated" | "night", className })`,
  `CardHeader({ title, subtitle, action, id, icon })`, `CardBody({ className })`,
  `PageHeader({ eyebrow, title, subtitle, action })`.
- `Button` / `ButtonLink({ variant = "primary" | "secondary" | "ghost" | "emergency" | "inverse" | "outline-inverse" })`:
  `inverse` and `outline-inverse` are for red/dark backgrounds. Always 44 px high.
- `Badge({ tone, icon, dot })` with tones `neutral brand success warning danger sim wear ml notice trend severe
  emergency`; `OriginBadge`, `ValidationBadge`, `LevelBadge`, `StatusBadge`.
- `Icon({ name, size, className, strokeWidth, title })`: 24×24 stroke icons, `aria-hidden` unless `title`.
- `Logo({ inverse, size, animated })`, `LogoMark({ size, animated, className })`.
- `Loading({ label })` (role=status skeleton + visible label), `ErrorState({ what, error, onRetry })` (role=alert),
  `EmptyState({ icon, title, children, action })`, `Section({ state, what, children })`.
- `Tabs({ items: [[key, label, count?]], value, onChange, label, variant = "underline" | "segmented", idPrefix })`:
  tab ids `${idPrefix}-tab-${key}`, panel `<div role="tabpanel" id={`${idPrefix}-panel`}
  aria-labelledby={`${idPrefix}-tab-${value}`}>`; roving tabindex, arrows / Home / End.
- `StatTile({ label, value, unit, hint, icon, tone = "plain" | "night" | "sim", className })`.
- `useDialog(ref, open, onEscape)` (`src/lib/useDialog.js`): for portalled modals; inerts the rest of `<body>`,
  locks scroll, focuses `[data-autofocus]` (or the dialog, which then needs `tabIndex={-1}`), Escape calls
  `onEscape` on the topmost dialog only, and restores everything (focus back to the opener, else `#main`).

## Accessibility rules

Colour never alone; alerts use `role="alert"`, loading uses `role="status"`; every target ≥ 44 px (`min-h-11`);
visible focus everywhere (white inside `.alarm`); the skip link and `<main id="main" tabIndex={-1}>` stay; modals are
portalled, `aria-modal`, inert the page and return focus; French UI texts that tests or QA rely on are kept.

## Dark mode (later)

Not shipped. Path: override the colour tokens on `:root[data-theme="dark"]` (and under
`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`), declare
`@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));` for the few places that need more than a
token swap, and switch `color-scheme`. Components already use semantic tokens only, so most of it is the token table.
