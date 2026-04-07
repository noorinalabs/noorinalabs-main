#!/usr/bin/env bash
# Install plugin config files from repo to ~/.claude/plugins/
# Run after cloning the repo to bootstrap plugin configuration.
#
# This script symlinks version-controlled config files (blocklist.json,
# known_marketplaces.json) into ~/.claude/plugins/. The marketplaces/
# directory is managed by Claude Code's plugin system and is not
# version-controlled.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${HOME}/.claude/plugins"

mkdir -p "$TARGET_DIR"

for file in blocklist.json known_marketplaces.json; do
    src="${SCRIPT_DIR}/${file}"
    dest="${TARGET_DIR}/${file}"

    if [ ! -f "$src" ]; then
        echo "SKIP: ${file} not found in repo"
        continue
    fi

    if [ -L "$dest" ]; then
        # Already a symlink — update it
        ln -sf "$src" "$dest"
        echo "UPDATED: ${dest} -> ${src}"
    elif [ -f "$dest" ]; then
        # Existing regular file — back up and replace
        cp "$dest" "${dest}.bak"
        ln -sf "$src" "$dest"
        echo "REPLACED: ${dest} -> ${src} (backup: ${dest}.bak)"
    else
        ln -s "$src" "$dest"
        echo "LINKED: ${dest} -> ${src}"
    fi
done

echo "Plugin config installation complete."
