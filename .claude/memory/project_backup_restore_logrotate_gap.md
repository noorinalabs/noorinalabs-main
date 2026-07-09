---
name: project_backup_restore_logrotate_gap
description: Backups have NEVER run on either host (timer uninstalled); coverage omits user-postgres/audit_log; restore never rehearsed; docker logs unbounded on stg+prod. Filed deploy#558/#559/#560/#561.
metadata:
  type: project
---

Discovered 2026-07-09 while the owner was authorizing a stg **and prod** graph wipe-and-rebuild. His framing: prod "is not stable enough to merit surgery" today, but "there will come a time when that will be untenable, so we'd need notions and mechanisms for snapshotting and restoring in place when that happens — probably for every data store."

**The mechanisms exist in the repo and have never been connected.** `scripts/backup.sh`, `scripts/restore.sh`, `systemd/isnad-backup.{service,timer}`, a `B2_*` credential pair and an `isnad-graph-backups` bucket are all committed. Verified on both hosts:

- stg (`87.99.137.225`): `systemctl status isnad-backup.timer` → *"Unit could not be found"*
- prod (`178.156.214.225`): no `isnad*` units at all; `is-active` → `inactive`

**No backup has ever been taken in this project.** → **deploy#558**.

**Coverage gap (deploy#559).** `backup.sh` dumps only `neo4j` + the isnad `postgres`. Twelve stateful containers run. **`user-postgres` has NO coverage** — it holds accounts/sessions/RBAC *and* the `audit_log` relocated out of Neo4j on 2026-06-30 ([[project_audit_log_relocation]]). Unlike the graph, none of it is reconstructible from the published Parquet. Also uncovered: `redis`, `user-redis`, `kafka`, `loki`, `grafana`. The deliverable includes *explicitly declaring* which stores are disposable — an undocumented omission and a deliberate exclusion look identical during an incident.

**Restore never rehearsed (deploy#560).** The only test (`test_backup_restore_compose_default.py`) asserts `backup.sh`/`restore.sh` share a `COMPOSE_FILE` default (deploy#498); it never runs either script. And since no backup exists, there is nothing to restore *from*. Rehearsal must assert on restored content (row counts, sampled record, `count(n)`), not exit code — `pg_restore --clean` warns-and-succeeds while restoring nothing. Must be shown RED against a corrupted backup before trusted green ([[feedback_passing_repro_masks_bug]]).

**Docker logs unbounded on BOTH hosts (deploy#561).** `json-file` driver, no `/etc/docker/daemon.json`, no `max-size`/`max-file`, no `logrotate.d` entry, no compose `logging:`. Footprint is small today (stg 22 MB, prod 41 MB; disks 31%/24%) — the risk is latent. **Demonstration:** the 07-09 stg load emitted `collapsed_double_corpus_prefix` **16M+ times** (~250 B each = multiple GB) and only escaped filling the disk because that container ran with `--rm`, so Docker reaped the log with it. That is a coincidence of invocation, not a control. Exited containers also retain logs indefinitely (`da174-graph-load`, exited 3 days). `daemon.json` `log-opts` apply only to containers created **after** the daemon restarts.

**Common root cause across deploy#551 / #558 / #561: hosts are configured by hand and nothing asserts their state.** deploy#551 predicted prod shares stg's root-owned `/home/deploy`; confirmed 07-09 (`drwxr-xr-x root root`, dated to the 05-01 rebuild). It is on the critical path — the first prod `deploy-data-load.yml` run creates `${LOAD_DATA_DIR}` under `/home/deploy` and will fail at `mkdir`. Do NOT hand-fix prod; the stg `chown` one-off is *why* #551 exists. Fix as IaC + assert in `verify-deploy.yml` (an uninstalled timer must FAIL deploy verification, not pass silently — [[feedback_enforcement_hierarchy]]).

**Timing argument to preserve:** wipe-and-rebuild is a legitimate rollback plan *only while* prod state is reproducible from an artifact. The moment prod holds non-reproducible state (users, sessions, audit_log — it already does), "just rebuild it" stops being a plan. The window to install backups is before that day, not after.

Gotcha met en route: `sudo -n du /var/lib/docker/containers/*/*-json.log` returns **0** — the glob expands as the unprivileged user *before* `sudo` runs, matches nothing, and `du` sums an empty list. Use `sudo -n sh -c "du ... "` so the glob expands as root. A zero from a command that can silently receive no arguments is not a measurement ([[feedback_passing_repro_masks_bug]]).

Related: [[feedback_iac_over_oneoffs]], [[project_narrator_chokepoints_enrich]], [[reference_pipeline_b2_publish_key]].
