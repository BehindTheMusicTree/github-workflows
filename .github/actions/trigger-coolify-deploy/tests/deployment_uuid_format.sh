#!/usr/bin/env bash
# Regression test for the deployment_uuid/phantom_uuid format check in action.yml
# (cancel_phantom_builds). Keeps this in sync with the regex at that call site —
# if you change one, change both.
set -euo pipefail

PATTERN='^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-z]{20,30})$'

check() {
  local value="$1" expect="$2" label="$3"
  if printf '%s' "$value" | grep -qiE "$PATTERN"; then
    actual=accept
  else
    actual=reject
  fi
  if [ "$actual" != "$expect" ]; then
    echo "FAIL: $label — expected $expect, got $actual for '${value}'"
    exit 1
  fi
  echo "ok: $label"
}

check "a1b2c3d4-e5f6-7890-abcd-ef1234567890" accept "legacy UUID"
check "A1B2C3D4-E5F6-7890-ABCD-EF1234567890" accept "legacy UUID, uppercase"
check "j9rlp1cg3qdsuqi8sqsvykpo" accept "Coolify nanoid-style id (24 chars)"
check "abcdefghijklmnopqrst" accept "nanoid-style id, 20 chars (lower bound)"
check "abcdefghijklmnopqrstuvwxyzabcd" accept "nanoid-style id, 30 chars (upper bound)"
check "not a valid id!" reject "garbage with spaces/punctuation"
check "" reject "empty string"
check "abc123" reject "too short to be a nanoid"
check "abcdefghijklmnopqrstuvwxyzabcde" reject "31 chars, over the bound"

echo "All deployment_uuid format checks passed."
