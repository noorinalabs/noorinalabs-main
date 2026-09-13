---
name: feedback_short_flag_consumes_next_token
description: "A typo'd short flag that TAKES AN ARGUMENT does not error — it silently consumes the next token and re-interprets your command. `rg -rl PATTERN .` is well-formed and means 'replace matches with the literal string l'. The tell is plausible-but-wrong output from a command that should have returned something structurally different."
metadata:
  type: feedback
last_verified: 2026-09-13
---

**The general rule (Aino Virtanen, W29):** a flag that takes an argument will **silently consume the next token**, so a mistyped short flag does not produce an error — it produces a *different, well-formed command*. This is why the failure surfaces as output rather than a diagnostic, and why it survives a careful re-read of the command line.

## The instance

Sweeping for stale prose, `rg -rl PATTERN .` was run instead of `rg -l PATTERN .`. In ripgrep, `-r` is `--replace`, so it took `l` as the replacement string. The command is entirely valid; it means *"print matches with each match replaced by the literal string `l`"*. Result: **1.9 MB of mangled lines** instead of a file list.

`-r` and `-l` are one keystroke apart on the same hand.

## The tell, which is the part worth memorising

It had **already silently garbled an earlier sweep in the same session**, which was seen, judged a display artifact, and moved past. The tell was present and got explained away.

> **Plausible-but-odd output from a command that should have returned something structurally different** — filenames, a count, a short list — is the signal. Not an error; there will not be one.

Ask *"is this the shape of output this flag combination produces?"* rather than *"does this output look wrong?"* A wall of text where you expected 6 paths is a shape mismatch even when every line looks like real repo content.

## Why it generalises

This is not an `rg` fact. It applies to **every tool in the toolchain with argument-taking short flags** — `-e`, `-f`, `-o`, `-r`, `-C`, `-S`, `--pre`, `--compress-program`. The same mechanism is what makes `sort --compress-program=CMD` and `rg --pre=CMD` exploitable (see [[feedback_allowlist_membership_needs_adversarial_measurement]]): a flag that takes a *command* as its value is the dangerous end of the same design.

A rule of "don't confuse `rg -r` and `-l`" catches exactly one instance. The argument-consuming framing catches the next one in a different tool.

## How to apply

- **When a search returns an unexpected volume or shape, re-read the flags before believing the result.** Especially after a fast-typed one-off.
- **Prefer long flags in scripts and committed commands** (`--files-with-matches` over `-l`) — they cannot silently absorb the next token into a different meaning.
- **A zero result and a huge result are equally suspect.** Both are shapes, and the wrong flag produces either depending on which one you hit — cf. [[feedback_silent_zero_is_not_a_measurement]].
- **Do not explain away odd output on a first sighting.** That is the cheapest moment to catch it; every later use inherits the corrupted result.

Follow-up: this belongs in `docs/TOOLCHAIN.md` § Text search (and `ontology/conventions.md`) via a PR — recorded here first so it is not lost. The general framing is the one to codify, not the specific flag pair.

**Third instance, 2026-09-13 (#1550) — the tell was explained away again, by a different agent, and by me.** `rg -rn` (not `-rl` this time) during a memory judge pass; every backticked identifier in the output was rewritten to `n`. The odd shape *was* noticed — and then falsified with a check that could not fail: re-running on a short temp file with `rg -n`, which is the correct invocation and so returned correct output, "clearing" the suspicion and pointing the diagnosis at harness redaction instead. A second agent hit the same flag the same hour and nearly filed the mangled quotation as a real charter defect. Sharpening for the § How to apply list below: **when odd output makes you suspect the tooling, the control must re-run the SAME command, not a corrected one.** Reproducing with a fixed command tests a different hypothesis than the one you hold, and it will exonerate the tool every time. Cf. the contaminated-control finding in [[feedback_enforcement_hierarchy]] (`find /etc -name zzz` exiting 1 for permissions, not for no-match, confirming a wrong rule).

Related: [[feedback_prose_guarantee_vs_mechanism]] (same round; a mechanism that appears to work and does not), [[feedback_silent_zero_is_not_a_measurement]].
