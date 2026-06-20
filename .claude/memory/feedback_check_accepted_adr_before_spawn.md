---
name: feedback_check_accepted_adr_before_spawn
description: "Before spawning an implementer on an issue, check whether an accepted ADR/decision already settled or REJECTED the proposed change; ADR-conflicting issues are owner policy calls, not implementer work."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8d2a38da-f166-4000-b650-daeed2f7ba13
---

Before spawning an implementer on an issue, grep the relevant ADR set (`docs/adr/` in the target repo) and recent design decisions for the area the issue touches. An issue filed weeks ago may propose **exactly what a later accepted ADR deliberately rejected** — handing it to an implementer would silently re-litigate (or worse, supersede) an accepted decision without owner sign-off.

**Why:** P3W12 Tier 1, deploy#164 (per-VPS/per-role SSH key split) proposed the multi-keypair scheme that accepted **ADR 0003 (2026-05-18)** had evaluated and rejected in favor of one shared canonical pubkey. The issue predated the ADR. Spawning blindly would have implemented against an accepted ADR. Surfacing it turned out to matter twice over: (1) ADR 0003's *technical* objection (Hetzner 409 uniqueness) was already **moot** because ADR 0003 itself removed the `hcloud_ssh_key` resource — so the rejected approach was now feasible; (2) the issue's underlying security concern was real and the ADR had only traded it for convenience, not refuted it. That makes it a live **owner policy decision** (supersede the ADR vs. accept the tradeoff vs. close), never an implementer default.

**How to apply:** When prepping a spawn brief, after HEAD-verifying file existence ([[feedback_pre_spawn_verify_file_exists]]) and the issue premise ([[feedback_investigate_before_implement]]), also check: does an accepted ADR or recorded decision already cover this area? If the issue *conflicts* with one, STOP and put the decision to the owner with the ADR's rationale + whether its premises still hold (blockers can go stale). If the owner chooses to proceed, the deliverable includes a superseding ADR (`Supersedes: NNNN` + the old ADR's `Superseded by:` updated), not just code. Sibling to [[feedback_verify_diagnosis_before_delegating]]; same "verify before delegating" family, ADR axis.
