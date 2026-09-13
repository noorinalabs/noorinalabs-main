---
name: feedback_rg_dash_r_is_replace_not_recursive
description: "`rg -rn <pat>` is not grep's recursive+line-numbers — `-r` is --replace and eats the next token, silently rewriting every match to that string. Output stays plausible, so corrupted identifiers get transcribed as verified fact."
type: feedback
last_verified: 2026-09-13
promotion_target: charter
promotion_threshold:
  retro_citations: 2
status: active
---
In `grep`, `-rn` means recursive + line numbers. In **ripgrep it means `--replace n`** — `-r` takes an argument, so it swallows the `n` as the replacement string. ripgrep is recursive by default and has no `-r`-for-recursive, so the muscle memory transfers silently and wrongly.

**What you get:** every match is rewritten to the replacement text, and line numbers disappear (the `-n` was consumed as the value, not parsed as a flag). Reproduced against `noorinalabs-deploy`:

```sh
$ rg -n  --no-ignore "ssh_public_key" terraform/hetzner/modules/hetzner-vps/variables.tf
33:variable "deploy_ssh_public_key_path" {
39:variable "root_ssh_public_key_path" {

$ rg -rn --no-ignore "ssh_public_key" terraform/hetzner/modules/hetzner-vps/variables.tf
variable "deploy_n_path" {
variable "root_n_path" {
```

**Why this is worse than a normal typo:** the corrupted output is *syntactically plausible*. `deploy_n_path` reads like a real Terraform variable — nothing looks broken, nothing errors, exit status is 0. The failure mode is not "my search failed", it is "my search returned confident, well-formed, wrong data". Sibling to [[feedback_silent_zero_is_not_a_measurement]]: there the instrument returns nothing and you read it as absence; here it returns something and you read it as source.

**Real cost (main#1139, PR #1153):** I used `rg -rn` to verify a child repo's Terraform, transcribed `deploy_n_path` / `root_n_path` into `reference_ssh_topology.md` as literal `main.tf` source, **and stamped the note `last_verified`**. The note was being corrected precisely because it had been giving operators a harmful instruction — so a stale note was replaced by a differently-wrong note carrying a fresh verification stamp. Weronika-Rev-1153 caught it by re-resolving the identifiers against deploy's `origin/main` contents API; an exhaustive `rg --no-ignore 'deploy_n_path|root_n_path'` over the whole deploy repo exits 1 with zero hits. `.claude/memory/**` is excluded from the markdown/link/spell linters, so all 21 CI checks were green over the wrong identifiers — **green CI is near-zero evidence on a memory-content diff**.

**How to apply:**

1. **Never write `rg -rn`.** For line numbers use `rg -n`; ripgrep recurses on its own. If you want `-r`, you want it deliberately and with an explicit replacement (`rg --replace '$1' …`).
2. **Never transcribe an identifier out of a search hit you have not eyeballed against the raw line.** When a name is load-bearing (a variable, a symbol, a flag going into a doc or memory), re-read it with a plain `rg -n` — or `sed -n '33p' <file>` — before writing it down.
3. **Falsify the identifier, don't confirm it.** The cheap check is the negative one: `rg --no-ignore '<name-you-wrote>' <repo>` should return **hits**. Exit 1 means you invented it. This is a two-second check that would have caught the whole defect.
4. **Any `last_verified` stamp is a claim.** Stamping a note whose facts came from a mangled instrument launders corrupted data into the store as verified truth. Stamp only what you re-read at the source.

**Recurrence 2026-09-13 (#1550) — two agents, independently, inside one hour; this note did not fire for either.** Same shape, new surface: `rg -rn 'validate_vps_host' .claude/team/charter/hooks.md` printed ``## Hook 10: Validate VPS_HOST (`n.py`)`` against a real line reading ``(`validate_vps_host.py`)``. One agent nearly filed that as a charter-documentation defect — a **fabricated** finding, with the file path and heading correct and only the quoted identifier invented. The other (Aino, mid `#1550` judge pass) hit it repeatedly, noticed the output was odd, tested it on a short file with `rg -n` (which is correct and therefore *cleared* the suspicion), and concluded the harness was redacting matched text — i.e. **explained it away as a display artifact, which is exactly the failure this note and [[feedback_short_flag_consumes_next_token]] both name in writing.** The control was contaminated in the [[feedback_enforcement_hierarchy]] sense: a check that agrees with you for a reason unrelated to the hypothesis.

Two things this adds to the rule above:

- **Only quoted text is corrupted; which files/lines matched is still correct.** `-r` rewrites the *rendering* of a match, not the matching. So a `-rn` sweep used to answer "does this string appear anywhere?" gives a **trustworthy yes/no** while giving an **untrustworthy quotation**. That asymmetry is why the output looks half-right and survives scrutiny — and why every verdict in #1550 that rested on presence/absence stood on re-verification, while every one resting on a quotation had to be re-read with `sed`/`awk`.
- **Tier escalation is now overdue, not optional.** Three-plus instances of a memory-tier rule that is correct, recently `last_verified`, and still not recognised in the moment is the [[feedback_enforcement_hierarchy]] trigger (*"Knowing a rule does not help if you cannot recognise that you are inside it"*). The follow-up both notes already carry — `docs/TOOLCHAIN.md` § Text search + `ontology/conventions.md` — remains unactioned, and the cheap hook exists in outline: `block_bare_grep.py` already intercepts this exact tool class and could warn on a `-r` whose value is a bare `[a-z]` token.
