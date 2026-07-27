---
name: reference_ssh_topology
description: Mental model for SSH in this project — VPSes, aliases, keys, the IdentitiesOnly bug, the whoami habit, post-rebuild known_hosts hygiene
type: reference
last_verified: 2026-07-27
originSessionId: 0ef090a7-ccf8-4152-82b9-a618873d3462
promotion_target: none
status: active
---
# SSH in this project — reference (refreshed 2026-06-03 — prod IP corrected)

Owner has been tripped up by SSH multiple times across handoffs. This memory captures the current mental model + the working footguns.

## Two VPSes (current as of 2026-06-03 — verified via Hetzner API)

| Alias | IP | Hetzner id | Status | Notes |
|---|---|---|---|---|
| `noorinalabs-stg` | 87.99.137.225 | 128728699 | running | Rebuilt 2026-05-01; Hetzner re-allocated same IP, config unchanged |
| `noorinalabs-prod` | **178.156.214.225** | 128728719 | running | **Rebuilt 2026-05-01 — IP CHANGED from old 87.99.134.161** |

**2026-06-03 incident + fix:** owner "couldn't SSH to prod." Root cause = `~/.ssh/config` `noorinalabs-prod` HostName still pointed at the OLD prod IP `87.99.134.161`, which is no longer in the Hetzner project (old hand-made box, recycled/foreign now — it answers :22 with a host key your known_hosts remembered but rejects all your keys; deploy#86 teardown target). Both VPSes were rebuilt 2026-05-01, AFTER the 2026-04-26 note. Fix applied: config HostName → `178.156.214.225`, `ssh-keygen -R 87.99.134.161`, backup at `~/.ssh/config.bak.2026-06-03`. After the fix, `ssh noorinalabs-prod` (deploy) works; both keys verified against the new box.

**Diagnostic lever:** `~/.noorinalabs-rotate-2026-04-26/HCLOUD_TOKEN` is the live Hetzner API token — use it read-only to list servers/IPs/ids when SSH state is in doubt (`curl -H "Authorization: Bearer $(cat ...)" https://api.hetzner.cloud/v1/servers`). The Hetzner project has **no** registered `ssh_keys` (boxes get pubkeys via cloud-init inline injection, not Hetzner-managed keys).

**`deploy` user privileges (verified 2026-06-03):** `groups=deploy,sudo,docker` — so `deploy` can run `docker`/`docker compose` directly (no root needed) AND has sudo. The Neo4j migration etc. run fine as plain `ssh noorinalabs-prod`.

## `~/.ssh/config` structure (as of 2026-04-26)

```
Host noorinalabs-stg noorinalabs-prod
    User deploy
    IdentityFile ~/.ssh/noorinalabs_deploy
    IdentitiesOnly yes

Host noorinalabs-stg
    HostName 87.99.137.225

Host noorinalabs-prod
    HostName 87.99.134.161

Match host noorinalabs-stg,noorinalabs-prod user root
    IdentityFile ~/.ssh/id_ed25519
```

Effective resolution:
- `ssh noorinalabs-stg` → `deploy@87.99.137.225` with `noorinalabs_deploy` (the default User+IdentityFile from the first Host block)
- `ssh root@noorinalabs-stg` → tries to swap to `id_ed25519` via Match clause but **the IdentitiesOnly=yes from the first block locks identity to noorinalabs_deploy**. Match's `IdentityFile` directive is additive (not replacing), so under IdentitiesOnly both keys ARE in the candidate set, but Aisha's empirical finding (Phase B B.0): `ssh root@noorinalabs-stg` fails publickey. Worked-around with explicit `ssh -o IdentityFile=~/.ssh/id_ed25519 -o IdentitiesOnly=yes root@<ip>`.

This is filed as tech-debt (gap surfaced 2026-04-26 Phase B). Cleanest structural fix: drop `IdentitiesOnly yes` from the first block, OR replace the first Host block with a Match clause that's user-conditional.

## Keys (as of 2026-04-26)

| Key file | Purpose | Authorized on |
|---|---|---|
| `~/.ssh/id_ed25519` | Owner workstation (general use) | stg `/root/.ssh/authorized_keys` + stg `/home/deploy/.ssh/authorized_keys` (cloud-init injected); prod `/root/` + `/home/deploy/` (manually pasted at hand-made-prod time) |
| `~/.ssh/noorinalabs_deploy` | CI deploy key (matches `DEPLOY_SSH_PRIVATE_KEY` repo-scope GH secret) | stg `/home/deploy/.ssh/authorized_keys` (manually appended in B.5'); prod `/home/deploy/.ssh/authorized_keys` (manually pasted at provisioning time) |

`~/.ssh/jwt_*.pem` mentioned in earlier handoffs — those are **stale**; Phase A 2026-04-26 generated new RSA keys at `~/.noorinalabs-rotate-2026-04-26/JWT_*.pem`. They migrate in via env-scope GH secrets at deploy time, not via SSH.

## RESOLVED: cloud-init multi-key gap (deploy#82 → #165/#173 → ADR 0006) — no manual append needed

**Corrected 2026-07-27 (main#1139).** This section previously said the TF cloud-init template injects only **one** pubkey (`var.ssh_public_key_path`) and that the CI deploy key must be **manually appended after every provision** before any deploy workflow fires. **That is no longer true, and following it wastes a manual step on every rebuild.**

Per [ADR 0006 — per-env per-role SSH keys](noorinalabs-deploy/docs/adr/0006-per-env-per-role-ssh-keys.md) (deploy#164, supersedes ADR 0003), cloud-init now injects **two distinct keys, per-env and per-role**:

| Module variable | Lands at | Key |
|---|---|---|
| `deploy_n_path` (default `./deploy.pub`) | `/home/deploy/.ssh/authorized_keys` | the CI DEPLOY key — private half is the env-scope `DEPLOY_SSH_PRIVATE_KEY` secret |
| `root_n_path` (default `./root.pub`) | `/root/.ssh/authorized_keys` | a SEPARATE ROOT key — owner-workstation-only, **never** in a GH secret |

Verified in `noorinalabs-deploy/terraform/hetzner/modules/hetzner-vps/`: `main.tf` renders both via `sensitive(chomp(file(var.deploy_n_path)))` / `…(var.root_n_path)` (the `chomp()` permadrift fix, deploy#174), `cloud-init.yaml.tpl` writes each to its own path, and `variables.tf`/`README.md` document both. The `hcloud_ssh_key` resource is **gone** (removed in deploy#222) — cloud-init is the only injection path.

Two consequences for anyone reading this note operationally:
- **`var.ssh_public_key_path` does not exist any more.** A runbook or plan still referencing it is stale.
- The checked-in `root.pub` is a **placeholder** whose private half does not exist. Operators must override `root_n_path` per-env with their real root pubkey, or root login on a fresh box will fail. The checked-in pubkeys exist only so module-only `terraform validate` and CI cold-rebuild provisioning work without an operator-local path.

## Post-rebuild known_hosts hygiene

After any VPS destroy+apply, the new server's host keys differ from the old box's. SSH refuses to connect with "REMOTE HOST IDENTIFICATION HAS CHANGED" until the stale entries are cleared. Owner's habit (verified working 2026-04-26):

```bash
ssh-keygen -R <ip>           # clear by IP
ssh-keygen -R <alias>        # clear by alias if hashed entries exist
```

Then `ssh -o StrictHostKeyChecking=accept-new <alias>` accepts the new host key on first connect. (Or just `ssh <alias>` — many distros now prompt to accept new keys interactively.)

## The `whoami` habit

First command into any VPS in any new session:

```bash
ssh noorinalabs-stg 'whoami; id'
```

Tells you which user you actually landed as, which groups you're in (docker? sudo?), and whether your alias still resolves the way you expect.

## Common pitfalls observed

1. **Alias-user mismatch** — owner has hit this multiple times across handoffs. Always run `whoami` first.
2. **`authorized_keys` overwrite in bootstrap-vps.sh** (deploy#112 — superseded by cloud-init now, but the underlying append-vs-overwrite hygiene rule still applies for any future manual edits).
3. **`sudo -u deploy` fails when already deploy** — paste from runbooks assuming root. The deploy user is not in sudoers for itself.
4. **Key file permissions** — private keys need `chmod 600`, otherwise `Permissions ... are too open`.
5. **`IdentitiesOnly yes`** — without it, ssh-agent presents every loaded key; after a few failures the VPS may rate-limit. With it (per current config), Match clauses can't add new identities to the candidate set in a way that actually gets offered.
6. ~~**Cloud-init single-pubkey**~~ — RESOLVED by ADR 0006 (see above); no longer a pitfall. The live pitfall in its place: the checked-in `root.pub` is a placeholder, so `root_n_path` must be overridden per-env.
7. **Host fingerprint drift after VPS rebuild** — see post-rebuild hygiene above.

## Best-practice direction (owner's roadmap)

- Drop `IdentitiesOnly yes` from `~/.ssh/config` first block, OR re-architect Host blocks per user-class (separate Host blocks for `noorinalabs-stg-deploy` and `noorinalabs-stg-root` with user-specific identity)
- ~~Land cloud-init multi-key support (#165 + #173 gap A) before Phase C~~ — DONE, ADR 0006 / deploy#164, `hcloud_ssh_key` removed in #222
- Rotate deploy SSH keys on a schedule once per-env keys are in env-scope GH secrets

## Cross-references

- `noorinalabs-deploy#82` — original cloud-init VPS baseline issue (the umbrella)
- `noorinalabs-deploy#165` — single-pubkey injection (sister issue, has Phase B comment with empirical evidence)
- `noorinalabs-deploy#173` — Phase B follow-up (5 gaps): chomp() permadrift, write_files-vs-users, sshd vs ssh service name on 24.04, debconf whiptail, ephemeral CI key
- `noorinalabs-deploy#174` — chomp() PR (gap A in #173)
- `noorinalabs-deploy#164` — ADR 0006 per-env per-role SSH keys (supersedes ADR 0003); closed out the multi-key gap above
- `noorinalabs-deploy#222` — removed the `hcloud_ssh_key` resource; cloud-init is now the sole key-injection path
