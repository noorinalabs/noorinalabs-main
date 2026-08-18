---
name: feedback_commit_identity_roster_from_cwd
description: "The commit-identity gate picks WHICH repo's roster to validate the author against from the shell's process CWD, not from the `git -C <path>` target — so committing a child-repo change while standing in another repo blocks with a wrong-roster error. `cd` into the worktree before committing."
metadata:
  type: feedback
last_verified: 2026-08-17
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---

When committing in a child-repo worktree, the local commit-identity gate resolves **which repo's `roster.json` to validate the author against** from the **shell's current working directory**, NOT from the `git -C <path>` target.

Running:

```
git -C /path/to/child-worktree -c user.name="X" -c user.email="…" commit …
```

while the shell's cwd is a *different* repo validates `X` against the **wrong repo's roster** and blocks with *"not a recognized roster member"* — listing the members of the repo you are standing in, not the one you are committing to. The error message is actively misleading: it names a roster that has nothing to do with the commit.

**Observed 2026-07-26**, merging wave-28 child PRs: a `noorinalabs-data-acquisition` merge commit authored as *Alejandra Reyes-Fuentes* (a valid da roster member) was rejected against the **ingest-platform** roster, because the shell cwd was still an ip worktree left over from a prior `git -C` call. `git -C` retargets git; it does not change the process cwd the hook reads.

## Why it is easy to hit

The Bash tool's cwd **persists between calls**. A single earlier `cd` — even for an unrelated read-only check — silently sets the roster that the next commit is validated against. This is the same root cause as [[feedback_spawn_worktree_follows_orchestrator_cwd]] (a stray `cd` misroutes the next isolated spawn); the cwd is a hidden global that several gates read.

## How to apply

For any commit in a child-repo worktree, **`cd` into that worktree first**:

```
cd /path/to/worktree && git -c user.name="…" -c user.email="…" commit …
```

`git -C` remains fine for read-only work, merges, and pushes — it is specifically the **identity gate on `commit`** that needs the cwd to match. Per-commit `-c` flags remain mandatory either way (never global or repo `git config` — `charter.md` § Commit Identity).

Related: [[feedback_child_repo_implementer_rule]] (which roster a child-repo author must come from — this note is the *mechanical* half of that rule: right name, wrong cwd, still blocked), [[feedback_child_repo_spawn_no_isolation]] (how to get a usable child worktree in the first place), [[feedback_owner_merge_gate_review_first]].
