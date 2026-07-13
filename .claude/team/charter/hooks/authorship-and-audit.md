# Hooks — Authorship, Sync & Audit

> Part of the [hooks charter index](../hooks.md) — re-shelved from `charter/hooks.md` for section-level loading (#963). Rules unchanged.

## Hook Authorship Requirements <!-- promotion-target: none -->
Every new hook in `.claude/hooks/` must meet these requirements **at the time it is merged**. Partial compliance is a moderate feedback event.

### 1. Input-language specification

The hook's module docstring (top of file) must include an explicit **Input Language** section defining:

- **Fires on:** which PreToolUse event (Bash, Agent, Edit, Write, etc.)
- **Matches:** the exact command / input shape the hook acts on, expressed as a regex or grammar fragment
- **Does NOT match:** inputs that superficially look similar but are intentionally out of scope (with examples)
- **Flag pass-through:** which CLI flags (e.g., `--repo`, `--admin`) are extracted from the matched command and how

Example (from `validate_pr_ci_status.py`):
```python
"""
Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh pr merge {N} [--repo {OWNER/REPO}] [--squash|--merge|--rebase] [--admin] [--auto]
  Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr create, git merge, git pull
  Flag pass-through:
    --repo   → overrides cwd-resolved repo when querying gh pr view
    --admin  → short-circuits (emergency override, allows merge)
    --auto   → allows pending checks (GitHub auto-merge)
"""
```

**Why:** Phase 2 Wave 8 surfaced six hook substring/regex bugs (#113 validate_labels cwd, #114 auto_set_env_test test-string false-positives, #118 validate_branch_freshness cwd, #123 validate_pr_review RequestOrReplied-Requested false-positive, ontology-tracker /tmp ghost entries, validate_labels default-limit). Root cause was hooks written liberally without an explicit spec of what they match vs. don't. An input-language docstring forces the author to enumerate the negative space before shipping.

### 2. Charter entry in `charter/hooks.md`

Every new hook must have a numbered entry in this file with: What it automates, Augments (which charter section), Manual steps remaining, Emergency override. No hook ships without a charter entry.

### 3. Test coverage for negative matches

The hook's test suite (or docstring-embedded manual verification) must include at least one input that **looks like a match but is intentionally excluded** — to guard against the substring-bug pattern. Example: a `validate_pr_merge` hook must verify it does NOT fire on `gh pr list`.

### 4. Dispatcher registration (not settings.json)

New Bash hooks must register in `dispatcher.py`'s `_BASH_HOOKS` list, not as a separate `settings.json` entry. See `charter/hooks.md` § Hook Dispatcher Consolidation (Hook 7 pattern).

### 5. Parser-Fixture Coverage Requirements

Every hook with input parsing MUST have test fixtures covering all known input shapes. New input shapes discovered in production (e.g., a `head_ref` shape the parser doesn't recognize, a quoting style that trips shlex, a YAML edge case) require fixture-add backport BEFORE the bug-fix PR can merge — the fixture pinning the new shape lands together with the parser fix in the same commit.

**Rationale:** P3W6 surfaced 4 hook parser bugs in a single wave (#285 /wave-kickoff Step 1 EXISTING_SHA captures 404 body; #287 validate_commit_identity false-blocks backslash-line-continuation; #289 validate_workflow_paths_coverage misparses bare `on.pull_request:`; #294 validate_pr_review skips reviewer counting on `deployments/*/wave-*` heads). All four are parser bugs in production hooks discovered AT runtime when an unanticipated input shape arrives. Fixture-with-fix discipline pins the new shape so future regressions surface in CI.

**Acceptance:** PR introducing a parser-bug fix MUST include the new fixture in the same commit. CI (or hook authors during review) flags PRs that change parser logic without an accompanying fixture addition.

**Dispatcher-style children (no committed `.claude/hooks/`):** Children that delegate all hook execution to the parent canonical via `settings.json` are exempt from per-child fixture requirements. Coverage obligations are fulfilled by the parent's test suite. A child is classified as dispatcher-style when `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1` returns 0 entries under `.claude/hooks/`. Design-system and landing-page (post-W5) are the canonical exemplars.

#### 5a. Mandatory Test Coverage for PreToolUse Segment Parsers

This is a **specialization of §5** for the narrow class of hooks that split a bash command on shell separators into segments (e.g. `auto_set_env_test.py` splits on `&&`/`||`/`;`/`|`/`\n` to check each test-bearing segment independently). Any such **segment-parser** hook MUST carry test coverage for ALL SIX separator classes — not just the ones the original feature happened to exercise.

| Class | Example | Test-class-name convention |
|---|---|---|
| Standard separators | `cmd1 && cmd2`, `cmd1 \|\| cmd2`, `cmd1; cmd2`, `cmd1 \| cmd2` | `StandardSeparatorTests` |
| Newline | `cmd1\ncmd2` (multi-line script) | `NewlineSeparatorTests` |
| Subshell | `(cmd1; cmd2)` | `SubshellTests` |
| Control-flow body | `for x in ...; do cmd; done` | `ControlFlowBodyTests` |
| Line-continuation | `cmd \`<br>`  arg` (backslash-newline) | `LineContinuationTests` |
| Quoted regions | `'sep && inside'`, `"sep \| inside"` | `QuotedRegionTests` |

Each class MUST include at minimum:

- One **allow** case — the segment correctly receives the env-block / hook-condition and the hook passes.
- One **block-with-correctly-targeted-suggestion** case — the segment is missing the env / hook-condition, the hook blocks, AND the suggestion lands on the right token (not a neighbouring segment). For the control-flow class where a clean splice is impossible, the block case asserts the HARD-BLOCK diagnostic path instead (per §Hook 4 / #478). Because that hook deliberately does NOT peek into the loop body for an existing env-block (even env-already-inside hard-blocks, so the operator edits manually), the control-flow "allow" case is a control-flow construct that carries no test runner at all — the hook correctly does not fire.

The canonical reference implementation is `.claude/hooks/tests/test_auto_set_env_test.py`. The convention-named classes there carry a `# segment-class: <Standard|Newline|Subshell|ControlFlowBody|LineContinuation|QuotedRegion>` marker comment so a future grep-based CI gate (out of scope here, follow-up) can assert all six are present.

**Why charter, not a code-review checklist:** a checklist is opt-in and decays (`feedback_enforcement_hierarchy`: "Charter rules without enforcement decay"). The `auto_set_env_test` hook shipped quote-aware (#478) and control-flow-aware detection but had NO coverage for newline-as-separator; the gap surfaced as repeated operator friction ("I've seen this error a few times") before #537 was filed and fixed in #538. Encoding the six-class matrix as a contract makes the NEXT segment-parser hook add all six from the start, rather than discovering each gap at runtime.

**Spawn-brief line for hook PRs:** reviewer-class and implementer-class spawn briefs for any segment-parser hook PR MUST include the line: *"ensure all 6 segment-class tests present (per `hooks.md § Mandatory Test Coverage for PreToolUse Segment Parsers`)."*

**Out of scope (follow-ups):** a grep-based CI gate asserting the six convention class-names; backfilling the six classes for *other* existing hooks (they have at least partial coverage already; a separate sweep); coverage requirements for non-segment-parser PreToolUse hooks (different signal pattern — §3 negative-match coverage already governs those).

<!-- Promoted from memory: feedback_safety_direction_over_ux_friction (control-flow safety-direction precedent #478) — codifies P3W12 retro § Proposed Process Changes #2 (issue #543), newline precedent #537/#538. Charter-tier only (no hook); CI-gate enforcement is a deferred follow-up. -->

### 6. Promotion Provenance Phrasing

Every hook's charter entry includes a provenance block describing where the hook came from. The `/promotion-audit` skill's `find_already_promoted` parser scans these blocks to decide which memories / charter rules / skill patterns have already landed as hooks. Ambiguous phrasing defeats the parser (false-negatives produce noisy AUTO classifications; false-positives produce noisy ALREADY-PROMOTED classifications). Three required parts:

**Backward claim (required):** a single sentence declaring backward provenance — what prior tier (memory / charter / skill / pattern) this hook was promoted from. Example:

> Promoted from memory `feedback_enforcement_hierarchy.md` via charter § Ontology Librarian Rule (PR #153).

Every hook MUST have exactly one backward-claim sentence. The parser's `_PROVENANCE_RE` and `_HTML_COMMENT_PROMOTED_RE` recognizers extract memory / charter / skill references from this sentence, so it MUST cite the source artifact by filename (memories: `feedback_X.md` or unsuffixed `feedback_X`; skills: `/skill-name`; charter rules: `CLAUDE.md § X` or `charter/X.md § Y`).

**Forward references (optional, must be in a separate paragraph):** if the hook's charter entry mentions sibling hooks, future artifacts, or design narrative, that narrative MUST live in its OWN paragraph — never co-located with the backward-claim sentence. Example forward reference:

> Worked example referenced by the future `/promotion-audit` skill design.

**Why separate paragraphs:** `find_already_promoted`'s `_FORWARD_REFERENCE_MARKERS` filter (`future`, `planned`, `design`, `upcoming`, `referenced by`, `will reference`, `proposed`, `TBD`) excludes slash-command hits that sit within ~60 chars of these markers. Forward-reference narrative mixed into the backward-claim sentence makes that filter trip on the backward citation too — turning a real promotion record invisible. Keeping the two concerns in separate paragraphs is the simplest discipline that preserves both meanings.

**Recognized parse keys:** the literal tokens `/promotion-audit` scans for. Author your provenance block with one of these as the opener so the parser finds it:

- `**Promotion provenance:**` — block-style header; the parser's `_PROVENANCE_RE` greedy-matches until the next blank line / heading. Used by hooks.md per-hook entries (e.g. Hook 15).
- `Promoted from` — opening token recognized inline; works inside either the block-style entry or a standalone sentence.
- `<!-- Promoted from memory: X -->` — HTML-comment marker form codified in #283 / #393. Used for charter-tier-only promotions (no corresponding hook). The parser's `_HTML_COMMENT_PROMOTED_RE` (DOTALL) captures the body up to `-->`, so trailing context (date, retro citation, rationale) is included in the regex sweep.

**Rationale:** PR #155 added the reactive `_FORWARD_REFERENCE_MARKERS` filter to handle Hook 15's own provenance block — which had narrative referencing a future skill mixed in with the backward citation. The filter is the runtime safety net; this guidance is the preempt-at-author-time fix that reduces future filter-edits. Sibling of #393 (HTML-marker convention) — this section catalogues the parse keys; the authoritative shape-selection rule (when to use HTML-comment vs. bold-prose) lives at [`charter/skills.md` § Promotion Pipeline Marker Convention](../skills.md#promotion-pipeline-marker-convention).

### 7. gh-command Parser Invariant (flag-value scoping + ambient-repo resolution)

**Any hook that parses a `gh` command (`gh issue` / `gh pr` / `gh workflow` / `gh api`) MUST:**

1. **Scope label/repo extraction to the actual flag VALUES** — the tokens that follow `--label`/`-l`/`--add-label`/`--remove-label`/`--repo`/`-R` — via the shared tokenizer (`_shell_parse.walk_flag_values` / `first_flag_value`, `_repo_flag_parse.extract_repo`, or the domain-shape `_wave_label_parse` helpers). It MUST NOT regex flag-shaped or label-shaped strings out of arbitrary command text, and MUST NOT reimplement shell tokenization privately (`shlex.split(...)` in the hook body). Routing through `_shell_parse.tokenize` is mandatory because it carries fixes a private copy silently loses — line-continuation normalization (#287), heredoc stripping, and segment splitting — and because a private regex over the raw command leaks label-shaped tokens out of `--body`/`--body-file` content (the #661 false-block).

2. **Resolve the flag-omitted (ambient git-context) case** — a `gh issue create/edit` run *inside* the target repo carries no `--repo` and relies on gh's ambient resolution. The hook MUST recover the repo from the invocation cwd's `origin` via `_shell_parse.resolve_repo_short_name` (mirroring gh), or log a `skip_no_repo_context`-style diagnostic and fail-open — **never silently drop the command** (the #650 EDIT-path drop) and never fall through to a malformed default repo (the #659 CREATE-path twin).

**Backing class:** #650 (EDIT path required `--repo`, dropped in-repo label edits — fixed PR #658), #659 (CREATE path same gate — fixed PR, commit `9ab5c37`), #661 (`validate_labels` matched a label-shaped token in `--body` — fixed `9ab5c37`), `validate_wave_label_evidence` (private `shlex`/flag-walker reimplementation + empty-default `noorinalabs/` slug — migrated under #663), and `warn_ghcr_image` (ad-hoc `re.search(r"-R\s+...")` extractor on `gh workflow run`, no ambient resolution — migrated under #663 wave-16, extending the invariant to the `gh workflow`/`gh api` class). `block_gh_pr_review` likewise dropped its private `re.split` segmenter for the shared tokenizer + heredoc strip (wave-16). Lineage: cwd-anchor #144/#521 → multi-cmd #455 → #650 → #659/#661 → workflow/api class (#663 wave-16).

**Machine-enforcement:** `.claude/hooks/tests/test_gh_command_parser_invariant.py` is the gate (runs in the pytest suite CI already mirrors in `.pre-commit-config.yaml`, so no new CI job / no `ci.yml` edit). It classifies every top-level hook that reads the incoming command and matches a `gh issue`/`gh pr`/`gh workflow`/`gh api` shape, then asserts each (A) does not call `shlex.split`/`shlex.shlex` directly and (C) carries no ad-hoc flag-value-capturing regex. The three sanctioned shared parsers (`_shell_parse`, `_wave_label_parse`, `_repo_flag_parse`) are exempt — they ARE the tokenizer/flag-walker/ambient-resolver. **Scope** is the full gh-command value-flag parser class: `gh issue`/`gh pr` (original) PLUS `gh workflow`/`gh api`, which #663 wave-16 migrated onto the shared parser and folded into enforcement — closing the deferred follow-up the original gate had enumerated.

<!-- Promoted from charter feedback `feedback_enforcement_hierarchy.md` (hook > skill > charter) and the convergent #650/#659/#661 class — owner-adopted P4W7 retro Proposed Change #1 (2026-06-13), actioned in P5 via issue #663 (charter rule + pytest gate for the `gh issue`/`gh pr` class), then extended to the `gh workflow`/`gh api` class in P6 wave-16 (#663). The gh-command analogue of the deferred grep-gate noted in §5a. -->

**Enforcement:** The Standards & Quality Lead (Aino) verifies these requirements during hook PR review. A hook missing any of the seven requirements must not be approved. For segment-parser hooks specifically, §5a's six-class test matrix is part of that verification; for gh-command parsers (`gh issue`/`gh pr`/`gh workflow`/`gh api`), §7's flag-value-scoping + ambient-repo resolution (and its gate) are part of it.

## Hook Sync Across Child Repos <!-- promotion-target: none -->

> The org-wide artifact ownership + execution-location matrix (hooks, skills, charter, memory, ontology, settings — meta vs child) is canonicalized in [`charter/artifact-ownership.md`](../artifact-ownership.md) (#328). This section remains the authoritative detail for the **hook** class specifically; the matrix points back here.

Shared hooks live in `noorinalabs-main/.claude/hooks/` (the parent repo's hooks tree). Child repos consume them via **parent-canonical paths** — their own `.claude/settings.json` registers each hook by absolute path into the parent's hooks tree, e.g.:

```jsonc
{
  "matcher": "Bash",
  "hooks": [{
    "type": "command",
    "command": "python3 /home/parameterization/code/noorinalabs-main/.claude/hooks/dispatcher.py",
    "timeout": 30
  }]
}
```

**The parent's `.claude/hooks/` is the single source of truth for shared hook code.** Child repos do NOT keep local `.py` copies of shared hooks; they reference the parent's files by path. This makes a new shared hook a configuration change in each child's `settings.json`, not a code-fan-out across child repos — eliminating the drift risk that surfaced in P2W9 (Hook 14 was registered in the parent for ~2 weeks before #194 surfaced no child had it).

### Required pattern

For every shared hook (i.e., a hook that exists at `noorinalabs-main/.claude/hooks/<name>.py` and applies to multiple repos):

1. Hook source code lives at `noorinalabs-main/.claude/hooks/<name>.py` ONLY. No copies in child repos.
2. Each child repo's `.claude/settings.json` registers the hook under the appropriate matcher with a `command` of `python3 /home/parameterization/code/noorinalabs-main/.claude/hooks/<name>.py` (or the dispatcher path for Bash hooks).
3. Child repos do NOT have their own `annunaki_log.py`, `_shell_parse.py`, `dispatcher.py`, or other shared support files. They reference the parent's copies.

### Anti-pattern: copy-resident hooks

Do NOT copy `.py` hook files into a child repo's `.claude/hooks/` and register them via relative paths. This is the **copy-resident anti-pattern**:

- Forces a per-repo PR to ship every shared-hook update (versus a single line in each child's `settings.json`).
- Two distinct mental models in flight whenever some children are copy-resident and others are symlink-style.
- Drift is permanent — no compile-time check that all copies are in sync with the parent's source of truth.

If you find a child repo using copy-resident hooks during routine work, file a tracking issue and align on the next hook-sync wave's plan rather than mixing the cleanup into an unrelated PR.

### Anti-pattern: empty child config

A child repo that participates in hook-gated workflows (commits, PRs, merges) MUST have a `.claude/settings.json` registering at least the parent dispatcher and matcher hooks relevant to that repo's surface (Edit/Write for sources, SendMessage for cross-repo coordination, etc.). An **empty child config** is a silent gap — hooks the parent enforces simply don't fire in that repo. Audit during wave-kickoff and file `tech-debt` if any in-scope repo is empty.

### Reviewer enforcement

When a PR adds or modifies a child repo's `.claude/settings.json`, reviewers verify:
- Each hook entry uses an absolute path into `noorinalabs-main/.claude/hooks/`, not a relative path.
- No new `.py` hook files are added to the child's `.claude/hooks/` (the dir should be empty or contain only child-local hooks specific to that repo's surface — none currently exist).
- Coverage matches the parent's matcher list for the equivalent surface (e.g., a child with code-editing tools should register PreToolUse Edit/Write hooks that the parent registers for the same purposes).

### Caveats acknowledged

- Symlink-style is fragile to parent-dir layout changes — but the org-canonical workstation layout (`/home/parameterization/code/noorinalabs-main/...`) has been stable since project inception.
- Symlink-style breaks when a child repo is cloned standalone OUTSIDE the parent. Hooks fail to invoke (no matching path); the harness gracefully falls through (no hook = allow). Document this in any per-child-repo CLAUDE.md that anticipates standalone cloning.
- Hook updates require a child-side `settings.json` edit when hook count changes (new hook added; matcher consolidation per § Dispatcher Consolidation Policy). This is one line per child — significantly cheaper than the per-repo PR cost the copy-resident pattern imposes.

### Promotion provenance

Surfaced during execution of [#194](https://github.com/noorinalabs/noorinalabs-main/issues/194) (Hook 14 sync to 7 child repos) — Aino's survey found 3 copy-resident, 3 symlink-style, 2 empty across the 7 child repos. Owner-greenlit the canonicalization 2026-04-27. Phase 1 (this section, charter codification) lands in P3W4. Phase 2 (per-child-repo sweep migrating the 3 copy-resident repos to symlink-style + scaffolding any empty repos) is tracked separately for P3W5. See [#214](https://github.com/noorinalabs/noorinalabs-main/issues/214).

---

## Hook Audit Protocol

When auditing a repo's hook ownership status (hook-owning vs. dispatcher-style):

1. Fetch the committed tree:
   ```
   gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1 \
     --jq '[.tree[].path | select(startswith(".claude/hooks/"))]'
   ```
2. Classification: if the result is empty (`[]`), the repo is dispatcher-style. If non-empty, it is hook-owning.
3. Filesystem enumeration (SSH, `ls`, `find`) is NOT a valid substitute — it includes untracked files, worktree artifacts, and gitignored content that are invisible to git.

**Rationale:** P3W7 produced 3 repo misclassifications from a single root cause: auditors enumerated working-directory files instead of querying the committed git tree. Misclassified repos: design-system, user-service, data-acquisition — all initially called "stale-mirror hook-owning" but confirmed dispatcher-style via committed-tree inspection. The correct method is one API call away.

**Enforcement:** Any audit-finding comment that asserts a repo's classification must cite the `gh api .../git/trees` invocation it ran (or the equivalent `gh api .../contents/.claude/hooks?ref=<sha>` form). Reviewers reject classification claims sourced from `ls`, `find`, SSH, or local checkout.
