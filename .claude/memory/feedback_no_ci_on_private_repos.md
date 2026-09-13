---
name: feedback_no_ci_on_private_repos
description: "Owner 2026-09-13: private repos must NOT run GitHub Actions/build steps — the owner keeps exhausting monthly Actions minutes. Public repos are free and unaffected. All 8 noorinalabs/* repos are PUBLIC; parametrization/* are PRIVATE except 2real-team-framework and wh-arcade-parody."
metadata:
  node_type: memory
  type: feedback
last_verified: 2026-09-13
---

**Owner directive (2026-09-13, wave-32 architecture-program scoping).**

> "I don't want anything that is a private repo to go through build steps and CI because I keep blowing my GitHub Actions minutes each month."

**Why:** GitHub bills Actions minutes for **private** repositories; public repositories run free.
The owner has been repeatedly exhausting the monthly allowance, and the cost is coming entirely
from the private side of the estate.

**Verified visibility map (`gh repo list`, 2026-09-13):**

| Visibility | Repos |
|---|---|
| PUBLIC (workflows free) | all 8 `noorinalabs/*`; `parametrization/2real-team-framework`; `parametrization/wh-arcade-parody` |
| PRIVATE (no workflows) | `botfarm_inc`, `steve-os`, `Other-brain`, `other-brain-life`, `disembodied-head`, `local_voice_clone`, `mission-control` |

**How to apply:**

1. **Before any story or PR adds or re-enables a GitHub Actions workflow, assert the target repo is PUBLIC.** Make it an explicit acceptance criterion so a reviewer can fail the PR on it.
2. **For a private repo the equivalent control is a LOCAL gate** — `pre-commit` / `pre-push` hooks — which cost no minutes. Do not reach for a workflow.
3. **Do not read a private repo's missing/suspended CI as neglect.** `botfarm_inc` has its workflows parked in `.github/workflows-disabled/` with `ci.merge_requires_green: false`; that is consistent with deliberate minute-conservation, not rot. The real defect in such a repo is an undeclared posture (e.g. a coupling test documented as guarding a restore path while being vacuous) — fix the declaration and add a local gate, do not re-enable the workflow.
4. This does **not** relax [[feedback_local_ci_parity_no_force]]: a private repo still needs the complete check-set, just run locally rather than in Actions.

**Caution — tier directory names lie about visibility.** All three repos under
`steve-os/public-repo/` (`other-brain`, `local_voice_clone`, `mission-control`) are **PRIVATE**
on GitHub, while `steve-os/CLAUDE.md:7` says "Treat `private-repo/` as sensitive" — implying the
`public-repo/` tier is not. Never infer a repo's visibility from its on-disk tier; run
`gh repo view <owner/repo> --json visibility`. Tracked by wave-32 epic E2 (main#1556).
