---
name: feedback_wave_branch_merge_not_squash
description: "NEVER --squash on any base, main included (owner 2026-07-30) — squash collapses persona authorship to the bare principal; Hook 22 only gates wave branches, so main is an enforcement gap"
metadata:
  node_type: memory
  type: feedback
last_verified: 2026-07-30
---

> **SCOPE WIDENED — owner directive 2026-07-30: "no more squash merges." `--squash` is prohibited on EVERY base, including `main`.** This note originally covered only per-issue → wave-branch merges; the reasoning below applies unchanged to `main`, and the owner has now made that explicit.
>
> **Critical enforcement gap:** Hook 22 hard-blocks `--squash` only when the base resolves to `deployments/phase-*/wave-*`. A squash into **`main` is NOT blocked** — the hook stays silent and the merge succeeds. On `main` this rule is convention-only, so **check the method yourself before merging.** Treat the gate's silence as a gap, never as permission.
>
> **How it was found:** on 2026-07-30 five PRs (#1173, #1153, #1154, #1155, #1156) were squash-merged to `main` under the then-current charter wording that called squash "the standard path" for `main`. All five landed authored by `parametrization <parametrization@gmail.com>`, discarding Aino Virtanen / Nurul Hakim / Nadia Khoury / Weronika Zielinska / Lucas Ferreira attribution. No gate fired, because `direct-to-main` waves open no wave→main integration PR and therefore never run the commit-author gate that would have caught it. **The absence of a red gate is exactly why this went unnoticed for a whole wave's worth of merges.**
>
> Charter now says so in both places: `charter/pull-requests/reviews.md` § Pre-Approved merge (the "squash is the standard path" clause is **withdrawn**) and `charter/pull-requests/wave-merge.md` (the "squash-into-main is untouched" parenthetical is **withdrawn**).

When merging a **per-issue PR into a wave branch** (`deployments/phase-{P}/wave-{M}`), use `gh pr merge <N> --merge`, **NOT `--squash`**.

**Why:** GitHub squash-merge re-authors the resulting single content commit to the **bare gh principal** (`parametrization <parametrization@gmail.com>`, committer=GitHub). This is because every persona email `parametrization+First.Last@gmail.com` is a Gmail +alias of the one `parametrization@gmail.com` account, so GitHub attributes all of them to the `parametrization` account and stamps that as the squash author — the persona name (Aino/Lucas/Weronika/Nurul/…) is demoted to a `Co-authored-by` trailer. At wave-wrapup the wave→main PR then fails the **`Verify commit authors are roster members`** CI gate (`.claude/lib/verify_commit_identity.py`, main#627 / deploy#409 evasion class): it runs `git log --no-merges base..head` and every squash commit is a single-parent **content** commit authored as `parametrization`, so the `--no-merges` merge-commit carve-out does NOT save it. Caught in P7W19 (#898).

`--merge` avoids this: the persona-authored content commits are preserved verbatim (they pass the gate), and the bare-principal **merge** commit GitHub creates is excluded by `--no-merges`. The gate's own docstring states this is the expected per-issue→wave-branch merge method.

**How to apply:**
- Per-issue PR → wave branch: `gh pr merge <N> --merge` (literal PR number; never a batch loop — [[feedback_batch_loop_merge_evades]]).
- Wave→main integration PR: also `--merge`, and **never `--delete-branch`** (wave branches retained — [[feedback_wave_branch_merge_retain]]).
- Only `noorinalabs-main` carries the commit-author gate; child repos lack it (so a child squash is latent-not-blocked), but use `--merge` everywhere for consistent attribution feeding the retro trust matrix.

**If already squashed (recovery):** re-author the wave-branch commits to true personas and force-update. Replay onto the *correct* base (the wave-branch's merge-base with main — NOT a later kickoff-status commit) via `git cherry-pick --no-commit <sha>` then `git -c user.name="Full Name" -c user.email="parametrization+First.Last@gmail.com" commit --no-edit -C <sha> --reset-author`. Use **literal** identities (the identity hook parses the command string pre-expansion, so `-c user.name="$var"` is rejected). `-C <sha> --reset-author` reuses the original message while resetting author to the `-c` committer — avoids needing message files (which trip `block_stale_tmp_message_file` if >30s old). Verify the rewritten tip's root tree SHA equals the original's (content-identical, metadata-only) before `git push --force-with-lease`.

**Related child-repo wrap gotcha:** the structural-ontology `staleness-check` only gates PRs to **main**, not wave-branch PRs. So a per-issue PR adding a tracked source file (`.py`/`.cypher`/`.ts`) without regenerating the child structural index passes its own CI but reddens the wave→main PR. Regenerate at wrap: `python3 scripts/structural_ontology.py emit --gen-lib <parent>/.claude/lib` (child) — this is the child analog of `/wave-wrapup` Step 12b. Caught in P7W19 (#222, da#202's new `.cypher`).

**Promotion (P7W19 retro, owner-decided 2026-06-25):** both halves of this memory are now codified, so it no longer relies on soft recall —
- The `--merge`-not-`--squash` rule → **Hook 22 (`block_squash_wave_merge.py`)**, a PreToolUse hard-block on `gh pr merge <N> --squash` into a `deployments/phase-*/wave-*` base (charter `hooks.md § Hook 22`, `pull-requests.md § One Merge Model Per Wave`).
- The child structural-staleness gotcha → **`/wave-wrapup` Step 10.7** (pre-regen each child's structural index before opening the wave→main PR).
