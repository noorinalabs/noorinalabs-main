---
name: project_ds_tokens_need_data_theme_attr
description: "DS dist color tokens only resolve at runtime when <html> has data-theme set; @theme{} block is browser-ignored"
metadata: 
  node_type: memory
  type: project
  originSessionId: 090bf6d5-0d19-47c9-9b85-67bfff1c5396
---

The published `@noorinalabs/design-system` dist (`dist/styles.css`, ≤0.0.4-wave10.0) defines every base color token in TWO places: a Tailwind v4 `@theme {}` block (a browser **ignores** this as an unknown at-rule when the dist is imported as plain CSS — Astro does NOT lower it to `:root`), AND browser-honored `[data-theme=light]` / `[data-theme=dark]` selector blocks (note: **unquoted** attribute form in the minified dist — grep `[data-theme=light]`, not the quoted form). Each `[data-theme=…]` block carries the full token set (14 LP tokens: primary/background/foreground/card/border/muted/etc).

Consequence: if nothing sets `data-theme` on `<html>`, only the ignored `@theme` block defines the tokens → every `var(--color-*)` resolves EMPTY → page renders unstyled (tell: `var(--color-border)` collapses, borders disappear). This was the lp#128 regression — it silently affected the whole P4W3 landing cluster (#125 theme migration, #123 team page) because no `data-theme` was set.

Fix (LP-side, lp#129): BaseLayout.astro SSRs `data-theme="light"` on `<html>` (no-JS default) + a pre-paint `is:inline` `<script>` (first in `<head>`, bare synchronous) that upgrades to a stored `theme` choice or OS `prefers-color-scheme` before first paint. Durable fix is DS-side — emit tokens to `:root` instead of `@theme` — tracked in **ds#104**. Toggle UI/persistence is lp#116's scope (the script's localStorage read is forward-compat plumbing).

**Verification lesson:** confirming "token text is present in the built CSS" is INSUFFICIENT — I did exactly that in #125 (`grep '--color-primary: oklch'`) and it passed because the text exists inside the ignored `@theme{}`. Must confirm the enclosing selector is browser-honored (`:root` or `[data-theme=…]`) AND that `<html>` actually carries the matching `data-theme`. A real browser/staging eyeball would have caught it immediately; the sandbox has no browser extension, so use the CSS-aware enclosing-selector check. See [[feedback_test_mock_masks_prod_failure]] (build-text presence masking runtime failure).
