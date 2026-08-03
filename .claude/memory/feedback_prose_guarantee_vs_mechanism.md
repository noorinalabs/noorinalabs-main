---
name: feedback_prose_guarantee_vs_mechanism
description: "A guarantee written in prose and never re-derived from the mechanism. One detection method — read the claim, trace it end-to-end through the code meant to honor it — but four distinct failure SITES (producer / scope / consumer / consumer-ex-ante), each with a different remedy. Six instances in wave 29 alone."
metadata:
  type: feedback
last_verified: 2026-08-03
---

The wave-29 dominant defect. A safety or observability property is **stated** — in a step name, a docstring, a module comment, a test name, a PR body — and nobody ever traced it back through the code that is supposed to honor it. The prose is what every downstream reader trusts, so the gap survives indefinitely and is invisible to review-by-reading.

**One detection method for all of them: read the claim, then trace it end-to-end through the mechanism meant to produce it.** Not "does this look right" — *follow the signal path*.

## The taxonomy (Aino Virtanen, W29 #1330 gate)

The failure **site** differs every time, which is why a single slogan like "the check can't fail" does not cover the class — it describes only the first row and actively mis-describes the second.

| Site | Shape | Instance |
|---|---|---|
| **Producer** | cannot emit a negative signal at all | `ci.yml` smoke step ends in `\|\| true` |
| **Scope** | fires, *can* fail, but measures a narrower property than the prose claims | #1318 allowlist gate: tests coverage, claims per-member inertness |
| **Consumer** | producer is correct; no consumer exists | hook exceptions written to `traces.jsonl`, which both documented consumers are told **not** to read |
| **Consumer, ex ante** | consumer described in prose, never built | `log_posttooluse_dispatch`: "informational unless `outcome.raised` is set" — no code anywhere implements the "unless" |

Four sites, four different remedies. That is the value of the taxonomy over the slogan: it tells you *where to look*.

## Two more instances from the same PR

- **A test that is positive-only wearing a negative name.** `test_check_never_calls_gh` asserted only `mock_run_git.called` and never referenced `gh`. Nino Kavtaradze added a real `subprocess.run(["gh", "pr", "view", "1"])` to `check()` — the exact behavior the name forbids — and it **passed**, along with all 4079 tests. Worse than an absence-only assertion, because *the name is what the next reader trusts*. The PR body cited it as its #1318 positive-pairing compliance evidence, so the citation didn't merely fail to describe the test — it inverted it.
- **A guard inert in this environment.** A new `UnicodeDecodeError` catch was documented as closing a gap "not previously guarded ANYWHERE." But `sys.stdin.errors` is `surrogateescape` here, so invalid UTF-8 becomes lone surrogates and never raises. Its test kills its mutant only via injected mock. The guard is genuine defense under a strict-errors locale — the defect is purely that the prose implies a demonstrated live gap.

## The sharpest single instance: a step name that describes a different input than its body supplies

`.github/workflows/ci.yml`, step named **"Verify hooks exit 0 on empty stdin"**:

```yaml
for f in .claude/hooks/*.py; do
  echo '{}' | python3 "$f" || true
done
```

**Two independent falsifications of one name.** `|| true` means no exit code turns it red — but it also pipes `{}`, which is **valid JSON and not empty stdin**. So even with `|| true` deleted it would still never test what it is named for. That second defect is the mechanism by which a real crash (`validate_wave_label_evidence.py` dying on malformed stdin) survived indefinitely with a green CI.

Aino's framing: **a second lock on a door already in the wrong wall.**

Two corollaries worth keeping:

- **A partly-toothless job is more dangerous than a uniformly toothless one.** The compile step directly above (`:108-114`) has no `|| true` and *does* gate. The working half supplies the credibility the broken half coasts on — which is probably why this survived review.
- **Repairing such a step requires RENAMING it.** Once it probes three inputs it is no longer "on empty stdin"; leaving the old name reproduces the original defect in miniature.

## How to apply

- **Trace, don't read.** For any documented guarantee, follow it to the code that produces it, then to the code that consumes it. Both ends can exist while the join does not — see [[feedback_both_ends_tested_join_untested]].
- **Ask "could this go red?" as a separate question from "is this correct?"** They are independent, and only the pair is sufficient. A generated-payload test can pass on an unfixed tree exactly as a fixture can.
- **Mutation-test the fix too.** A de-vacuification that ships un-mutation-tested is its own instance. Plant a deliberate failure and require the instrument to notice.
- **Grep the whole job, not the step.** A job-level `continue-on-error` re-vacuifies a step without touching its lines and survives a careful diff read.
- **When the complaint is "too slow," every cheap remedy is some form of *look at less*** — and looking at less is indistinguishable from working unless you require the failure to stay closed. Require explicit truncation-fails-closed (#1332 criterion 4).
- **A stale-looking reason is more dangerous than a missing one.** #1329's `validate_edit_completion` exclusion said `main()` calls both paths "unconditionally"; it actually branches on `hook_event_name`. A reader who sees the branch concludes the reason is *stale* rather than *wrong*, converts the hook, and reintroduces the bug the exclusion prevents. Two partially-correct descriptions existed (one named the filter and misdescribed the structure, the other described the structure and omitted the filter) and the union was written down nowhere — neither reviewer was wrong, **the record was**.

**Why:** code and tests get *run*; prose gets *written from memory* and then trusted forever. Every artifact in this class was reviewed and approved by someone competent, because reading it is exactly the activity that cannot detect it.

Related: [[feedback_pr_body_table_is_a_claim]] (the same root, restricted to measurement tables), [[feedback_allowlist_membership_needs_adversarial_measurement]] (the scope-site instance in full), [[feedback_fixture_makes_guard_assertion_inert]], [[feedback_silent_zero_is_not_a_measurement]], [[feedback_equivalent_mutant_is_not_an_inert_test]], [[feedback_corpus_misses_its_constant_dimension]] (#1332 is that lesson on the *size* dimension — a corpus of hand-typed adversarial strings is small by construction).
