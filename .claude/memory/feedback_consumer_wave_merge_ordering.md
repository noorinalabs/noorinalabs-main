---
name: feedback_consumer_wave_merge_ordering
description: consumer-repo wave→main PR whose CI resolves a tool from the producer's base branch must merge AFTER the producer's wave→main; else its staleness/build check fails on the not-yet-present tool.
metadata:
  type: feedback
---

When a **consumer** repo's CI resolves a shared tool from a **producer** repo's
*base branch* (sibling-checkout pattern, `feedback_cross_repo_wave_ref_resolution`),
the consumer's wave→main integration PR will FAIL its tool-dependent check until the
producer's wave→main PR has merged — because the check resolves the tool from the
producer's `main`, where the tool does not exist yet.

**Concretely (P6W17, #820 C×T2 pilot):** isnad-graph#1130's `staleness-check`
sibling-checks-out `noorinalabs-main` resolving the ref to the PR's **base** (`main`)
and runs the structural-ontology generator from there. The generator was still only
on `deployments/phase-6/wave-17`, merging to main via main#861. So #1130's
staleness-check was RED purely on ordering — `main#861` (producer) had to merge
first; re-running #1130's check immediately after went green (`gh run rerun <id> --failed`).

**Why:** The wave-branch ref-resolution helper matches the PR's `base_ref`. For a
per-issue PR (base = wave branch) the producer's tool IS on the wave branch, so it
passes. For the wave→main integration PR (base = main) the tool is only on main once
the producer's integration PR merges. Same helper, different base → the dependency flips.

**How to apply:** At `/wave-wrapup`, sequence cross-repo integration merges
**producer-before-consumer**, not alphabetically. A consumer's only-failure being the
tool-dependent check is an ordering signal, not a real defect — merge the producer,
re-run the consumer's check, then merge the consumer. This will recur for **every** repo
in the P7W1 #820 (ontology C×T2) 6-repo fan-out (all six consume
the noorinalabs-main generator). Related: [[feedback_passing_repro_masks_bug]] (the
inverse — a check that's green for the wrong reason), [[feedback_cross_repo_wave_ref_resolution]].
