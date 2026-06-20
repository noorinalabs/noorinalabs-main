---
name: feedback_agent_color_render_quirk
description: Color variance for the same agent across user-side teammate-message tags doesn't mean two agent instances exist; verify via SendMessage routing color before claiming duality.
type: feedback
originSessionId: 7deaa69a-9ef8-44e6-9ca9-39e5a23f368c
promotion_target: none
promotion_threshold:
  retro_citations: 3
status: active
---
When the user's terminal renders `<teammate-message teammate_id="X" color="A">` for the same agent X with **different** colors A across messages in one session (e.g., Nadia appearing green, then blue, then green), this is a **UI rendering quirk** — not evidence of multiple parallel agent instances.

**Why:** P3W4 2026-05-05 PR#266 review: orchestrator observed Wanjiku tagged blue then purple, Nadia tagged green then blue then green; initially framed this as a multi-instance / message-replay glitch sibling to `feedback_self_loop_task_replay_glitch`. Investigation showed the harness's authoritative source — `SendMessage` routing returns `targetColor: "green"` for every Nadia message and `targetColor: "purple"` for every Wanjiku message. There's only one agent process per name. The user-side color tag varies for unknown UI reasons (possibly per-message-thread render, message age coloring, etc) but does not reflect duality.

**How to apply:**
1. Don't trust the user-side `<teammate-message>` color tag as identity — it's render decoration
2. Trust the harness `SendMessage` response field `routing.targetColor` as authoritative — that's the agent's actual color
3. If you suspect duality, verify by inspecting team config: `cat ~/.claude/teams/<team-name>/config.json | jq '.members[] | {name, agentId, color}'` — there's exactly one entry per name
4. The actual replay-glitch family covered by `feedback_self_loop_task_replay_glitch` is a different phenomenon (TaskCreate replay), not this color render variance — don't conflate them
5. If a "second instance" message contains correct state-verification logic that catches an issue (e.g., "no-action because already done"), the underlying behavior is still legitimate output from the single instance — keep the diligence, drop the duality framing
