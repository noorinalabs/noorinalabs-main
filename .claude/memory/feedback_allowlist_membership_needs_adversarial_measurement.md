---
name: feedback_allowlist_membership_needs_adversarial_measurement
description: "When an allowlist IS the safety boundary, each member must be measured at its adversarial edge, not its common invocation — `sort` looks inert until `--compress-program` executes its stdin. Coverage of 'is it listed' is not coverage of 'can it execute'."
metadata:
  type: feedback
last_verified: 2026-08-03
---

An allowlist used as a safety boundary has a membership criterion, and **the criterion is the safety property**. Testing that a member behaves inertly *when invoked plainly* does not establish membership — it establishes the common case, which is never where a bypass lives.

## The instance (W29, PR #1316, found by Nino Kavtaradze at the merge gate)

`HEREDOC_INERT_RELAY_FILTERS` allowlists tools that may sit downstream of a heredoc without making its body count as CODE. `sort` shipped on it. But:

```
sort --compress-program=CMD      # runs CMD with the data on its stdin, once the sort spills
```

Marker proxy, bash and zsh: **the heredoc body genuinely ran.** The hook returned ALLOW with `is_code=[False]` and the body stripped before the matchers. Spill threshold at `-S 1` is ~9 body lines, and the padding is attacker-controlled.

**The author's own standard already excluded this class.** `sed` and `awk` were kept *off* the list precisely because each has a data-driven exec surface (`sed 's/.*/&/e'`, `awk '{system($0)}'`) — "a plain invocation being inert is not sufficient." The ground-truth test for `sort` measured only bare `sort`. The rule was right; one member was never held to it.

What made it a **blocker rather than debt**: the module comment and tests asserted *in writing* that every member had been measured inert. That is a false statement about the code's own safety property — the same class as three untested claims that blocked #1310 the same day.

The other 30 members were then measured plain **and** exec-shaped in both shells and came back clean, including the highest-risk candidate `jq` (`env.PATH`, `$ENV.PATH`, `input_filename`, `@sh` — no `system()` in mainline).

## Second instance, same PR, one round later — a CONTEXTUAL safety premise is a lower bar than inertness

`rg` was then added to the same list, measured inert: `--pre` runs *per input PATH*, and a heredoc-fed stdin pipe has none. The measurement was correct. **The premise was contextual, and the context is attacker-supplied:**

```
rg --pre=/bin/sh pat /dev/stdin     # RAN, both shells — /dev/stdin names the pipe carrying the body
```

`rg` runs `COMMAND PATH` with the file on the child's stdin, so `sh /dev/stdin` executes the body.

**The adversarial test written for exactly this flag still could not catch it** — it exercised only the no-PATH form. An adversarial test that *fixes* the context instead of varying it measures one cell, and here the fixed dimension was the attacker's to choose. That is [[feedback_corpus_misses_its_constant_dimension]] arriving inside a test that was already written to be adversarial.

**Grade the premise, not just the measurement.** "This tool has no exec surface" is unconditional. "This tool's exec surface cannot be reached *in this context*" is conditional on something — ask who controls that something. If the answer is the caller, the premise is not a safety property.

Two more things from that round worth keeping:

- **The reviewer who recommended `rg` was the one who found the hole**, and named it as the same error he had just blocked `sort` for — a plain-form measurement plus a *policy* argument (the org mandates `rg`). **A policy argument is never a safety argument.** He retracted the recommendation on the tracking issue so nobody re-added it citing him.
- Dropping `rg` left a **known contradiction open**: the list still admits `grep`, which this org hard-blocks (#1008), while omitting the mandated `rg`. Recorded deliberately as a residual rather than silently carried — a wrong entry removed for a good reason still leaves the policy conflict it was meant to fix.

## How `rg` got admitted: a missing binary makes ADMITTING assertions pass vacuously

The mechanism, found by the same reviewer a round later and verified against the check-runs API:

| head | Pytest check | what the rg rows asserted |
|---|---|---|
| `8507e4a` | **success** | `expect_runs=False` — "the shell did not run the body" |
| `853c916` | **failure** | `expect_runs=True` — "the shell DID run the body" |

**ripgrep is not installed on the runner.** The pipeline is `command not found`, so at `8507e4a` "the shell did not run the body" was **trivially true** — the suite reported `rg` measured inert on CI while measuring nothing, and the member was admitted on a check that **could not have gone red**. Local was green because rg is installed locally.

**The asymmetry is the point, and it is directional:** a missing external tool pushes every `expect_runs=False` row toward **passing** and every `expect_runs=True` row toward **failing**. So it is **silent for rows that ADMIT a member and loud only for rows that EXCLUDE one** — the exact direction that lets bad entries in. The red that finally appeared was the suite telling the truth about `rg` for the first time on a runner.

**Remedy is install AND guard, not guard alone.** Install the tool in the CI job — `ci.yml` already does this for bashlex ("this install makes CI run them, not skip them") and zsh ("so the zsh half of the oracle RUNS in CI rather than skipping"). Add `skipUnless(which(tool))` **alongside**, never instead: *a guard alone converts a silent vacuous pass into a silent skip, which is the state that let the member in.*

**Generalise:** any test whose assertion is *negative* ("X does not happen") and whose subject is an **external binary** can pass because the binary is absent. Audit those rows against the runner's actual toolchain, not the developer's. And when a long-green check suddenly reds after a row flips from negative to positive, suspect the earlier green rather than the new red.

## Second failure mode: the allowlist can contradict org policy

The same list allowlisted **`grep`** and omitted **`rg`** — while this org **hard-blocks bare `grep`** (#1008) and mandates `rg`. The list admitted the forbidden tool and blocked the required one. Nobody checked the membership set against the conventions the org already enforces elsewhere.

## The general rule — pair every negative row with a positive one sharing its instrument

Found by mutating the **instrument** rather than the code, which is the move that generalises everything above:

| instrument mutation | what went red | the plain-`sort` (negative) row |
|---|---|---|
| marker substitution dead | 6 rows incl. the positive `sort_compress_program` | **stayed green** |
| passthrough script not executable | `sort_compress_program` | **stayed green** |

**A negative row cannot detect its own instrument breaking** — *"did not run"* is exactly what a dead instrument reports. That is the missing-binary vacuity **without needing a missing binary**, and it holds for every `expect_runs=False` assertion regardless of tooling.

What makes such a row sound is the **pair**: a positive row in the same class, sharing the same instrument, red-sensitive to every break the negative row is blind to. `rg` was admitted because at that commit it had **only negative rows**, so nothing could distinguish "inert" from "not installed."

> **A negative ground-truth row is only trustworthy when a positive row in the same class shares its instrument. A member whose measurement can never fail is equivalent to a member with no measurement.**

That is mechanically checkable — for each allowlist member, does at least one row using the same harness *assert something happens*? — and it subsumes the missing-binary case rather than sitting beside it. Recorded on #1318.

## How to apply

- **For each member, ask: can *any* invocation of this execute its input?** Not "is the usual invocation safe." Flags worth probing: `--compress-program`, `-e`/`--exec`, `--filter`, `-f -`, `--random-source`, anything taking a *command* or a *program* as a value.
- **Measure at the boundary with a real proxy**, in every shell the org uses. Reasoning about a tool's manual is not measurement — `sort` reads as obviously inert.
- **Diff the membership set against existing org conventions** before shipping. An allowlist is policy; it can silently contradict policy stated elsewhere.
- **Do not let the code claim more than was measured.** If the comment says "every member measured inert," that must be literally true or the comment is a defect.
- **Structural gap worth closing** (#1318): the suite gated allowlist *coverage* — every member appears in the corpus — but nothing required an **adversarial-invocation measurement per member**. Coverage of "is it listed" is not coverage of "can it execute."

**Why:** an allowlist inverts the usual review instinct. The unknown-by-default side gets scrutiny because it looks dangerous; the listed side reads as already-decided, and a wrong entry there is a silent hole with a green suite around it.

Related: [[feedback_fold_in_or_defer_a_gate_finding]] (this was folded in, not deferred — a working script can contain `sort`, and it fails in the silent-miss direction), [[feedback_pr_body_table_is_a_claim]] (the written "measured inert" claim), [[feedback_both_ends_tested_join_untested]].
