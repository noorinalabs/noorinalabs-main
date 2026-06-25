---
name: feedback_wave_branch_merge_not_squash
description: "Per-issue PRs into a wave branch must merge with --merge, not --squash (squash collapses persona authorship to bare principal → commit-author gate red on wave→main)"
metadata:
  node_type: memory
  type: feedback
---

When merging a **per-issue PR into a wave branch** (`deployments/phase-{P}/wave-{M}`), use `gh pr merge <N> --merge`, **NOT `--squash`**.

**Why:** GitHub squash-merge re-authors the resulting single content commit to the **bare gh principal** (`parametrization <parametrization@gmail.com>`, committer=GitHub). This is because every persona email `parametrization+First.Last@gmail.com` is a Gmail +alias of the one `parametrization@gmail.com` account, so GitHub attributes all of them to the `parametrization` account and stamps that as the squash author — the persona name (Aino/Lucas/Weronika/Nurul/…) is demoted to a `Co-authored-by` trailer. At wave-wrapup the wave→main PR then fails the **`Verify commit authors are roster members`** CI gate (`.claude/lib/verify_commit_identity.py`, main#627 / deploy#409 evasion class): it runs `git log --no-merges base..head` and every squash commit is a single-parent **content** commit authored as `parametrization`, so the `--no-merges` merge-commit carve-out does NOT save it. Caught in P7W19 (#898).

`--merge` avoids this: the persona-authored content commits are preserved verbatim (they pass the gate), and the bare-principal **merge** commit GitHub creates is excluded by `--no-merges`. The gate's own docstring states this is the expected per-issue→wave-branch merge method.

**How to apply:**
- Per-issue PR → wave branch: `gh pr merge <N> --merge` (literal PR number; never a batch loop — [[feedback_batch_loop_merge_evades]]).
- Wave→main integration PR: also `--merge`, and **never `--delete-branch`** (wave branches retained — [[feedback_wave_branch_merge_retain]]).
- Only `noorinalabs-main` carries the commit-author gate; child repos lack it (so a child squash is latent-not-blocked), but use `--merge` everywhere for consistent attribution feeding the retro trust matrix.

**If already squashed (recovery):** re-author the wave-branch commits to true personas and force-update. Replay onto the *correct* base (the wave-branch's merge-base with main — NOT a later kickoff-status commit) via `git cherry-pick --no-commit <sha>` then `git -c user.name="Full Name" -c user.email="parametrization+First.Last@gmail.com" commit --no-edit -C <sha> --reset-author`. Use **literal** identities (the identity hook parses the command string pre-expansion, so `-c user.name="$var"` is rejected). `-C <sha> --reset-author` reuses the original message while resetting author to the `-c` committer — avoids needing message files (which trip `block_stale_tmp_message_file` if >30s old). Verify the rewritten tip's root tree SHA equals the original's (content-identical, metadata-only) before `git push --force-with-lease`.

**Related child-repo wrap gotcha:** the structural-ontology `staleness-check` only gates PRs to **main**, not wave-branch PRs. So a per-issue PR adding a tracked source file (`.py`/`.cypher`/`.ts`) without regenerating the child structural index passes its own CI but reddens the wave→main PR. Regenerate at wrap: `python3 scripts/structural_ontology.py emit --gen-lib <parent>/.claude/lib` (child) — this is the child analog of `/wave-wrapup` Step 12b. Caught in P7W19 (#222, da#202's new `.cypher`).
