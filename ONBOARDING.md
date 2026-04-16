# Welcome to NoorinALabs

## How We Use Claude

Based on Steven French's usage over the last 30 days:

Work Type Breakdown:
  Build Feature   ████████████░░░░░░░░  62%
  Debug & Fix     ████░░░░░░░░░░░░░░░░  22%
  Plan & Design   ██░░░░░░░░░░░░░░░░░░  10%
  Improve Quality █░░░░░░░░░░░░░░░░░░░   6%

Top Skills & Commands:
  /exit              ████████████████████  33x/month
  /remote-control    ████████████░░░░░░░░  20x/month
  /buddy             ███████░░░░░░░░░░░░░  12x/month
  /usage             █████░░░░░░░░░░░░░░░   8x/month
  /handoff           ████░░░░░░░░░░░░░░░░   6x/month
  /session-start     ██░░░░░░░░░░░░░░░░░░   3x/month
  /ontology-rebuild  ██░░░░░░░░░░░░░░░░░░   3x/month

Top MCP Servers:
  (none configured — all work runs through built-in tools and skills)

## Your Setup Checklist

### Codebases
- [ ] [noorinalabs-main](https://github.com/noorinalabs/noorinalabs-main) — Parent orchestration repo (team config, cross-repo coordination, ontology)
- [ ] [noorinalabs-isnad-graph](https://github.com/noorinalabs/noorinalabs-isnad-graph) — Computational hadith analysis platform (FastAPI, React, Neo4j)
- [ ] [noorinalabs-deploy](https://github.com/noorinalabs/noorinalabs-deploy) — Deployment orchestration (Terraform, Docker Compose, workflows)
- [ ] [noorinalabs-design-system](https://github.com/noorinalabs/noorinalabs-design-system) — Shared design system (tokens, components, icons, brand assets)
- [ ] [noorinalabs-data-acquisition](https://github.com/noorinalabs/noorinalabs-data-acquisition) — Data source acquisition (scrapers, API connectors, downloaders)
- [ ] [noorinalabs-isnad-ingest-platform](https://github.com/noorinalabs/noorinalabs-isnad-ingest-platform) — Ingest platform services
- [ ] [noorinalabs-landing-page](https://github.com/noorinalabs/noorinalabs-landing-page) — Organization landing page
- [ ] [noorinalabs-user-service](https://github.com/noorinalabs/noorinalabs-user-service) — User/auth/RBAC service (extracted from isnad-graph)

### MCP Servers to Activate
  (none required — the team currently operates without MCP integrations)

### Skills to Know About
- `/session-start` — **Run this first every session.** Boots the team, checks ontology, loads handoff from the previous session. Non-negotiable.
- `/handoff` — Saves session state so the next person (or your next session) can pick up where you left off.
- `/ontology-rebuild` — Resolves dirty ontology entries after code changes. Runs automatically at session start but can be triggered manually.
- `/ontology-librarian {topic}` — Look up domain knowledge before making code changes. Required before any implementation work.
- `/wave-kickoff` — Starts a new wave: branch creation, label management, issue labeling, execution plan.
- `/wave-wrapup` — Finalizes a wave: PR review, merge sequencing, issue cleanup, handoff to retro.
- `/wave-retro` — Full retrospective: PR analysis, trust matrix updates, feedback log, charter proposals.
- `/annunaki` — Check the error monitor for captured hook/command failures.
- `/annunaki-attack` — Analyze captured errors and implement fixes (hooks, skills, charter changes).
- `/review-pr` — Review a PR using the team's charter format.

## Team Tips

_TODO_

## Get Started

_TODO_

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
