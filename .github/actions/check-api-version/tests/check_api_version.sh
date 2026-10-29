#!/usr/bin/env bash
# Exercises check-api-version.sh against file:// health payloads (curl reads them like an HTTP response).
set -euo pipefail

script="$(cd "$(dirname "$0")/.." && pwd)/check-api-version.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

check() {
  local payload="$1" min="$2" expect="$3" label="$4" url="file://${tmp}/health.json" actual
  if [ "$payload" = "__missing__" ]; then
    rm -f "${tmp}/health.json"
  else
    printf '%s' "$payload" >"${tmp}/health.json"
  fi
  if bash "$script" "$url" "$min" >/dev/null 2>&1; then
    actual=pass
  else
    actual=fail
  fi
  if [ "$actual" != "$expect" ]; then
    echo "FAIL: $label — expected $expect, got $actual"
    exit 1
  fi
  echo "ok: $label"
}

check '{"version":"14.5.0"}' 14.5.0 pass "equal"
check '{"version":"14.5.1"}' 14.5.0 pass "patch above"
check '{"version":"15.0.0"}' 14.5.0 pass "major above"
check '{"version":"14.10.0"}' 14.9.0 pass "numeric (not lexical) comparison"
check '{"version":"14.4.1"}' 14.5.0 fail "below"
check '{"version":"9.9.9"}' 14.5.0 fail "lower major with higher minor"
check '{"status":"ok"}' 14.5.0 fail "no version field"
check '{"version":"14.5"}' 14.5.0 fail "malformed API version"
check '{"version":14}' 14.5.0 fail "non-string version"
check 'not json' 14.5.0 fail "non-JSON payload"
check '{"version":"14.5.0"}' 14.5 fail "malformed min_version"
check __missing__ 14.5.0 fail "unreachable endpoint"

echo "All check-api-version checks passed."
