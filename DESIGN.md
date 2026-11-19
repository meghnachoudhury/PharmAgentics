# Design

The web app (`frontend/figma-make`) is an analyst's tool: quiet, precise, consistent. The interface recedes so the evidence and the decision lead. Product context is in [PRODUCT.md](PRODUCT.md); tokens live in `frontend/figma-make/src/index.css`.

## Theme

Dark only. Restrained colour: neutrals carry the page, and the sage teal of the "Pa" mark appears only on the one primary action per view, the current selection and focus.

| Token | Value | Use |
| :- | :- | :- |
| `paper` | #0b0f0e | Page, input wells |
| `sheet` | #121816 | Panels and the sidebar (one flat, solid layer) |
| `rule` | #232c29 | The one border and divider colour |
| `ink` / `muted` | #e6ece9 / #94a39d | Body / secondary text |
| `navy` / `navyhover` | #3f6d66 / #487871 | Primary button fill (white text, 5.9:1 and 5.0:1) |
| `agent` / `agentdeep` | #8fc2b8 / #a9d3ca | Current selection, focus, links |
| `ok` | #8ab4f8 | Verified and approved, always with a word or a check mark |
| `amber`, `neg` | #fbbf24, #f87171 | Data-health warnings; rejection and Sensitive data |

Every text pair clears WCAG AA (4.5:1). Remeasure after any colour change.

## Type

- **IBM Plex Sans** (self-hosted, `public/fonts`) for the interface, labels and data. Numbers use `tabular-nums`.
- **Source Serif 4** for page titles (h1, h2) and brief prose (16px, line height 1.7, at most 68 characters a line).
- Small uppercase labels (classification) use 11px with 0.06em tracking.

## Components

Use the shared class constants in `App.tsx`, not one-off styles:

- `BTN` (primary, one per view), `BTN2` (secondary), `FIELD`, `LABEL`, `PANEL`.
- Panels: 12px radius, one 1px `rule` border, no shadow. Controls: 8px radius.
- Tabs: plain text with a 2px `agent` underline on the current tab. The analyst/leadership switch is a small neutral segmented control.
- Lists are rows divided by `rule` inside one panel, never grids of cards.
- Chips only for status (in review, approved, paused).
- Data classification (core-009) is a quiet uppercase text label, never a coloured pill; only Sensitive takes a colour.

## Surfaces and depth

- Frosted glass (`.glass`) only on things that float over the page: the sidebar while it hovers open, menus, the phone drawer, toasts.
- One faint sage glow at the top right of the page; nothing else glows.

## Layout

- Sidebar: a 64px icon rail that opens over the page on hover or focus; the pin keeps it open (248px). The "Pa" mark is the only logo, in the rail.
- Content (`.workspace-content`, max 52rem) is centred on the whole page, using `--rail` (the sidebar's width), and clears the sidebar when the screen is narrow.

## Avoid

Avatar circles with initials, coloured badge pills with icons, tinted and ringed selected states, a logo repeated in the page, hero headings on working screens, full-width buttons, and blur on solid panels.
