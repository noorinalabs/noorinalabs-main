---
name: feedback_rg_dash_r_is_replace
description: "`rg -r` is --replace, NOT 'recursive'. `rg -rn 'pat' file` silently consumes `n` as the replacement string and prints every match rewritten as `n` — the file is found, the pattern matched, and the OUTPUT IS A LIE. Recursion is ripgrep's default; a `-r` typed for recursion is always doing something else."
metadata:
  node_type: memory
  type: feedback
last_verified: 2026-09-13
---

**What happens.** `rg -rn 'validate_vps_host' .claude/team/charter/hooks.md` prints:

```
## Hook 10: Validate VPS_HOST (`n.py`)
```

The actual line reads ``## Hook 10: Validate VPS_HOST (`validate_vps_host.py`)``. `-r`/`--replace` took `n` as its argument, so every match was rewritten to `n` on output. The `n` never reached the flag parser as `-n`.

**Why it is dangerous rather than merely wrong.** The command still finds the right file and still matches the right pattern, so it looks like a successful search. This is the sibling of [[feedback_silent_zero_is_not_a_measurement]] in a nastier direction: not a silent *zero*, but a silent **substitution** — a confident, plausible, wrong quotation.

On 2026-09-13 this fabricated a charter documentation defect (Hook 10's filename recorded as `n.py`) that was one step from being filed as a wave-32 story. Two agents hit it independently within the same hour; the Program Director caught it by opening the file with `--fixed-strings`. `rg --fixed-strings -c '`n.py`' .claude/team/` returns zero — the charter was correct all along.

**Why the muscle memory is wrong.** `-rn` reads naturally as "recursive + line numbers", by analogy with `grep -rn`. But **ripgrep recurses by default**, so a `-r` typed for recursion is *always* doing something else. In ripgrep, `-n` alone gives line numbers.

**How to apply.**

1. Never pass `-r` to `rg` unless you actually intend `--replace`. Use `rg -n 'pat' <path>`; recursion needs no flag.
2. When quoting a file's contents as evidence for an issue, PR, charter claim or review verdict, verify with `rg --fixed-strings` or `sed -n`. **A tool that can rewrite its own output must not be the sole source for a quotation you are about to file.**
3. Same class as the `gh` failures found the same day: `gh issue list` returning a swallowed error as `0`, and `gh project item-add` failing with `rc=1` and the misleading text `unknown owner type`. In all three the tool reports something plausible rather than erroring — so the defence is to check the value against a second, differently-shaped instrument, not to trust the first.
