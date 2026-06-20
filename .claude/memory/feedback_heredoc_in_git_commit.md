---
name: feedback_heredoc_in_git_commit
description: The parent repo's validate_commit_identity hook's heredoc-stripping regex fails on nested escapes in chained bash scripts, causing spurious block of valid commits. Use git commit -F /tmp/msg.txt instead.
type: feedback
originSessionId: 43b60daf-62e0-4fa1-b083-aef94bac4edf
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/hooks/validate_commit_identity.py heredoc handling fix shipped via main#188 / PR#248 (P3W4)"
---
Do not chain `git -c user.name=... commit -m "$(cat <<'EOF' ... EOF)"` inside a single bash call. Write the commit message to `/tmp/msg.txt` via the Write tool and call `git -c user.name=... -c user.email=... commit -F /tmp/msg.txt` instead.

**Why:** `validate_commit_identity.py` (both pre-#186 `_detect_target_roster` and post-#186 `_load_merged_roster` designs) runs `_strip_heredocs` then `_strip_quoted_strings` on the whole bash command before checking for `git ... commit`. When the command contains a `git -c user.name=...` early and a heredoc with embedded escaped double-quotes later, the regex leaves an orphaned fragment that the identity parser then reads as `user.name="\"` and blocks. This bit me mid-session during noorinalabs-main#112 part (b) — worked around by splitting each repo workflow into small bash calls and using `-F`. Team-lead filed parent #188 to fix the parser, but the workaround is durable even after a fix.

**How to apply:** When a commit message exceeds one line or contains any quotes/newlines, always use `-F /tmp/msg.txt`. Safe anywhere any parent hook scans Bash command strings. Doubly load-bearing for cross-repo `cd <child> && git commit ...` patterns where the parent hook fires on the orchestrator's Bash call.
