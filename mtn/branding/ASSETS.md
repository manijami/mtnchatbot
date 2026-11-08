# MTN design assets — slots, formats and fallbacks

Official MTN design files live in **`mtn/branding/private/`**. That folder is gitignored: never
commit it, never push it, and share it out of band (secure share or secret store). The branding
image (`mtn/branding/Dockerfile`) copies them into the local image only. Every slot has a fallback,
so a fresh clone without `private/` still builds and runs.

How a slot is filled at build time, in order:

1. `private/<folder>/<name>.svg`, copied as is (preferred: vector, small, sharp at every size).
2. `private/<folder>/<name>.png`, wrapped in an SVG so the published URL stays the same.
3. The tracked fallback `assets/<folder>/<name>.svg`, if there is one.
4. Nothing. The UI then uses its built-in fallback, listed below.

Each slot is published at **`/assets/mtn/<folder>/<name>.svg`**.
`/assets/mtn/assets.json` lists the slots filled from `private/` (`{"official": ["avatars/smart-chat", …]}`),
so MTN layout code (Stage B onwards) can prefer an official icon and otherwise use its built-in one.
Rebuild after adding or changing a file: `docker compose build api`.

## Slots

### `logo/`: MTN logo

| File | Format and size | Where it appears | Fallback |
|---|---|---|---|
| `logo.svg` | SVG, or PNG at least 512 px wide, **transparent background**, black outline mark | Top bar (on yellow), sign-in page, light mode | `generated/logo.svg` (made from `logo/yello_logo.jpg`), then the tracked placeholder |
| `logo-on-dark.svg` | Same, for dark backgrounds (white or yellow mark) | Dark mode, dark sidebar | `logo.svg` |

Already present: `logo/yello_logo.jpg` (8000 px, mark on a yellow square) and `logo/white_logo.png`
(800 px, mark on a **white, non-transparent** background). Neither can sit directly on the yellow
top bar. Please supply `logo.svg` with a transparent background.

### Favicons and app icons: `generated/`

| File | Format | Where | Fallback |
|---|---|---|---|
| `logo.svg`, `favicon-16x16.png`, `favicon-32x32.png`, `apple-touch-icon-180x180.png`, `icon-192x192.png`, `maskable-icon.png` | PNG at the stated sizes; `logo.svg` | Browser tab, bookmarks, PWA install, in-app logo | Tracked placeholders in `assets/` |

These are generated from `logo/yello_logo.jpg` by the Phase 1 asset script.

### `avatars/`: assistant avatars

| File | Format and size | Where | Fallback |
|---|---|---|---|
| `smart-chat.svg` | SVG, or square PNG of 128 px or more; a circle reads best | Model menu, message author, chat list for MTN Smart Chat | `assets/avatars/smart-chat.svg`: yellow disc with a black chat-bubble glyph (original drawing) |
| `document-assistant.svg` | Same | Same, for MTN Document Assistant (including the Groq fallback) | `assets/avatars/document-assistant.svg`: yellow disc with a black document glyph |

`librechat.yaml` (`modelSpecs[].iconURL`) points at `/assets/mtn/avatars/<name>.svg`.

### `file-types/`: Office file cards (Stage C)

| File | Format and size | Where | Fallback |
|---|---|---|---|
| `docx.svg`, `pptx.svg`, `xlsx.svg`, `pdf.svg` | SVG, about 40×48 | Office file card, preview panel, My files | `assets/file-types/*.svg`: a generic page labelled DOCX, PPTX, XLSX or PDF (original drawing) |

Do not use Microsoft or Adobe product logos unless MTN supplies them with confirmed usage rights.

### `icons/`: UI icons (Stage B and C)

| File | Format | Where | Fallback |
|---|---|---|---|
| `chats`, `projects`, `assistants`, `files`, `search`, `new-chat`, `help` | SVG, 24×24, single colour using `currentColor`, outline style | Sidebar and top bar | Lucide outline icons (already in LibreChat) |
| `attach`, `mic`, `send` | Same | Composer | Lucide / upstream icons |
| `share`, `more`, `download`, `preview`, `expand`, `close` | Same | Chat header, file card, preview panel | Lucide |

Icons must use `currentColor` so they follow light mode, dark mode and focus states.

### `illustrations/`

| File | Format | Where | Fallback |
|---|---|---|---|
| `empty-state.svg` | SVG, about 240×160 | New-chat welcome area (Stage B, optional) | None (text only) |

### `fonts/`: MTN Brighter Sans

| File | Format | Where | Fallback |
|---|---|---|---|
| `MTNBrighterSans-*.otf` | OTF (WOFF2 preferred if MTN can supply it) | All text | Inter (the theme's font stack) |

Open item: MTN must confirm that the Newlyn Works licence covers web embedding.

### `brand/`: palette (design input, not copied into the image)

| File | Format | Used for | Fallback |
|---|---|---|---|
| `palette.json` (or a brand-guide PDF) | `{"yellow": "#FFCB05", "black": "#000000", …}` with the role of each colour | Updating `interface.theme` in `mtn/config/librechat.yaml`, then re-running `node mtn/scripts/theme-contrast.js .` | The current tested palette in `librechat.yaml` |

### `reference/`: design reference (never copied into the image)

| File | Use |
|---|---|
| `ui-reference.png` | The target mock-up that each stage's screenshots are compared against |
