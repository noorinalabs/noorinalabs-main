---
name: user_steven
description: Project owner preferences, working style, enforcement expectations, and role context
type: user
promotion_target: none
status: active
---

- Project owner of Noorina Labs, manages all repos
- Git identity: Steven French / parameterization@gmail.com
- Prefers autonomous execution — don't ask permission for things the charter already defines (e.g., end-of-wave process should auto-trigger)
- Expects charter compliance — will call out when review gates, peer reviews, retros, or process steps are skipped
- **Enforcement priority: hooks > skills > charter rules** — Steven repeatedly asks "how do we make sure this happens every time?" Prefers hard technical enforcement over behavioral reminders. If a process step keeps getting skipped, build a hook to block the violation.
- Expects retros, feedback log updates, and trust matrix updates at wave end — explicitly flagged on 2026-04-08 that these were being skipped. Expects the orchestrator to send him the updates.
- Wants one team per repo with unique personas, repo-specific org charts sized to the repo's purpose
- Uses tmux split-panes mode for agent teams (configured in ~/.claude.json)
- Comfortable with parallel agent execution across multiple repos
- Values memory reliability — was disappointed when something wasn't remembered across sessions. Save important context promptly.
- Wants skills/hooks built to automate repetitive team processes — views this as foundational infrastructure, not nice-to-have
- On 2026-04-07, asked to ensure charter/hooks changes are on main before branching so agents pick them up

## Presentation preferences

- **Every file reference must be CLICKABLE** (asked 2026-07-11). Cite files as a path the terminal can resolve — `path/to/file.py` or `path/to/file.py:42` when a line matters — **never a bare basename** (`restore.sh`, `backblaze-bootstrap.md`) and never a prose-only mention. Repo-relative for files inside a repo; absolute for anything outside it (e.g. scratchpad artifacts). This applies to summaries and status reports, not just code walkthroughs — it is where bare basenames tend to creep in.
