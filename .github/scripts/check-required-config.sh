#!/usr/bin/env bash
# Check that required env vars are set. Caller passes list; workflow sets env from secrets/vars.
# Usage: check-required-config.sh [s:NAME|v:NAME]...
#   Or: echo "s:NAME"; echo "v:NAME" | check-required-config.sh  (one spec per line)
#   s:NAME = secret (report as "NAME (secret)")
#   v:NAME = variable (report as "NAME (variable)")

set -e

specs=()
if [[ $# -eq 0 ]]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && specs+=( "$line" )
  done
else
  specs=( "$@" )
fi

missing=""
for spec in "${specs[@]}"; do
  if [[ "$spec" == s:* ]]; then
    name="${spec#s:}"
    suffix=" (secret)"
  elif [[ "$spec" == v:* ]]; then
    name="${spec#v:}"
    suffix=" (variable)"
  else
    name="$spec"
    suffix=""
  fi
  val="${!name}"
  [[ -z "$val" ]] && missing="${missing} ${name}${suffix}"
done

if [[ -n "$missing" ]]; then
  echo "ERROR: Missing required config:$missing"
  echo "Set variables and secrets in Settings → Environments (or org/repo level). See README."
  exit 1
fi
echo "All required vars and secrets are set."
