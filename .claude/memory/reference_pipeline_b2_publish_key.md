---
name: reference_pipeline_b2_publish_key
description: B2 pipeline-bucket key topology + publish gotchas — read-only consumer key vs write-capable producer key, z4h zshenv early-return, rclone 401 diagnosis.
metadata:
  type: reference
---

The `noorinalabs-pipeline` B2 bucket is the batch graph-load transport: `scripts/publish_parquet.py` (producer, da#342/#343, in data-acquisition) uploads `data/curated/`+`data/staging/` to it; `deploy-data-load.yml` (consumer, deploy#546/#547) downloads from it onto the VPS via rclone. `make publish-parquet` (or `PARQUET_REF=<ref> uv run python scripts/publish_parquet.py`). Default ref `staged/narrator-resolve/<UTC-date>-<git-short-sha>`.

**Two keys, same env-var NAME, different value by location (owner decision 2026-07-08, "local write, GH read-only", least-privilege):**
- **GitHub Actions secret** `PIPELINE_B2_KEY_ID`/`PIPELINE_B2_KEY` = **READ-ONLY** key (caps `listFiles,listKeys,readFiles,listBuckets`). Correct for the VPS consumer — it only downloads.
- **Local `~/.zshenv`** `PIPELINE_B2_KEY_ID`/`PIPELINE_B2_KEY` = **WRITE-capable** key (needs `writeFiles`; `deleteFiles` for overwrite/cleanup), scoped to bucket `noorinalabs-pipeline`. Required for `publish_parquet.py` (producer). Owner must mint this in the B2 console (App Keys → scope to bucket) — orchestrator cannot.

**Three distinct B2 keys total** (docs/secrets-audit-2026-04-24.md): `B2_*` (backups → `isnad-graph-backups`, backup.sh), `TF_STATE_B2_*` (terraform state), `PIPELINE_B2_*` (this pipeline bucket).

**Gotchas that cost time:**
- **z4h `~/.zshenv` early-return:** the zsh4humans block runs `[[ -o no_interactive && -z "${Z4H_BOOTSTRAPPING-}" ]] && return` near the top — for a NON-interactive shell (the agent Bash tool) this returns out of `.zshenv` entirely, so any `export` placed BELOW it never reaches the tool env (works fine in the user's interactive terminal, so it *looks* set). Fix: put the exports at the very TOP of `~/.zshenv`, above the z4h block.
- **Read-only key write failure is misdiagnosed by rclone:** a write with a read-only key fails `ERROR failed to create bucket: Unknown 401 unauthorized` — this is NOT a bucket-creation-permission problem and `--b2-no-check-bucket` (`RCLONE_CONFIG_PIPELINE_NO_CHECK_BUCKET=true`) does NOT fix it; the *write itself* is unauthorized. `rclone lsf` (read) still succeeds, masking it. Diagnose capabilities definitively via B2 native API: `curl -s -u "$KEY_ID:$KEY" https://api.backblazeb2.com/b2api/v3/b2_authorize_account` → capabilities live at `apiInfo.storageApi.capabilities` (v3 nesting; NOT top-level `allowed`).
- rclone native-env config (CWE-214-safe, no secret on argv): `RCLONE_CONFIG_PIPELINE_TYPE=b2 RCLONE_CONFIG_PIPELINE_ACCOUNT=$PIPELINE_B2_KEY_ID RCLONE_CONFIG_PIPELINE_KEY=$PIPELINE_B2_KEY`.

Rollback baseline published 2026-07-08: `staged/narrator-resolve/baseline-20260705-run5scrubbed` (26 objects, 1.045 GiB = the run-5-scrubbed curated+staging set currently on stg/prod). Related: [[feedback_iac_over_oneoffs]], [[project_narrator_chokepoints_enrich]], [[project_p7_narrator_pollution_resolve_fixes]].
