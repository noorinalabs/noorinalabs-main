---
name: feedback_wikilink_md_suffix_grep
description: "When removing a memory, grep the BARE slug (not [[slug]]) to catch inbound links — the .md-suffixed form [[slug.md]] evades a bracket-anchored grep and leaves a dangling link."
metadata:
  node_type: memory
  type: feedback
---

When relocating or deleting a memory file, you MUST repoint every inbound `[[wikilink]]` from retained files or you leave a dangling link. The trap: wikilinks appear in TWO forms — the bare-slug `[[project_foo]]` AND the `.md`-suffixed `[[project_foo.md]]`. A grep anchored on the bracketed bare form (`\[\[project_foo\]\]`, the shape used in the #732 curation commit a7d7b2e) **silently misses** the suffixed form.

**Why:** the suffixed form is a legitimate, in-the-wild authoring variant; a bracket-anchored pattern only matches one of the two.

**How to apply:** grep the **bare slug without brackets** (`grep -rn 'project_foo' .claude/memory/`) — this catches `[[project_foo]]`, `[[project_foo.md]]`, and any prose mention, then triage each hit. Verify post-edit with the same bare-slug sweep returning ZERO across the retained corpus. Surfaced #740 parent-cleanup (PR #758): `project_hadith_id_double_prefix.md` linked `[[project_data_pipeline_architecture.md]]` (suffixed) — a slug-only `[[slug]]` grep reported clean while the link actually dangled. Reviewers (Nadia, Wanjiku) re-verified both forms. Relates to [[feedback_full_read_over_tail]] (corpus state-claims need exhaustive, not narrow, scanning); informs #752 wikilink-hygiene work.
