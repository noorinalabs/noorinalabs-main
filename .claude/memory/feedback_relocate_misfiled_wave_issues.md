---
name: feedback_relocate_misfiled_wave_issues
description: "Mis-filed wave issues (code lands in a different repo than filed) MUST be relocated at kickoff — close in home repo, recreate in actual repo. Every wave."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 090bf6d5-0d19-47c9-9b85-67bfff1c5396
---

Owner directive (2026-06-12, P4W3 kickoff): when wave-kickoff pre-flight 0.3 finds an issue whose code actually lands in a **different repo** than the one it's filed in, you must **relocate** it — not just note the discrepancy. Close it in its home repo and re-create it in the repo that actually changes. Owner: "I want this done every time when we reach this part of the wave process."

**Why:** the issue's home repo drives the wave branch / PR target / child-repo-implementer assignment and the auto-kickoff-comment hook (reads `wave_{M}_scope.tier_*` keyed by repo `id`). A filed-in-main issue whose code is in isnad-graph would target the wrong branch and pull the wrong roster. Relocating fixes it at the source instead of carrying the mismatch through the whole wave.

**How to apply:** enforced in `/wave-kickoff` SKILL.md § 0.3a (skill-tier). Sequence, BEFORE slate-persist and BEFORE any wave-label apply:
1. Re-create in the actual repo(s) with a faithful body + `## Provenance` pointer. Split across repos if the work spans repos (one issue per repo — also serves smaller-PR / parallelize preference). Category label(s) only, NOT the wave label yet.
2. `gh project item-add 2`; replace the source entry in `wave_{M}_scope.tier_*` with the new ref(s) + slate, keyed to the actual repo.
3. Relocation comment on the source issue → `--remove-label p{N}-wave-{M}` → `gh issue close --reason "not planned"`.
4. Then apply the wave label to the NEW issues so the kickoff hook fires against the right repo+slate.

Precedent P4W3: main#138 → ig#970 (UI) + ingest#70 (HTTP endpoint); main#633 → ingest#71 (pip) + ig#971 (authlib+pip). Relates to [[feedback_child_repo_implementer_rule]] and the deploy#242 sibling-of miscue.
