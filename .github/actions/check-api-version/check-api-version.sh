#!/usr/bin/env bash
set -euo pipefail

health_url="${1:?health_url required}"
min_version="${2:?min_version required}"
origin_ip="${3:-}"

semver='^[0-9]+\.[0-9]+\.[0-9]+$'

if [[ ! "$min_version" =~ $semver ]]; then
  echo "::error::min_version must be X.Y.Z (got '${min_version}')"
  exit 1
fi

resolve=()
if [[ -n "$origin_ip" ]]; then
  if [[ ! "$health_url" =~ ^https://([^/:?#]+)(:([0-9]+))?([/?#]|$) ]]; then
    echo "::error::origin_ip requires an HTTPS URL with a hostname"
    exit 1
  fi
  resolve=(--noproxy "${BASH_REMATCH[1]}" --resolve "${BASH_REMATCH[1]}:${BASH_REMATCH[3]:-443}:${origin_ip}")
fi

response_file="$(mktemp)"
trap 'rm -f "$response_file"' EXIT
if ! status="$(curl -sS --max-time 15 "${resolve[@]}" -o "$response_file" -w '%{http_code}' "$health_url")"; then
  echo "::error::Could not reach ${health_url}"
  exit 1
fi
if [[ ! "$status" =~ ^2[0-9][0-9]$ && ! ( "$status" == 000 && "$health_url" == file://* ) ]]; then
  echo "::error::HTTP ${status} received from ${health_url}"
  exit 1
fi
body="$(cat "$response_file")"

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
