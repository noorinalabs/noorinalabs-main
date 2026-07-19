# Session-Hygiene Playbook & Lean Briefs (#1020)

> **What this file governs.** How to keep a long-lived session cheap — the re-billed
> context tail, cache-prefix discipline, tool-result clearing — and how to keep a
> spawn brief lean (section-extract over whole-file paste; signatures-only code
> skeletons). The `warn_oversized_brief.py` advisory hook and the `make skeleton`
> target are the machine backstops for the lean-brief half; the rest is discipline.

## Lean Section-Extract Briefs

**Pass a subagent only the charter/CLAUDE.md *section* its task needs — never the whole
file.** A brief that pastes full `CLAUDE.md` + a whole charter sub-document into every
spawn re-pays for context the role will never use; across the Opus/Sonnet subagents a
cross-repo wave spawns, that is the single largest per-token waste. The rule is standing,
not per-wave:

- **Extract the section, cite the path.** Quote (or tightly paraphrase) just the relevant
  section, then point the agent at the file+anchor for the rest — e.g. a reviewer gets a
  [`charter/pull-requests/reviews.md`](../pull-requests/reviews.md) pointer, not the whole
  PR charter. An agent can always `Read` the deeper file on demand; it should not carry it
  by default.
- **The PR charter is pre-split for exactly this** — [`charter/pull-requests.md`](../pull-requests.md)
  is a thin index over `reviews.md` / `authoring.md` / `wave-merge.md` / `ci-gates.md` /
  `evidence-standards.md` / `acceptance-scope.md`. Route a role to the one sub-file it needs.
- **Identity/branching/commit rules live in the roster file and the charter** — a brief
  points at them (`.claude/team/roster/<member>.md`, `charter.md` § Commit Identity), it
  does not re-transcribe them.
- **Tool scope is declared, not briefed.** The `.claude/agents/<role>.md` frontmatter
  `tools:` list restricts a role to the tools it uses (an allowlist), so a text-only role
  loads no unused tool schemas — the brief need not re-list them.

**Advisory backstop.** [`warn_oversized_brief.py`](../../../hooks/warn_oversized_brief.py) is
a non-blocking PreToolUse advisory on `Agent` spawns (registered in the `Agent` matcher of
`.claude/settings.json`): it warns when a single brief embeds a very large block of
verbatim `CLAUDE.md` / `charter.md` / `charter/**/*.md` prose, nudging toward a
section-extract + pointer. It never blocks a spawn (fail-open by design — an over-long
brief is a cost smell, not a correctness fault).

### Repomix skeleton packing for a CODE subtree

The same "extract, don't paste the whole thing" rule applies to code, not just charter
prose. When a spawn genuinely needs the *shape* of a subtree wider than the ontology's own
`path:line` pointers (orientation across many files, not one symbol lookup — the ontology
stays the tool for that), pack a Tree-sitter **skeleton** (signatures kept, bodies
stripped, roughly halving to two-thirds off raw token count) instead of pasting whole
files:

```
make skeleton DIR=.claude/lib/ontology_gen INCLUDE='*.py' OUT=/tmp/skeleton.xml
```

Paste the output file's contents into the brief. `DIR` narrows to the subtree the ontology
already selected as relevant; `INCLUDE` narrows further to a glob within it when the whole
subtree is still too broad. The ontology **selects** which files matter; this
**compresses** them for the brief — the two compose, they don't compete.

**Dependency note.** `make skeleton` shells out to `npx --yes repomix` (Tree-sitter
compression), which fetches repomix on demand — it needs Node's `npx` on PATH but adds
nothing to the repo. If `npx` is absent the target fails fast with a clear message; install
Node, or fall back to a hand-picked section extract.

## Session-Hygiene Playbook

**The API is stateless: every turn re-sends — and re-bills — the entire context tail.**
A long-lived session is not "free after the first turn"; each subsequent turn re-pays for
every token still in context. The four disciplines below keep that re-billed tail small.

### The cost mechanics (why this pays)

Grounded in Opus 4.8 pricing ($5 / Mtok input, $25 / Mtok output) and the caching
economics (verified against the `claude-api` skill — `shared/prompt-caching.md`):

- **Output costs 5× input, per token** ($25 vs $5). Output is written once and is small;
  the input tail is re-sent every turn and grows without bound. On a long session the
  **re-billed input tail — not the output — is the dominant cost.**
- **A cache *read* costs ≈ 0.1× input; a cache *write* costs 1.25× input** (5-minute TTL;
  2× at 1-hour). So a token that stays in a stable, cached prefix re-bills at **one-tenth**
  the price of the same token in the volatile (uncached) tail. Keeping the prefix cacheable
  is a 10× lever on the re-billed tail.
- **`usage.cache_read_input_tokens` + `cache_creation_input_tokens` + `input_tokens` = the
  full prompt.** `input_tokens` is only the *uncached remainder* — read all three, not the
  one field, to see the true size (and to prove caching is working; see § Verifying below).

### 1. `/clear` at every wave/task boundary — the biggest single-session saving

When one task ends and an unrelated one begins, **`/clear`** — do not let the new work
inherit a 100K-token tail it will never reference but will re-bill on every turn. A wave
boundary, a task pickup that shares nothing with the last, a context switch from
implementing to a long review of unrelated code: all are `/clear` points. The old tail
carries zero value into the new task and pure cost. This is the largest lever because it
drops the *entire* accumulated tail at once, not a slice of it.

### 2. Proactive `/compact` at ~60% — don't ride to auto-compact at 95%

Auto-compaction fires only when context is nearly full (~95%), by which point you have
already re-billed the bloated tail across many turns. **`/compact` proactively at ~60%**
so the summary replaces the tail *before* it has been re-paid dozens of times. Compaction
summarizes (unlike `/clear`, which drops), so it is the right tool when the current task
must continue but its history has grown heavy. **Afterward, verify load-bearing state
survived the summary** — an open PR number, a branch name, a not-yet-pushed SHA, a
half-applied migration. A summary that silently drops a load-bearing fact is worse than the
tail it replaced; re-state the fact after compacting.

### 3. Cache-prefix discipline — stable content to the FRONT, volatile to the BACK

Caching is a **prefix match**: render order is `tools → system → messages`, and **one
changed byte anywhere in the prefix invalidates every cache entry after it** (drops those
tokens from 0.1× back to 1×). Two rules follow:

- **Keep the stable prefix byte-identical mid-session.** `CLAUDE.md`, the `@import`-ed
  `MEMORY.md`, the charter text a session loads, and the tool definitions sit at the front
  — do not mutate them mid-session (a reworded `CLAUDE.md`, an added/removed/reordered tool
  busts the cache for everything after it). The Opus 4.8 minimum cacheable prefix is **4096
  tokens**, so the prefix has to be both stable *and* substantial to cache at all.
- **Push volatile content to the back.** Live git status, the shared task list, freshly
  recalled memory, timestamps — anything that changes per turn — belongs *after* the stable
  content, never interpolated into the front. This is exactly why the wave/status digest is
  read on demand (`wave_status.py digest`) rather than embedded in `MEMORY.md`, and why the
  volatile handoff summary lives in the gitignored `session_handoff.md`, not in the
  always-loaded index (see [[project_ontology_system]] and CLAUDE.md § Project Memory).

### 4. Tool-result clearing — `clear_tool_uses_20250919` where the harness exposes it

Stale tool results (file dumps, CI logs, `git archive` extractions) linger in context and
re-bill every turn. Where the harness exposes context editing
(`context_management.edits` with `clear_tool_uses_20250919`, beta
`context-management-2025-06-27`), clear them — but tune it:

- **`clear_at_least ≥ 5000`.** Each clear *rewrites* the prefix boundary, and a rewrite is
  a cache **write** (1.25× input). Clearing a trickle of tokens costs more in cache-write
  churn than it saves; batch the clears so each one frees a worthwhile block.
- **`exclude_tools` for results you will re-reference.** A file you are actively editing or
  a diff you keep citing should not be cleared out from under you — exclude it, or you pay
  to re-read it.

### Verifying the cache-prefix claim

The claim "the stable prefix actually caches" is checked against
`usage.cache_read_input_tokens`, the same field the `claude-api` skill prescribes:

1. **Live signal.** Across turns whose prefix (`CLAUDE.md` + `MEMORY.md` + charter + tools)
   was *not* touched, `cache_read_input_tokens` must be **non-zero and roughly the prefix
   size** while `input_tokens` stays small (the uncached tail only). Zero cache reads across
   an unchanged-prefix stretch = a silent invalidator busting the prefix — find the byte
   that changed (a `datetime.now()`-style header, a reordered tool, a reworded `CLAUDE.md`).
2. **Mid-session mutation is the anti-signal.** If any wave edits `CLAUDE.md`, `MEMORY.md`,
   or the charter *and continues the same session*, expect one turn of elevated
   `cache_creation_input_tokens` (the prefix was rewritten) — that is the cache-bust the
   discipline exists to avoid, made visible. Prefer editing those files at a `/clear`
   boundary, not mid-task.

## Web-Fetch Discipline: ask for the fact, not "summarize the page"

External fetches are the other major token sink alongside code-retrieval — a
"summarize this page" `WebFetch` dumps raw HTML/prose into context that then gets re-billed
on every subsequent turn (see § Session-Hygiene Playbook above for why the re-billed tail
dominates cost).

`WebFetch(url, prompt)` runs the fetched content through a small model scoped to `prompt`
*before* it reaches the calling agent's context — a narrow prompt ("what is the current LTS
version of Node.js per this page?") returns a sentence; a broad one ("summarize this page")
returns paragraphs, most of which the task never uses. **Default to the narrow form** — ask
the specific question the task needs answered. Widen only when the task genuinely needs the
whole document, not as the default shape of the call. A web fact worth re-reading across
sessions belongs in a `reference` memory (`capture_reference.py`), not re-fetched every
session (CLAUDE.md § Durable web-fetch capture).
