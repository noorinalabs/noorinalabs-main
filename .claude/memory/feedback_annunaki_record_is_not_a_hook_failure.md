---
name: feedback_annunaki_record_is_not_a_hook_failure
description: "A record in .claude/annunaki/errors.jsonl is not evidence that the hook it names failed. `hook:` is writer-attribution, not failure-attribution, and reading error text is captured as producing it. Read the mechanism before inferring one from the log line."
metadata:
  type: feedback
last_verified: 2026-08-04
---

## The law

**A record in `.claude/annunaki/errors.jsonl` names the hook that WROTE it, not a hook that failed.** Two independent ways the log invites a wrong reading, both measured at the W29 retro (#1354):

**1. `hook:` is writer-attribution.** `annunaki_monitor` appears in the `hook:` field of every masked-failure record it captures — because it is the writer. The wave-29 triage brief read 52 such records as "52 times the error monitor itself errored," and reasoned onward that *an error monitor that throws is blind exactly when it matters*. Sound reasoning, false premise: all 52 were `exit_code: 0` / `confidence: high` / `category: masked-failure`, the monitor did not throw once in the wave, and 35 were genuine catches of real pipe-masked push and test failures. The discriminating fields are in every record — **read `exit_code` and `category` before reading `hook:` as blame.**

**2. Reading error text is captured as producing it.** `_is_content_display` (`annunaki_monitor.py:321`) suppresses display idioms via an allowlist of leading verbs (`:212` — `cat|head|tail|less|more|bat|git show|git diff|git log|gh pr diff|gh pr view`), and `:245` disqualifies **any** command containing `2>&1`. So the two commands anyone actually uses to diagnose CI — `gh run view <id> --log-failed 2>&1 | tail -c 8000` and `rg -n "FAILED" <saved-log>` — fail the allowlist twice over and mint `confidence: high` records from log *content*. One already-fixed CI failure produced **17** records this way: 33% of the monitor class, 4% of the wave's whole 427-record genuine population.

## Why it matters more than a miscount

**The false-record class scales with how hard a failure was to debug.** A failure inspected five times writes five records. So the artifact whose purpose is surfacing *unsolved* problems systematically over-weights *solved* ones — the harder something was to fix, the louder its corpse. At W29 all 17 traced back to a bug fixed in-wave (`ci.yml:148-158`, `fetch-depth: 0` for `test_wave_status.py::BaseVsHeadDifferential`, which `git show`s a historical SHA a shallow clone lacks). Triage cost is paid every wave until #1354 lands, and #1354's fix widens the verb list — it does not remove the general obligation to ask whether a captured command was *reading* error text.

## How to apply

- **Before citing a class count from `errors.jsonl`, group by the underlying failure signature, not by `hook:`.** 17 records, 1 incident. `_dedup_hash` does not collapse these — the capturing commands genuinely differ.
- **Check whether the cited bug is still live** before filing or escalating. Two of W29's loudest classes were already fixed in-wave.
- **`exit_code: 0` + `category: masked-failure` means the monitor is working**, not failing. A monitor that actually threw would surface via `outcome.raised` in `traces.jsonl` — which, per [[feedback_prose_guarantee_vs_mechanism]], no consumer reads (#1331), so its silence is not evidence either.
- Same shape one level up: **`skip_*` action records are notices, not misses.** W29's `post_wave_kickoff_comment` / `skip_unresolved_issue_number` records state plainly that no comment was posted and name the remediation (`kickoff_sweep.py`, #1141); the sweep ran and all four issues had kickoff comments 8 seconds later. I read it as a silent fail-open by analogy to a sibling class and was wrong; only re-verification against the issues caught it. Read the record's own text before inferring its mechanism from a neighbour's.

## Pattern class

This is [[feedback_silent_zero_is_not_a_measurement]] pointed at a log rather than a probe: the instrument's output has a shape that reads as a measurement of one thing while measuring another. Companion to [[feedback_verify_posttooluse_firing]], which covers the write side (does the hook fire at all) — this note covers the read side (what a record that exists actually attests). Sibling: [[feedback_push_pipe_masks_rejection]], the genuine masked-failure class the monitor exists to catch and which must not be suppressed while fixing the false one.

W29 #1354.
