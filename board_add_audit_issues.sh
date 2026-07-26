#!/bin/sh
# Add all 89 code-audit program issues (2026-07-26, umbrella noorinalabs-main#1089)
# to GitHub Project 2 (the Cross-Repo Wave Plan board).
#
# Run from any gh-authenticated terminal at the repo root:
#   sh board_add_audit_issues.sh
# Requires gh auth with project scope (run `gh auth refresh -s project` first if
# item-add returns 403).
#
# This is the /board-audit Step-6 bulk-add for a KNOWN orphan set: these issues
# were filed via the GitHub API from a remote session, so Hook 13's in-session
# auto-add never fired. None of them carry a wave label yet, so Wave-field sync
# is a designed no-op for them (labels are canonical; the field gets set when a
# wave-kickoff labels them). Safe to re-run: item-add on an already-present item
# is a no-op.
#
# AFTER this, run the full /board-audit from the same terminal for the org-wide
# orphan sweep + Wave-field drift sync. Standing owner action from the W27 retro:
# project 2's Wave field is missing the W24 option — add it (Settings -> Fields ->
# Wave) or the 4 wave-24-labeled issues stay skipped.

add() {
  gh project item-add 2 --owner noorinalabs --url "$1" \
    || echo "WARN: failed to add $1" >&2
}

# noorinalabs-main: umbrella 1089, epics 1090-1098, decision 1099, tasks 1100-1123
for n in $(seq 1089 1123); do
  add "https://github.com/noorinalabs/noorinalabs-main/issues/$n"
done

# isnad-graph: BUG-04/05/06 + D2-D10
for n in $(seq 1191 1202); do
  add "https://github.com/noorinalabs/noorinalabs-isnad-graph/issues/$n"
done

# user-service: BUG-01/07 + E2-E8
for n in $(seq 204 211); do
  add "https://github.com/noorinalabs/noorinalabs-user-service/issues/$n"
done

# deploy: C5-C12
for n in $(seq 698 704); do
  add "https://github.com/noorinalabs/noorinalabs-deploy/issues/$n"
done

# data-acquisition: BUG-03a + F1-F10
for n in $(seq 492 501); do
  add "https://github.com/noorinalabs/noorinalabs-data-acquisition/issues/$n"
done

# isnad-ingest-platform: BUG-02, BUG-03b, B2/B4/B5/B6, F7
for n in $(seq 140 146); do
  add "https://github.com/noorinalabs/noorinalabs-isnad-ingest-platform/issues/$n"
done

# design-system: BUG-10 + H1/H3/H4/H5/H6
for n in $(seq 134 139); do
  add "https://github.com/noorinalabs/noorinalabs-design-system/issues/$n"
done

# landing-page: BUG-11/12 + H3-LP/H6-LP
for n in $(seq 159 162); do
  add "https://github.com/noorinalabs/noorinalabs-landing-page/issues/$n"
done

echo "Done: 89 item-add calls issued. Verify the count on project 2, then run /board-audit for the full sweep."
