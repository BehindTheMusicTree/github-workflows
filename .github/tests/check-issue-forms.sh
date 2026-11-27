#!/usr/bin/env bash
# Offline fixtures for conformance/check-issue-forms.sh: the shared forms in .github, and the local
# templates or configuration that would replace them in any other repo.
set -euo pipefail
project="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
failed=0

# run_case <label> <expected-exit> <expected-output-substring-or-empty> <repo>
run_case() {
  local label=$1 want=$2 needle=$3 repo=$4 out rc=0
  out=$("$project/conformance/check-issue-forms.sh" --local "$tmp/fx" --repo "$repo" 2>&1) || rc=$?
  if [[ "$rc" != "$want" ]] || { [[ -n "$needle" ]] && ! grep -qF -- "$needle" <<<"$out"; }; then
    echo "FAIL $label: exit $rc (want $want), output: $out" >&2
    failed=1
  else
    echo "ok   $label"
  fi
}
reset() { rm -rf "$tmp/fx"; mkdir -p "$tmp/fx/.github/ISSUE_TEMPLATE"; }
# form <file> <type> <label>: write a valid form
form() {
  cat > "$tmp/fx/.github/ISSUE_TEMPLATE/$1" <<YML
name: Some form
description: Describe the work
type: $2
labels: [$3]
body:
  - type: textarea
    id: what
    attributes: {label: What}
YML
}
valid_set() {
  reset
  form bug-report.yml Bug needs-triage
  form feature-request.yml Feature needs-triage
  form tracking-issue.yml Task tracking
  form follow-up-action.yml Task follow-up
  printf 'blank_issues_enabled: true\n' > "$tmp/fx/.github/ISSUE_TEMPLATE/config.yml"
}

valid_set
run_case "valid shared forms" 0 "ok   .github" .github

valid_set; rm "$tmp/fx/.github/ISSUE_TEMPLATE/tracking-issue.yml"
run_case "missing form" 1 "tracking-issue.yml: missing form" .github

valid_set; form bug-report.yml Task needs-triage
run_case "wrong issue type" 1 "bug-report.yml: invalid form" .github

valid_set; form follow-up-action.yml Task tracking
run_case "wrong initial label" 1 "follow-up-action.yml: invalid form" .github

valid_set; printf 'name: [unclosed\n' > "$tmp/fx/.github/ISSUE_TEMPLATE/bug-report.yml"
run_case "invalid YAML" 1 "bug-report.yml: invalid YAML" .github

valid_set; printf '%s\n---\n%s\n' 'name: a' 'name: b' > "$tmp/fx/.github/ISSUE_TEMPLATE/bug-report.yml"
run_case "multi-document YAML" 1 "bug-report.yml: invalid YAML" .github

valid_set; printf 'blank_issues_enabled: false\n' > "$tmp/fx/.github/ISSUE_TEMPLATE/config.yml"
run_case "blank issues disabled" 1 "config.yml: blank issues must be enabled" .github

valid_set; rm "$tmp/fx/.github/ISSUE_TEMPLATE/config.yml"
run_case "missing config" 1 "config.yml: blank issues must be enabled" .github

reset
run_case "no local templates" 0 "ok   r" r

reset; form bug.yml Bug needs-triage
run_case "local form overrides" 1 "local issue template or configuration overrides" r

reset; printf 'blank_issues_enabled: true\n' > "$tmp/fx/.github/ISSUE_TEMPLATE/config.yml"
run_case "config only overrides" 1 "ISSUE_TEMPLATE/config.yml" r

reset; printf '# bug\n' > "$tmp/fx/.github/ISSUE_TEMPLATE/bug.md"
run_case "local markdown template overrides" 1 "ISSUE_TEMPLATE/bug.md" r

reset; mkdir -p "$tmp/fx/docs"; printf '# t\n' > "$tmp/fx/docs/ISSUE_TEMPLATE.md"
run_case "docs single template overrides" 1 "docs/ISSUE_TEMPLATE.md" r

reset; mkdir -p "$tmp/fx/docs/ISSUE_TEMPLATE"; printf '# t\n' > "$tmp/fx/docs/ISSUE_TEMPLATE/a.md"
run_case "docs template directory overrides" 1 "docs/ISSUE_TEMPLATE/a.md" r

reset; printf '# t\n' > "$tmp/fx/ISSUE_TEMPLATE.md"
run_case "root single template overrides" 1 "ISSUE_TEMPLATE.md" r

reset; mkdir -p "$tmp/fx/ISSUE_TEMPLATE"; printf '# t\n' > "$tmp/fx/ISSUE_TEMPLATE/a.md"
run_case "root template directory overrides" 1 "ISSUE_TEMPLATE/a.md" r

reset; printf 'x\n' > "$tmp/fx/.github/ISSUE_TEMPLATE/notes.txt"
run_case "any file in the template folder overrides" 1 "notes.txt" r

reset; mkdir -p "$tmp/fx/.github/workflows"; printf 'on: push\n' > "$tmp/fx/.github/workflows/ci.yml"
run_case "unrelated files are ignored" 0 "ok   r" r

exit "$failed"
