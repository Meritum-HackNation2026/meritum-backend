#!/usr/bin/env bash
# Refresh the read-only copy/pl.json from meritum-design-system.
#   uv run bash scripts/sync.sh            copy from design-system main
#   uv run bash scripts/sync.sh <ref>    copy from another branch, tag or commit
# Never edit copy/pl.json by hand: tests/test_synced_copy.py checks SHA256SUMS.
# Needs `gh` signed in with read access to Meritum-HackNation2026/meritum-design-system.
set -euo pipefail
cd "$(dirname "$0")/.."
repo=Meritum-HackNation2026/meritum-design-system
ref=$(gh api "repos/$repo/commits/${1:-main}" --jq .sha)
mkdir -p copy
gh api -H 'Accept: application/vnd.github.raw' \
  "repos/$repo/contents/copy/pl.json?ref=$ref" >copy/pl.json
printf 'meritum-design-system %s\n' "$ref" >SOURCE
if command -v sha256sum >/dev/null; then
  sha256sum copy/pl.json >SHA256SUMS
else
  shasum -a 256 copy/pl.json >SHA256SUMS
fi
echo "copy/pl.json synced from $repo@${ref:0:12}"