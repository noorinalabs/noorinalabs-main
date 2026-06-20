---
name: feedback_lint_gate_cover_all_syntactic_forms
description: "A regex/line-scan code gate must cover every syntactic form of the thing it enforces, or the bare-import form evades it"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7e042acd-06d6-4813-a40c-4eac8f291ea2
---

A regex/line-scan gate that enforces a policy on a Python API must match EVERY syntactic form that reaches that API, not just the most common one. The dotted-attribute form and the direct-import form are distinct surfaces.

**Why:** the deploy#363 os-environ gate (machine enforcement of "Settings-mandatory in src/") matched only `\bos\.(?:environ|getenv)\b` — the dotted form. `from os import environ` / `from os import getenv` (then bare `environ[...]`/`getenv(...)`) silently evaded it. Nino caught this on PR #396 security review by testing the evasion. A gate that the policy *depends on* but that the policy's target can trivially route around is worse than no gate (false sense of enforcement).

**How to apply:** when writing or reviewing a line-scan/regex gate over a named API, enumerate the access forms before trusting it — for a Python module member that's at least: dotted (`mod.name`), direct import (`from mod import name`, incl. comma lists / parenthesized / `as`-aliases), and module aliasing (`import mod as m` → `m.name`). Match the cheap-to-detect ones (dotted + direct-import via an import-line + whole-word name check); explicitly DOCUMENT the form you choose not to chase (module aliasing needs import-graph analysis, not a line scan — acceptable if rare + conspicuous in review). Security reviewers: actually test the evasion, don't just read the regex.

Surfaced on deploy#363 PR #396 (Nino Kavtaradze, 2026-06-02). Related: [[feedback_test_mock_masks_prod_failure]] (a gate that can be bypassed isn't enforcement), [[feedback_enforcement_hierarchy]] (hooks/gates decay when they don't actually bind).
