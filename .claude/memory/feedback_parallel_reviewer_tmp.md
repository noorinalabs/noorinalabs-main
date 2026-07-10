---
name: feedback_parallel_reviewer_tmp
description: Parallel reviewer agents writing to the same /tmp/review.md path overwrite each other; one reviewer ends up posting the other's body under their own identity, breaking the validate_pr_review distinct-Requestor gate
type: feedback
originSessionId: 52b75b4f-2d1e-4024-b6db-e384bc5f8904
---
When two reviewer-class agents are spawned in parallel on the same PR and the brief specifies `--body-file /tmp/review.md`, both agents write to the SAME path in a shared filesystem. The later writer overwrites the earlier writer's draft, so whichever agent posts second (or posts after a race-loss) ends up sending the OTHER reviewer's body under their own GitHub identity. Result: two comments with the same `Requestor:` line (both Santiago, or both Aino) → `validate_pr_review` hook counts 1 distinct Requestor, not 2 → 2-reviewer gate fails.

**Why:** Reviewer briefs that hardcode `/tmp/review.md` predate the parallel-spawn pattern. Both agents share the host filesystem; `/tmp` is not agent-scoped. P3W9 PR #382 dual-reviewer (Aino-382 + Santiago-382) instance 2026-05-11: Aino's draft was clobbered by Santiago's before posting; Aino posted Santiago's body verbatim under `user.login=parametrization` (the shared GitHub identity layer made it visually obvious only on `Requestor:` line read-back). Fixed in-place via PATCH per `verdict_amendment_edit_not_append` — comment URL preserved.

**How to apply:**
- When acting as a reviewer in a parallel-spawn scenario, write the verdict body to a UNIQUE filename: `/tmp/<reviewer-name>_review_<PR#>.md` (e.g., `/tmp/aino_review_382.md`), NOT the brief's default `/tmp/review.md`.
- ALWAYS read-back the posted comment immediately after `gh pr comment` and verify the `Requestor:` line matches YOUR identity, not the other reviewer's. The 4-literal-string verification in the brief catches this if you check the literals BEFORE assuming success.
- Recovery: if you discover post-hoc that you posted the wrong body, edit in place via `gh api -X PATCH .../issues/comments/<id> --input <json>` where the JSON is built with `python3 -c "import json; print(json.dumps({'body': open('file').read()}))"`. Do NOT post a new comment — the hook counts the most recent verdict per author and a corrected new comment leaves the bad one behind.
- Charter follow-up worth proposing in retro: brief template should specify per-reviewer filename, OR validate_pr_review hook should warn on identical bodies across distinct GitHub-identity authors as a likely collision signal.

## The shared scratch path is `$CLAUDE_JOB_DIR/tmp`, and it is shared by EVERY agent in the job (2026-07-10)

The `/tmp/review.md` case above is one instance of a broader fact: **`$CLAUDE_JOB_DIR/tmp` is a single directory shared by every agent spawned in the same job**, not per-agent. During a large parallel review session it held 1806 entries and 123 directories authored by six different agents.

Two agents building mutation harnesses each `git archive`'d a repo into a scratch subdir, and one `rm -rf`'d a *shared parent* to rebuild — deleting the other's export. **Each would have read the other's vanished export as their own setup failing.** For mutation work this is the worst kind of collision: a harness whose export silently disappeared and a mutant that never applied produce the *same* green (or the same spurious red).

**How to apply:**
- Name every scratch path `<agent>_<pr#>_<unique>` and **never `rm -rf` a shared parent** — only paths you created under your own uniquely-named subtree.
- After `git archive <sha>` into a scratch dir, **assert the export is the tree you asked for** before trusting it: `git hash-object -- "$ABS/path"` must equal `git rev-parse <sha>:path`. A mid-run overwrite by another agent shows up here.
- The structural generator derives the repo name from the output directory **basename**, so keep the basename (`noorinalabs-data-acquisition`) and make the *parent* unique: `$CLAUDE_JOB_DIR/tmp/<agent>_<pr#>_<n>/noorinalabs-data-acquisition`.

### `$$` is NOT stable across Bash tool calls — do not use it for a cross-call unique dir

Each Bash tool invocation is a **fresh shell**, so `$$` (the shell PID) is a *different value on every call*. Confirmed:

```
call 1:  echo $$   ->  3471437
call 2:  echo $$   ->  3471547     # different shell, different PID
```

So `mkdir dir_$$` in one call and `cd dir_$$` in the next land in **different directories**. It is stable only *within* a single call/block. The failure it produces is a silent-zero-family instrument lie: a "does my export still exist / does the blob differ?" probe run in call 2 against `dir_$$` checks a path nobody wrote, and returns a false "missing / differs." (Surfaced by a reviewer whose blob-identity check reported a spurious mismatch against a directory the previous call never created.)

**How to apply:** for a scratch dir that must persist across Bash calls, use a fixed literal chosen once (`<agent>_<pr#>_1`), or a name derived from something stable across calls (the PR sha, the agent name) — never `$$`. Reserve `$$` for create-and-use-in-the-same-block. Sibling of [[feedback_silent_zero_is_not_a_measurement]]: the instrument pointed at a path that never existed and reported its absence as data.
