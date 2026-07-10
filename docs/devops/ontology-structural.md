# Structural ontology — merge-driver canonical form and fan-out checklist

> **SUPERSEDED IN `noorinalabs-main` (main#939), rollout in progress for child repos.**
> The root cause the union merge-driver tried to fix — spurious conflicts on a committed,
> regenerated `code-graph.json` — is fixed at the source in `noorinalabs-main` by **no longer
> committing the structural index** (it is now a gitignored build product; see
> [`ontology/README.md`](../../ontology/README.md) § Structural layer and the root `.gitignore`).
> The merge-driver could never have worked on GitHub anyway: custom `merge=` drivers live in
> per-clone `git config` and GitHub's server-side merge never runs them, so committing the index
> made every concurrent PR conflict regardless. In `noorinalabs-main` the driver, its
> `.gitattributes` registration, and `make setup-ontology-merge-driver` have been **retired**.
> Cross-repo aggregation now regenerates every in-scope repo's index locally before rolling up
> (`ontology_gen.aggregate`), so nothing depends on a committed copy.
>
> The merge-driver mechanics below are **retained transitionally** for **child repos that have
> not yet migrated** — each still commits its own index and registers the driver until its
> per-#939 follow-up lands (`noorinalabs-data-acquisition` is expedited). As each child migrates,
> delete its row from the fan-out checklist. This banner is removed once every child has migrated.

This document was the canonical reference for the union merge-driver that prevented
spurious merge conflicts on `ontology/structural/code-graph.json` (#855, #856, #820
C×T2). It was authored to standardize the invocation form across all repos after a
divergence was identified between noorinalabs-main and the isnad-graph pilot (#871).

## Background

`code-graph.json` is a single committed artifact that every feature branch regenerates
independently. A plain text 3-way merge produces spurious conflicts on the sorted
node/edge arrays even when the two branches touched different source files (the
`feedback_parallel_panels_shared_file` hazard). The `ontology-codegraph` union
merge-driver (`.claude/lib/ontology_gen/merge_driver.py`) handles this by:

- Parsing both the ours, theirs, and base graphs
- Union-merging nodes by `id` and edges by `(src, dst, type)`
- Re-serializing in canonical order, so the result is byte-identical to a fresh
  regeneration

The driver name (`ontology-codegraph`) is declared in `.gitattributes`; the driver
command is per-clone local git config (it cannot live in a committed file).

## Canonical invocation form (#871)

```
git config merge.ontology-codegraph.name 'ontology code-graph union merge'
git config merge.ontology-codegraph.driver \
    'python3 <path-to>/merge_driver.py %O %A %B %P'
```

The **plain-script form** is canonical for all repos. The script is self-contained:
`merge_driver.py` carries an `ImportError` fallback (#860) that bootstraps `.claude/lib`
onto `sys.path` via `Path(__file__).resolve().parent.parent`, so the package-relative
import of `ontology_gen.model` resolves without any `PYTHONPATH` setup.

### Why plain-script and not `python3 -m`?

The isnad-graph pilot (#1128) used `PYTHONPATH={gen_lib} python3 -m ontology_gen.merge_driver`
because, at the time it was written, `merge_driver.py` did not have the self-contained
fallback — a bare `python3 .../merge_driver.py` invocation raised `ImportError` on the
package-relative `from .model import`. The `#860` fallback fixed that. The module form
now has no advantage over the plain-script form and requires explicit `PYTHONPATH`
manipulation that makes the git config harder to read and verify. The canonical form
going forward is plain-script.

### noorinalabs-main (driver lives here)

The driver is in this repo at `.claude/lib/ontology_gen/merge_driver.py`. Register with
a relative path (git runs drivers from the repo root):

```bash
# Via the Makefile target (preferred):
make setup-ontology-merge-driver

# Or manually:
git config merge.ontology-codegraph.name 'ontology code-graph union merge'
git config merge.ontology-codegraph.driver \
    'python3 .claude/lib/ontology_gen/merge_driver.py %O %A %B %P'
```

### Child repos (driver lives in the sibling noorinalabs-main checkout)

Child repos do not contain a copy of `merge_driver.py` (the generator is intentionally
not vendored — single source of truth, see `#854`). `scripts/structural_ontology.py
register-merge-driver` locates the driver via `locate_generator()` (which walks up to
the sibling noorinalabs-main or uses `$ONTOLOGY_GEN_LIB`) and registers an
absolute-path plain-script command:

```bash
# Via setup-hooks (preferred — make setup-hooks calls this automatically):
make setup-hooks

# Or directly:
python3 scripts/structural_ontology.py register-merge-driver
```

The resulting git config entry will look like:

```
[merge "ontology-codegraph"]
    name = ontology code-graph union merge
    driver = python3 /abs/path/noorinalabs-main/.claude/lib/ontology_gen/merge_driver.py %O %A %B %P
```

The absolute path is resolved at registration time. After `make setup-hooks` (or the
equivalent per-repo target), run `git config merge.ontology-codegraph.driver` to verify
the path is correct and points to the live noorinalabs-main checkout.

### $ONTOLOGY_GEN_LIB override

Set `ONTOLOGY_GEN_LIB=<path-to>/noorinalabs-main/.claude/lib` before running
`register-merge-driver` (or `make setup-hooks`) to override auto-discovery. CI uses this
to point at the sibling-checkout path:

```yaml
- uses: actions/checkout@v4
  with:
    repository: noorinalabs/noorinalabs-main
    path: _main
- run: ONTOLOGY_GEN_LIB=_main/.claude/lib python3 scripts/structural_ontology.py register-merge-driver
```

## Six-repo fan-out checklist (#820 C×T2)

For each child repo receiving the structural ontology layer, the following must be in
place (matching the isnad-graph pilot pattern, updated to the canonical invocation form):

- [ ] `scripts/structural_ontology.py` — consumer wrapper with `locate_generator()`,
  `emit`, `check`, and `register-merge-driver` subcommands. `register-merge-driver`
  MUST emit the **plain-script** form (not the module form).
- [ ] `.gitattributes` — `ontology/structural/code-graph.json merge=ontology-codegraph`
- [ ] `Makefile` — `setup-hooks` target that calls
  `python3 scripts/structural_ontology.py register-merge-driver`
- [ ] `.github/workflows/structural-ontology.yml` — CI job that checks out
  noorinalabs-main as a sibling, passes `--gen-lib _main/.claude/lib`, and runs
  `python3 scripts/structural_ontology.py check --require-generator`
- [ ] `.pre-commit-config.yaml` — `structural-ontology-staleness` hook that runs the
  same `check` subcommand (local dev degraded skip if generator absent; CI is
  authoritative)
- [ ] `pre_commit_ci_sync.py` — `structural-ontology` kind registered so the sync-drift
  gate enforces local/CI parity for this check

### Updating `register-merge-driver` in existing child repos

The isnad-graph pilot's `cmd_register_merge_driver` uses the module form. Update it to
the plain-script form before the fan-out lands additional repos on the old form:

```python
# Before (module form — NOT canonical):
driver = f"PYTHONPATH={gen_lib} python3 -m ontology_gen.merge_driver %O %A %B %P"

# After (plain-script form — canonical, #871):
driver = f"python3 {gen_lib}/ontology_gen/merge_driver.py %O %A %B %P"
```

The isnad-graph update is tracked as a follow-on to this PR (see #871 acceptance
criterion "per-child-repo rollout follows the same standardized shape").

## Verification

After registering the driver in any repo, verify it resolves and runs correctly:

```bash
# 1. Confirm the config entry:
git config merge.ontology-codegraph.driver

# 2. Confirm the script path exists and is executable:
python3 "$(git config merge.ontology-codegraph.driver | awk '{print $2}')" 2>&1 | head -1
# Expected: "usage: merge_driver.py <base %O> <ours %A> <theirs %B> [pathname %P]"

# 3. End-to-end test (union of two identical graphs is idempotent):
cp ontology/structural/code-graph.json /tmp/cg_test.json
git merge-file -p /tmp/cg_test.json /tmp/cg_test.json /tmp/cg_test.json 2>/dev/null
echo "exit $?"  # should be 0
```
