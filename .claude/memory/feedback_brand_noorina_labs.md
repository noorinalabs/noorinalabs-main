---
name: feedback_brand_noorina_labs
description: Display brand is "Noorina Labs" (two words); camel-case "NoorinALabs" is WRONG; lowercase slug stays.
metadata:
  type: feedback
---

The display/product brand is **Noorina Labs** — two words, capital N, capital L,
space between. The camel-cased one-word form with a capital A mid-word
(N-o-o-r-i-n-A-L-a-b-s) is **WRONG** for ALL user-facing text (headings, prose,
titles, meta, docs, error messages). Owner flagged it 2026-06-21; canonical rule
lives in `.claude/team/charter/brand.md`.

**Why:** the brand had silently drifted to the wrong camel-case form in 19
places across 16 files because `.cspell/project-words.txt` had *blessed* the
wrong spelling as a dictionary word — so the spell gate never caught it (main#792).

**How to apply:**
- Prose/headings/UI/docs → write `Noorina Labs`.
- The lowercase one-word slug `noorinalabs` is a CODE IDENTIFIER (GitHub org,
  repo names `noorinalabs-*`, npm scope `@noorinalabs/*`, registry, domain
  `noorinalabs.com`) — leave it exactly as-is; never rewrite it to "Noorina Labs".
- Enforcement is now machine-level: the wrong form is removed from the cspell
  dictionary, so CI Spellcheck FAILS on any reintroduction. `brand.md` is the one
  file allowed to contain the wrong form (it documents it as wrong) via a
  file-scoped `<!-- cspell:ignore NoorinALabs -->`.

Related: the office-docs pipeline `gen-office.sh` now pins a FIXED
`SOURCE_DATE_EPOCH` (not git commit time) so the #781 office-drift gate is
squash-merge-safe — see [[feedback_local_ci_parity_no_force]].
