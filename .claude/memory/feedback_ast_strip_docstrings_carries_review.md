---
name: feedback_ast_strip_docstrings_carries_review
description: "To re-anchor a stale verdict after a doc-only follow-up commit, prove the .py is docstring-only by comparing ASTs with docstrings stripped — turns 'my prior measurements still hold' from an assertion into a re-runnable artifact"
metadata:
  node_type: memory
  type: feedback
last_verified: 2026-07-30
---

When a PR's head moves for a **documentation** fix, every prior verdict goes stale under the #950/#1040 content-staleness rule — `compute_review_state()` drops it regardless of how immaterial the change was (see [[feedback_pr_review_verdict_format]] §7 and §9: materiality is not an input to the gate, and a head move drops *every* verdict, not just the blocker's). The reviewer then faces a choice: redo the whole pass, or assert "nothing I measured changed."

**Neither. Prove it mechanically:**

```python
import ast
def strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
               and isinstance(body[0].value.value, str):
                node.body = body[1:]
    return tree
# compare ast.dump(strip_docstrings(ast.parse(old))) == ast.dump(strip_docstrings(ast.parse(new)))
```

If the ASTs match with docstrings stripped, the added lines are **provably** docstring-only rather than merely *looking* that way in a diff — so the whole prior battery (mutation kills, base-vs-head differentials, state matrices) carries forward **by construction**, not by the reviewer's say-so. Pair it with an ancestry check (`gh api .../compare/<old>...<new>` → `status: ahead, ahead_by: 1, behind_by: 0`) to rule out amend/rebase/force, and a byte-identity check on the test file.

**Why it beats both alternatives:** a full re-review is expensive and its conclusion is still only as good as the reviewer's memory; a bare "nothing material changed" is exactly the unverifiable claim the staleness rule exists to reject. The AST comparison is a **cheap artifact anyone can re-run** — the reviewer's judgement is removed from the load-bearing step.

**Origin:** PR #1178 (2026-07-30). Nadia Khoury pushed a doc-only additive commit (`256f79a0` → `a69c280e`, 18+/3-), which took the gate from 2/2 to **`distinct_reviewer_count=0, passes=False`**. Both reviewers — Aino Virtanen and Weronika Zielinska, working independently and without seeing each other — reached for the same technique and both reported `identical after stripping docstrings: True`. Convergence by two reviewers who could not coordinate is itself the argument for adopting it.

**A useful side effect:** touching a markdown file pulled the PR from **14 to 21 check-runs** — Markdown lint, cspell, lychee, mermaid render, YAML/JSON syntax and actionlint only trigger on doc paths. A doc-only commit is therefore *better* gated than the code commit it follows, not worse.

**How to apply:**
- Doc-only follow-up commit → re-anchor with the AST check + ancestry check + test-file byte identity, then post a short re-affirmation citing all three. Do not redo the full pass, and do not skip the proof.
- Any change to executable lines → the prior battery does **not** carry; re-review properly.
- Orchestrators: after any head move, re-request from **every** reviewer, not just the one who blocked. Both verdicts drop, and re-anchoring is cheap when the delta is provably inert.
