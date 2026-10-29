#!/usr/bin/env bash
set -euo pipefail

health_url="${1:?health_url required}"
min_version="${2:?min_version required}"

semver='^[0-9]+\.[0-9]+\.[0-9]+$'

if [[ ! "$min_version" =~ $semver ]]; then
  echo "::error::min_version must be X.Y.Z (got '${min_version}')"
  exit 1
fi

if ! body="$(curl -fsS --max-time 15 "$health_url")"; then
  echo "::error::Could not reach ${health_url}"
  exit 1
fi

if ! actual="$(jq -er '.version' <<<"$body")"; then
  echo "::error::${health_url} returned no .version field"
  exit 1
fi

if [[ ! "$actual" =~ $semver ]]; then
  echo "::error::${health_url} reported a malformed version '${actual}'"
  exit 1
fi

lowest="$(printf '%s\n%s\n' "$min_version" "$actual" | sort -V | head -n1)"
if [ "$lowest" != "$min_version" ]; then
  echo "::error::API at ${health_url} is ${actual}, below required ${min_version}. Release the API first."
  exit 1
fi

echo "API version ${actual} satisfies >= ${min_version}"
