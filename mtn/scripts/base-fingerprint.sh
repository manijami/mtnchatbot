#!/usr/bin/env sh
# Writes mtn/deploy/base-fingerprint.sha256: SHA-256 of every non-test api/ source file and the
# workspace package manifests at the upstream base commit. mtn/deploy/core.Dockerfile checks the
# base image against it, so the MTN overlay is only ever layered on the exact upstream build.
#   usage: mtn/scripts/base-fingerprint.sh <base-commit>
set -eu
commit="${1:?usage: $0 <base-commit>}"
out="$(git rev-parse --show-toplevel)/mtn/deploy/base-fingerprint.sha256"
git ls-tree -r --name-only "$commit" -- api package.json packages/api/package.json \
    packages/data-provider/package.json packages/data-schemas/package.json \
  | grep -E '\.(js|json)$' \
  | grep -vE '(__tests__|\.spec\.|\.test\.|/test/|__mocks__|jest\.config)' \
  | while read -r f; do
      printf '%s  %s\n' "$(git show "$commit:$f" | shasum -a 256 | cut -d' ' -f1)" "$f"
    done > "$out"
echo "$(wc -l < "$out" | tr -d ' ') files fingerprinted at $commit -> $out"
