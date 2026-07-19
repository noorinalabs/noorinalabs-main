# `.claude/agents/` — per-role model tiering

Each `*.md` here is an agent definition (`name`, `description`, `model`, `tools`,
optional `skills`) that sets a **default model tier by task class** so subagents
stop inheriting the orchestrator's Opus tier onto mechanical work. The tier
assignments are authored to match, exactly, the charter table in
[`.claude/team/charter/agents/orchestration-model.md § Model-tier selection when
spawning`](../team/charter/agents/orchestration-model.md). Task-complexity
routing is a reported 30–50% cost reduction at equal-or-better quality
(token-efficiency audit main#986, Part 6); running every subagent at Opus leaves
that on the table. Created for main#1015.

> These files set the **default** tier for a spawn of that `name`. The
> orchestrator still sets `model:` explicitly on every `Agent` spawn per the
> charter checklist — a call-site `model:` override wins, which is how the
> built-in `Explore` agent (SDK-controlled model) gets tiered. Whether the
> harness honors these files as spawn defaults has NOT been independently
> verified here; they are authored to the charter spec.

## Tier assignments

| Agent file | Tier | Class |
|---|---|---|
| `ontology-librarian.md` | Haiku | read-only reference lookup |
| `search.md` | Haiku | read-only search / fan-out |
| `wave-audit.md` | Haiku | mechanical issue reconciliation |
| `close-stale.md` | Haiku | mechanical issue reconciliation |
| `board-audit.md` | Haiku | mechanical board/label reconciliation |
| `ruff-format.md` | Haiku | mechanical lint/format fix |
| `pr-reviewer.md` | Sonnet | routine charter-format review (never Haiku) |
| `tpm.md` | Sonnet | coordinator-class |
| `release-coordinator.md` | Sonnet | coordinator-class |
| `infrastructure-manager.md` | Sonnet | per-repo Manager coordinator |
| `sre-engineer.md` | Sonnet | substantive implementation |
| `observability-engineer.md` | Sonnet | substantive implementation |
| `platform-architect.md` | Sonnet | substantive design (rounds up to Opus for cross-repo architecture) |
| `program-director.md` | Opus | orchestration / cross-repo planning |
| `standards-lead.md` | Opus | hook/gate/charter design (fail-open risk) |
| `security-engineer.md` | Opus | security / threat / design |
| `merge-gate-reviewer.md` | Opus | the ≥1-Opus merge-gate review |

## The ≥1-Opus merge-gate safeguard

**Model tiering must NEVER drop a PR to Sonnet-only review.** Every PR carries at
least one `merge-gate-reviewer` review at `model: opus` in addition to any
Sonnet-tier `pr-reviewer`. A review is a correctness judgment, not a lookup
(P9W25 lesson: genuine engine-running reviews catch defects a string-only pass
misses), so:

- `pr-reviewer` is **Sonnet minimum — never Haiku**.
- `merge-gate-reviewer` is **Opus**, and it is the last line of defense that
  keeps "the reviewer isn't immune" discipline on the model that is hardest to
  fool, even when the second reviewer is Sonnet.

This is the charter's **asymmetric-risk "round UP a tier" rule** applied to
review: a hard task misrouted to a cheaper tier fails *silently*
(plausible-but-wrong output, not an error), and the downside is one-sided, so any
spawn whose output gates a merge, a data write, or a prod change biases upward.
When uncertain, round up. See
[`orchestration-model.md § Model-tier selection when spawning`](../team/charter/agents/orchestration-model.md)
("Asymmetric-risk rule").

## Tools scoping

Read-only / reference / reviewer roles
(`ontology-librarian`, `search`, `wave-audit`, `close-stale`, `board-audit`,
`pr-reviewer`, `merge-gate-reviewer`) are **not** granted `Edit`/`Write` — they
report or comment, they do not mutate tracked files. `ruff-format` gets `Edit`
(not `Write`) because a formatting fix edits existing files only. Coordinator and
implementer roles get the full `Write`/`Edit` + `Task*` + worktree tool set.
