---
name: project_lp_ds_icon_consumption
description: "Landing-page (Astro) cannot import the design-system's React-only icons; geometry-mirror is interim, ds#103 tracks the framework-neutral export. Plus npm-auth recipe + stale publish-lore correction."
metadata: 
  node_type: memory
  type: project
  originSessionId: 090bf6d5-0d19-47c9-9b85-67bfff1c5396
---

**The design system ships icons ONLY as React components** (`@noorinalabs/design-system/icons` → `React.createElement` bundled in `dist/index.js`). The **landing page is pure Astro with no React renderer**, so it CANNOT `import` them. `noorinalabs-landing-page/src/components/Icon.astro` therefore reproduces the DS Qalam geometry by hand (graph→GraphExplorer, user→Narrators, search→Search, compare→Compare, book→Hadiths; 24×24, currentColor, 1.5px stroke). This is an **interim mirror** — the real "consume from DS" fix is **noorinalabs-design-system#103** (framework-neutral `iconPaths` export; refactor React icons to render from it). Once ds#103 ships, swap Icon.astro's hand-copied geometry for a direct import. Landed in lp#119 / PR#126 (P4W3). The icon geometry source-of-truth = the **published bundle**, not the DS wave-11 source (which can drift); extract via grep on `node_modules/@noorinalabs/design-system/dist/index.js`.

**Stale-lore correction:** the published `@noorinalabs/design-system@0.0.4-wave10.0` `styles.css` DOES ship `--color-brand-navy`/`--color-brand-gold`, the full semantic token set, AND both `prefers-color-scheme` + `[data-theme]` dark mode. The old global.css comment claiming "DS publish pipeline broken since v0.0.1, brand tokens may be absent, inline OKLCH fallbacks load-bearing" is WRONG for current versions. Kofi's lp#118 (PR#125) removed that comment + the whole LP-local navy/gold/neutral ladder, folding the LP onto DS semantic tokens.

**npm-auth recipe (LP/DS install):** `@noorinalabs/*` resolves from GitHub Packages (`https://npm.pkg.github.com`); `NODE_AUTH_TOKEN` is unset in the sandbox. Install with: write `//npm.pkg.github.com/:_authToken=$(gh auth token)` + `@noorinalabs:registry=...` to a temp file, then `NPM_CONFIG_USERCONFIG=/tmp/xxx npm install`. Do NOT commit the token.

**DS export bug (surfaced, filed in ds#103 notes):** published pkg `exports["./icons"]` → `./dist/icons/index.js` which does NOT exist (only `.d.ts` there; all JS is in `dist/index.js`). The `./icons` subpath import appears broken.

Related: [[project_data_pipeline_architecture]] is unrelated; this is design-system/landing-page cross-repo. CI format-check is scoped `src/**` only (repo-root files like RUNBOOK.md fail local `prettier --check .` but CI never checks them).
