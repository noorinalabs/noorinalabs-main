---
name: feedback_test_mock_masks_prod_failure
description: "Charter-tier-candidate pattern — unit tests that exercise injection-point mocks bypass server-side validation; pair with static-analysis or real-call gate"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0be57897-3749-48b2-8850-f155e5434000
---

Unit tests that route around external subprocess / network / server-side validation via injection-point mocks (`graphql_runner=mock`, `auth_status_runner=mock`, etc.) CAN'T catch bugs that only manifest in the real call path. Mocks return pre-fabricated data; they don't enforce schema, variable usage, auth scopes, or any server-side correctness rule. A test suite that ONLY exercises mocked paths will green-light protocol-violation bugs.

**Why:** Two observed instances by 2026-05-16:

1. **P3W11 2026-05-16 Hook 21 `variableNotUsed`** (issue #448, hotfix PR #449): `_ITEM_LOOKUP_QUERY` declared `$repo: String!` and `$num: Int!` as required GraphQL variables but never referenced them in the query body. GitHub's GraphQL rejected every call with `variableNotUsed`; gh exited non-zero; the hook silent-no-op'd on first-production-fire. 31 unit tests passed because `FakeGraphQLRouter` routes by substring match — it never parsed the query and never enforced variable-usage rules. Cost: ~30 min discovery, 1 hotfix PR, 4 manual compensations (`deploy#284`, `data-acquisition#52`, `deploy#11`, `main#448`).
2. **#175 (filed during Hook 15 sentinel work)** — narrower instance: `test_cwd_hash_matches_shell_pwd_sha1sum` spot-checks the Python sha1 against an in-test Python reimplementation, NEVER runs the shell pipeline. If the skill's bash snippet drifts, the test still passes. Filed but not yet fixed.

**How to apply:**

For every hook / skill that calls an external system via injection-point mock pattern, add ONE of these gates ALONGSIDE the mocked tests:

| External system | Recommended gate |
|---|---|
| GraphQL queries / mutations | Static-analysis test: regex over the query/mutation strings, assert every declared `$var: Type!` appears ≥1 additional time as `$var` in the operation body |
| Shell pipelines invoked by skills | `subprocess.run` test that executes the canonical pipeline in an isolated cwd and asserts the output matches the Python equivalent |
| REST API calls | Schema-validation test: pin the expected request shape (URL + method + body keys) and assert the mock fixtures match a real (recorded) endpoint response shape |
| OAuth / auth-scope checks | Test fixture that asserts the parser handles real `gh auth status -h github.com` output across format variations |

PR #449 added the GraphQL static-analysis gate (`GraphQLVariableUsageTests` class in `test_post_label_change_wave_field_sync.py`) as the first instance of this pattern in the repo.

**Charter-promotion candidate (W11 retro):** Two-instance pattern surfaced 2026-05-16. Owner-decided pattern shape during P3W11 wave-scoping. Promotion shape: new `pull-requests.md` or `hooks.md` rule "Injection-point mocks must be paired with a real-call validation gate (static analysis OR subprocess OR schema check)." Aino + Santiago both surfaced this in their PR #449 reviews independently; convergence is evidence the pattern is real.

Sibling memories: [[feedback_verify_3p_integrity]] (analog at the third-party-claim layer — verify against source, don't trust the README); [[feedback_actionlint_needs_shellcheck]] (analog at the lint-tool layer — silent skip when dependency missing).
