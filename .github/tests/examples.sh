#!/usr/bin/env bash
# The shipped examples must pass the shipped conformance checks: each examples/*.yml is copied to
# the path named by its `# Place at .github/workflows/<name>` header and checked as an adopting repo.
set -euo pipefail
project="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
dest="$tmp/examples/.github/workflows"
mkdir -p "$dest"

shopt -s nullglob
for file in "$project"/examples/*.yml; do
  name=$(grep -m1 -oE '^# Place at \.github/workflows/[^ ]+' "$file" | sed 's|.*/||' || true)
  [[ -n "$name" ]] || { echo "FAIL: example $(basename "$file"): missing \`# Place at\` header" >&2; exit 1; }
  [[ ! -e "$dest/$name" ]] || { echo "FAIL: example $(basename "$file"): duplicate placement $name" >&2; exit 1; }
  cp "$file" "$dest/$name"
done

RULES_FILE="$project/conformance/rules.json" "$project/conformance/check-concurrency.sh" --local "$tmp/examples" --repo examples

if command -v actionlint >/dev/null; then
  (cd "$tmp/examples" && actionlint -config-file "$project/.github/actionlint.yaml" .github/workflows/*.yml)
elif [[ -n "${CI:-}" ]]; then
  echo "FAIL: actionlint is required in CI" >&2
  exit 1
else
  echo "skip: actionlint not installed"
fi
echo "ok   examples"
