#!/usr/bin/env bash
# Check the community forms or detect local templates that override them.
set -euo pipefail
[[ ${1:-} == --local && -d ${2:-} && ${3:-} == --repo && -n ${4:-} && $# == 4 ]] || { echo 'usage: check-issue-forms.sh --local <dir> --repo <name>' >&2; exit 2; }
root=$2 repo=$4
command -v jq >/dev/null || { echo 'FAIL: jq is required' >&2; exit 2; }
yq --version 2>/dev/null | grep -q mikefarah || { echo 'FAIL: yq (mikefarah) is required' >&2; exit 2; }
errors=0
if [[ "$repo" == .github ]]; then
  while IFS='|' read -r file type label; do
    path="$root/.github/ISSUE_TEMPLATE/$file"
    if [[ ! -f "$path" ]]; then echo "FAIL $file: missing form"; errors=1; continue; fi
    if ! data=$(yq -o=json -I=0 '.' "$path" | jq -s 'if length == 1 then .[0] else error("expected one document") end'); then
      echo "FAIL $file: invalid YAML"; errors=1; continue
    fi
    if ! jq -e --arg type "$type" --arg label "$label" '
      (.name | type == "string" and length > 3) and
      (.description | type == "string" and length > 0) and
      (.body | type == "array" and length > 0 and any(.[]; .type == "textarea" or .type == "input" or .type == "dropdown" or .type == "checkboxes")) and
      .type == $type and .labels == [$label]
    ' <<<"$data" >/dev/null; then echo "FAIL $file: invalid form structure, type or initial labels (expected $type / $label)"; errors=1; fi
  done <<'FORMS'
bug-report.yml|Bug|needs-triage
feature-request.yml|Feature|needs-triage
tracking-issue.yml|Task|tracking
follow-up-action.yml|Task|follow-up
FORMS
  path="$root/.github/ISSUE_TEMPLATE/config.yml"
  if [[ ! -f "$path" ]] || ! yq -o=json -I=0 '.' "$path" | jq -se 'length == 1 and .[0].blank_issues_enabled == true' >/dev/null; then
    echo 'FAIL config.yml: blank issues must be enabled'; errors=1
  fi
else
  found=$(cd "$root" && find . -maxdepth 4 \( -type f -o -type l \) \( -ipath './.github/ISSUE_TEMPLATE/*' -o -ipath './ISSUE_TEMPLATE/*.md' -o -ipath './docs/ISSUE_TEMPLATE/*.md' -o -ipath './ISSUE_TEMPLATE.md' -o -ipath './.github/ISSUE_TEMPLATE.md' -o -ipath './docs/ISSUE_TEMPLATE.md' \) -print) || { echo 'FAIL: cannot scan the checkout for local issue templates' >&2; exit 2; }
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    echo "FAIL ${path#./}: local issue template or configuration overrides shared forms"
    errors=1
  done <<<"$found"
fi
if (( errors )); then exit 1; fi
echo "ok   $repo: issue forms"
