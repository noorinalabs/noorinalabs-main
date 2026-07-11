---
name: feedback_child_checkout_goes_stale_mid_session
description: The local child-repo clone goes stale DURING a session as you merge PRs — /session-start's fast-forward is a start-of-session snapshot, not a subscription. Never run terraform/build/test against a child checkout without re-verifying it against origin/main first.
metadata:
  type: feedback
---

**2026-07-11, deploy Backblaze bootstrap.** I ran `terraform plan` in `noorinalabs-deploy/terraform/backblaze/` and got **`0 to add, 1 to change`** where the bootstrap doc promised **`2 to add, 1 to change`**. The backups bucket, its scoped key, and all three `backups_*` outputs were **absent from the config**.

I was one sentence away from telling the owner the bootstrap document was fiction.

**The config was fine. The CHECKOUT was 35 commits behind `origin/main`.**

```
local HEAD:  86896c7   Merge PR #573        <- from BEFORE this session's work
origin/main: 6cdcb58   Merge PR #584        <- everything we merged TODAY
behind by:   35 commits
```

`origin/main:terraform/backblaze/main.tf` declared `b2_bucket.backups` (L75) and `b2_application_key.backups_rw` (L99) the whole time.

## The mechanism, and why /session-start does not save you

`/session-start` Step 0 runs `check_child_checkouts.py --refresh`, which fast-forwards clean children to `origin/main`. **That is a snapshot at session start, not a subscription.**

> ### **We merged nine PRs during this session. Every one landed on `origin/main`. The local clones pulled NONE of them.**

The longer and more productive the session, the staler the child checkout gets. **The drift is CAUSED by the work.** A session that merges nothing stays fresh; a session that merges nine PRs is guaranteed to be stale by the end — which is exactly when you start running things against it.

## What made this dangerous rather than merely wrong

A `terraform plan` from a stale config is not a stale *reading* — it is a **stale instruction against live state.**

- **What it would have done:** created **no backup bucket at all**, while churning the pipeline bucket's lifecycle rules. A silent no-op on the thing you came to do.
- **What it would have done if the resource already existed:** `0 to add` becomes **`1 to destroy`**. A config that does not declare a resource is a config that **deletes** it. Here the backups bucket did not exist yet, so the stale plan was survivable — **by luck, not by design.**

**Generalise past Terraform.** Anything that reads the child working tree and acts on it inherits this: a build, a test run, a lint gate, a `docker build`, a script that greps `.github/workflows/`. **A stale checkout does not announce itself — it produces a confident, well-formed, wrong answer.**

## How to apply

**Before running ANY command that reads a child repo's working tree — especially one that writes to live infrastructure — re-verify freshness. It is one command:**

```sh
git -C <child> fetch --quiet origin main
git -C <child> rev-list --count HEAD..origin/main   # MUST be 0
```

- Non-zero → `git -C <child> pull --ff-only origin main` and re-derive **from scratch**. Do not patch the conclusion you already drew.
- **Especially after merging anything in that repo during the session.** You merged it; your clone did not.
- **`terraform plan` diverging from a documented expectation is a checkout-freshness signal before it is a config bug.** Check the SHA before you doubt the document.

## The class

Same shape as everything in [[feedback_silent_zero_is_not_a_measurement]]: **I read a state and treated it as current.** The instrument (the working tree) genuinely could not answer the question I asked it (*"what does the config say?"* — it can only say *"what did the config say 35 commits ago?"*), and it answered confidently anyway.

And the tell was there in the output: **the plan contradicted a written expectation.** I nearly resolved that contradiction by disbelieving the document, because the plan felt like ground truth. **A plan is not ground truth. It is a function of a checkout.**

See also [[feedback_canonical_source_via_git_show]] — the same defect, caught earlier, for reading a file: *local main may lag origin; fetch via `git show <sha>:<path>`*. **That memory was about READING a file. This one is about ACTING on a tree — and the blast radius is infrastructure, not a wrong quote.**
