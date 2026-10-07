#!/usr/bin/env bash
# Regression test for stale_deployments.jq, the stale-deployment filter used by action.yml.
set -euo pipefail

FILTER="$(dirname "$0")/../stale_deployments.jq"
APP=app0uuid
recent=$(date -u -v-60S +%Y-%m-%dT%H:%M:%S.000000Z 2>/dev/null || date -u -d '-60 seconds' +%Y-%m-%dT%H:%M:%S.000000Z)
url() { printf '/project/p1/environment/e1/application/%s/deployment/x' "$1"; }

# /api/v1/deployments serializes a sortBy()'d collection, so it can come back as an id-keyed object.
deployments=$(cat <<JSON
{
  "3": {"deployment_uuid": "stale-iso-fraction", "deployment_url": "$(url $APP)", "pull_request_id": 0, "status": "in_progress", "created_at": "2026-10-07T12:35:23.000000Z"},
  "4": {"deployment_uuid": "stale-sql-format", "deployment_url": "$(url $APP)", "pull_request_id": 0, "status": "queued", "created_at": "2026-10-07 12:35:23"},
  "5": {"deployment_uuid": "stale-offset", "deployment_url": "$(url $APP)", "pull_request_id": "0", "status": "queued", "created_at": "2026-10-07T12:35:23+00:00"},
  "6": {"deployment_uuid": "null-created-at", "deployment_url": "$(url $APP)", "pull_request_id": 0, "status": "queued", "created_at": null},
  "7": {"deployment_uuid": "recent-in-progress", "deployment_url": "$(url $APP)", "pull_request_id": 0, "status": "in_progress", "created_at": "${recent}"},
  "8": {"deployment_uuid": "stale-pr-5", "deployment_url": "$(url $APP)", "pull_request_id": 5, "status": "in_progress", "created_at": "2020-01-01T00:00:00Z"},
  "9": {"deployment_uuid": "stale-other-app", "deployment_url": "$(url ${APP}x)", "pull_request_id": 0, "status": "in_progress", "created_at": "2020-01-01T00:00:00Z"},
  "10": {"deployment_uuid": "stale-no-url", "pull_request_id": 0, "status": "in_progress", "created_at": "2020-01-01T00:00:00Z"},
  "11": {"deployment_uuid": "old-finished", "deployment_url": "$(url $APP)", "pull_request_id": 0, "status": "finished", "created_at": "2020-01-01T00:00:00Z"}
}
JSON
)

check() {
  local input="$1" pr="$2" expected="$3" label="$4" actual
  actual=$(printf '%s' "$input" | jq -r --arg app "$APP" --arg pr "$pr" --argjson max_age 3600 -f "$FILTER" \
    | jq -r '"\(.deployment_uuid)\(if .age_seconds == null then "?" else "" end)"' | paste -sd, -)
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $label — expected '${expected}', got '${actual}'"
    exit 1
  fi
  echo "ok: $label"
}

check "$deployments" 0 "stale-iso-fraction,stale-sql-format,stale-offset,null-created-at?" \
  "regular app: stale queued/in_progress of this app only, all timestamp formats, unparseable flagged"
check "$deployments" 5 "stale-pr-5" "PR preview: only that PR's stale deployments"
check "[$(printf '%s' "$deployments" | jq -c '.["3"]')]" 0 "stale-iso-fraction" "array response"
check '[]' 0 "" "no active deployments"

echo "All stale-deployment filter checks passed."
