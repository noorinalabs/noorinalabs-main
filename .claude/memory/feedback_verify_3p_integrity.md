---
name: feedback_verify_3p_integrity
description: Don't claim a third-party tool's integrity property (verifies SHA, signs commits, etc.) without grepping the actual source — convention isn't proof
type: feedback
last_verified: 2026-07-27
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---
When pinning a third-party tool's installer, never claim it has integrity-checking behavior (SHA verification, GPG signature, manifest cross-check, etc.) without **grepping the actual installer source** for the operation. "It's a release downloader from a reputable project" is not evidence of verification.

**Why:** On deploy#176 I pinned `rhysd/actionlint`'s `download-actionlint.bash` to a tag SHA and wrote in the commit message + PR body that "the downloader verifies the binary's SHA256 against the upstream release manifest." Weronika-Rev-176 spent 30 seconds with `curl ... | grep -iE 'sha256|gpg|verify|checksum'` and it returned nothing — the script is plain `curl -L | tar xvz`. The pin chain only froze *which* downloader runs, not what binary it pulls. Bereket forwarded my false claim into formal slate-reasoning to Nadia.

**How to apply:** Before claiming an installer/downloader/action verifies anything, run:

```sh
curl -sL <installer-url> | rg -i 'sha256|sha512|sha1|checksum|verify|gpg|sig|integrity|hash|cosign|signed'
```

If that returns nothing, the tool **does not verify**. Either:
1. Add inline verification yourself (`curl + sha256sum -c <hash>`), OR
2. Don't make the claim. Describe what the pin actually does ("pins which script runs") and file followup if the integrity gap matters.

**Generalizes to:** any "trust this third-party because it's pinned" pattern — GitHub Actions wrappers, Homebrew formula installers, pip/npm post-install scripts, container `latest`-vs-`@sha256:` (where the sha256 IS the integrity check, but only on `:tag@sha256:...`-form references — `:latest` plus a separate digest comment is not).

**Cheap fix pattern that always works for binary downloads from GH releases:**

```sh
curl -fsSL -o tool.tar.gz "https://github.com/X/Y/releases/download/vN/tool_linux_amd64.tar.gz"
echo "<published-sha256>  tool.tar.gz" | sha256sum -c -
tar -xzf tool.tar.gz
```

The published checksum lives at `https://github.com/X/Y/releases/download/vN/<tool>_checksums.txt` for goreleaser-built projects (most modern Go tools), or in the release notes body. Two-source verify: the hash from the manifest must match the hash computed locally.
