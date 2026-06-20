---
name: project_ds_component_utilities_noop
description: ig FE — DS component Tailwind utility classes (referenced only in DS dist JS) emit zero CSS; Dialog modal rendered unconstrained until @source inline force-gen
metadata: 
  node_type: memory
  type: project
  originSessionId: 5cda3514-df05-49e1-8a83-a950a28f40db
---

Sibling of [[project_ds_theme_color_utilities_noop]], for COMPONENT (not color) utilities.

The published `@noorinalabs/design-system` ships `dist/styles.css` = **token-only** (`:root{--color-*}`, ~25KB) and its components as **compiled React in `dist/index.js`**. It does NOT ship the Tailwind *utility* classes its components reference — those class names live only inside the minified dist JS. isnad-graph's Tailwind v4 build does not scan `node_modules`, so any DS-component utility that ig's own source never also uses produces **zero CSS rules**.

Common utilities survive (`bg-card`, `p-4`, `rounded-md`, `border`, … are used directly in ig src so they generate). The break shows up on component-unique utilities. Concrete bug (ig#1027, P5W3): the DS `Dialog`/`DialogContent`/`DialogOverlay` positioning+sizing classes — `fixed`, `start-1/2`, `top-1/2`, `-translate-x-1/2`, `-translate-y-1/2`, `max-w-lg`, overlay `inset-0`/`bg-black/80` — appear nowhere in ig src → modal had no fixed positioning, no centering transform, no max-width → blew out browser width.

Fix shipped (PR #1055, `frontend/src/styles/theme.css`): force-generate the full DS Dialog class contract via Tailwind v4 `@source inline("…")` — the component-utility analogue of the existing `@theme inline` color-token bridge (ig#1000). +1.2KB CSS, fixes every dialog app-wide (session modal, SearchPage filters, future dialogs). Do NOT instead `@source` the whole DS dist: scanning minified JS bloats CSS ~26% with false-positive candidates and is unreliable (extractor picked up `max-w-lg` from comment prose but skipped `start-1/2`/translates).

Real durable fix is DS-side: ship a compiled utilities CSS layer so consumers don't hand-mirror class lists (follow-up candidate). Until then keep the `@source inline` list in theme.css in sync if the DS Dialog class set changes.

Note: the `e2e` CI job in isnad-graph is disabled pending #812 (existing specs mock old `/api/v1/auth/me`; app moved to `/api/v1/sessions`/`/users/me`). New e2e specs run locally only, not as a live gate.
