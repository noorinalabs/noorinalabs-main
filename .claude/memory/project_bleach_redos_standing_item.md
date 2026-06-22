---
name: project_bleach_redos_standing_item
description: "bleach GHSA-g75f-g53v-794x (linkify parse_email ReDoS) — no upstream fix and never will be (bleach EOL 2026-06-05); pip-audit --ignore-vuln stays in place per-repo; revisit each wave (main#703); close only when kaggle is dropped."
metadata:
  node_type: memory
  type: project
---

`bleach` is a transitive dep (via `kaggle`) carrying **GHSA-g75f-g53v-794x** — a ReDoS in `linkify()` when `parse_email=True` (~30 KB crafted input → multi-second CPU per call). Tracked by the standing revisit issue **main#703** (`security` + `tech-debt`, scheduled in `phase-6.md` for W3 but verified early each wave). The advisory is **non-applicable to our code** — we never call `bleach.linkify(parse_email=True)` — but `pip-audit --strict` flags it on any gated repo, so a narrowly-scoped `--ignore-vuln GHSA-g75f-g53v-794x` keeps the gate honest.

**Where the ignore / floor lives (child repos — edits belong to those repos' own personas, [[feedback_child_repo_implementer_rule]]):**
- `noorinalabs-isnad-ingest-platform` — `ci.yml` `security-audit`: `pip-audit --strict --desc --ignore-vuln GHSA-g75f-g53v-794x`. bleach pinned 6.4.0. The ignore is what unblocks the gate.
- `noorinalabs-data-acquisition` — `pyproject.toml` floors `bleach>=6.4.0` (clears the two FIXED advisories GHSA-gj48-438w-jh9v + GHSA-8rfp-98v4-mmr6). Runs **no** pip-audit gate, so **no** `--ignore-vuln` needed there.

**The two non-ReDoS bleach advisories ARE fixed** by `bleach>=6.4.0` and are NOT ignored — only the ReDoS one is.

## Revisit log
- **P6W2 (2026-06-21, Nino Kavtaradze, main#703):** Re-verified. (1) **No upstream fix** — GHSA-g75f-g53v-794x still lists `Patched versions: none`; latest bleach is **6.4.0** (2026-06-05) and the project is now **formally deprecated/EOL** ("Bleach is no longer maintained. There will be no future releases including for security issues"). So an upstream fix will **never** arrive — this is now a permanent ignore, not a wait-for-patch. (2) **Still needed** — bleach is pulled transitively by `kaggle`; not directly used. (3) **Ignore confirmed correct** — narrowly scoped to the single advisory, on the latest available bleach. No child-repo config change required this wave. **Remediation path is now singular: drop/replace `kaggle`** (the only way to remove bleach) — no kaggle-drop issue exists yet; candidate to file. Issue stays **OPEN** (close criteria — fix lands OR kaggle dropped — unmet; advisory-DB-drift caveat: [[feedback_pip_audit_strict_advisory_db_drift]]).

**Close main#703 ONLY when:** bleach ships a fix for GHSA-g75f-g53v-794x (impossible now — EOL) **OR** `kaggle` is dropped/replaced so bleach is no longer pulled (the only real remediation). Until then, surface via `/wave-scope` every wave.
