# sellm brand

Canonical colours from the live shell (`shell-extra.css`):

| Token | Hex | Use |
| --- | --- | --- |
| `purple-1` | `#667eea` | Gradient start, theme-color |
| `purple-2` | `#764ba2` | Gradient end |
| `ink` | `#0f172a` | Dark text / dark wordmark |
| `panel` | `#ffffff` | Light surfaces |
| `muted` | `#64748b` | Secondary text |

## Assets

| File | Role |
| --- | --- |
| `logo-mark.svg` | Primary app mark (gradient tile + geometric S) |
| `logo-mark-mono.svg` | Monochrome mark (single-colour silhouette) |
| `logo-wordmark-dark.svg` | “sellm” for light backgrounds |
| `logo-wordmark-light.svg` | “sellm” for dark / gradient backgrounds |
| `logo-horizontal-dark.svg` | Mark + wordmark for light UI |
| `logo-horizontal-light.svg` | Mark + wordmark for dark / gradient UI |
| `icon-master.svg` | 1024 master used to derive PWA icons |

No prior logo existed in the repo. This kit is derived from the existing product name and purple gradient already used in the UI — not unrelated placeholder branding.

## Usage

- Prefer SVG in the web UI.
- Derive PNG/ICO favicons and PWA icons from `icon-master.svg` via `scripts/generate_pwa_icons.py`.
- Keep essential mark content inside the maskable safe zone (~80%) for adaptive icons.
