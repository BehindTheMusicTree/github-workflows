#!/usr/bin/env bash
# Regression test for the stale-deployment jq filter in action.yml ("Trigger deploy and wait").
# Keep FILTER in sync with that call site — if you change one, change both.
set -euo pipefail

FILTER='.deployments[]? | select((.pull_request_id | tostring) == $pr and (.status == "queued" or .status == "in_progress") and (now - (.created_at | sub("\\.[0-9]+"; "") | sub(" "; "T") | sub("Z?$"; "Z") | fromdateiso8601)) > $max_age)'

recent=$(date -u -v-60S +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '-60 seconds' +%Y-%m-%dT%H:%M:%SZ)
deployments=$(cat <<JSON
{"deployments": [
  {"deployment_uuid": "stale-iso-fraction", "pull_request_id": 0, "status": "in_progress", "created_at": "2026-10-07T12:35:23.000000Z"},
  {"deployment_uuid": "stale-sql-format", "pull_request_id": 0, "status": "queued", "created_at": "2026-10-07 12:35:23"},
  {"deployment_uuid": "recent-in-progress", "pull_request_id": 0, "status": "in_progress", "created_at": "${recent}"},
  {"deployment_uuid": "stale-other-pr", "pull_request_id": 5, "status": "in_progress", "created_at": "2020-01-01T00:00:00Z"},
  {"deployment_uuid": "old-finished", "pull_request_id": 0, "status": "finished", "created_at": "2020-01-01T00:00:00Z"}
]}
JSON
)

check() {
  local pr="$1" expected="$2" label="$3" actual
  actual=$(printf '%s' "$deployments" | jq -r --arg pr "$pr" --argjson max_age 1800 "$FILTER | .deployment_uuid" | paste -sd, -)
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $label — expected '${expected}', got '${actual}'"
    exit 1
  fi
  echo "ok: $label"
}

check 0 "stale-iso-fraction,stale-sql-format" "regular app: only stale queued/in_progress, both timestamp formats"
check 5 "stale-other-pr" "PR preview: only that PR's stale deployments"

echo "All stale-deployment filter checks passed."
