#!/usr/bin/env bash
# Offline fixtures for conformance/check-concurrency.sh. Each fixture repo is a directory of $FX shaped
# like a checkout: --local reads it directly, --org reads it through a stub that replaces `gh`.
set -euo pipefail
project="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export FX="$tmp/fx"

cat > "$tmp/stub.sh" <<'EOF'
#!/usr/bin/env bash
# Serves `gh repo list` (repos = directories of $FX) and `gh api repos/<org>/<repo>/contents/<path>`.
# STUB_FAIL fails every call; STUB_FAIL_PATH fails calls whose path contains it.
[[ -n "${STUB_FAIL:-}" ]] && { echo "HTTP 500" >&2; exit 1; }
if [[ "$1" == "repo" ]]; then ls "$FX"; exit 0; fi
path=${!#}
[[ -n "${STUB_FAIL_PATH:-}" && "$path" == *"$STUB_FAIL_PATH"* ]] && { echo "HTTP 500" >&2; exit 1; }
repo=$(cut -d/ -f3 <<<"$path")
target="$FX/$repo/${path#repos/*/*/contents/}"
if [[ -d "$target" ]]; then
  ls "$target" | jq -R '{name:., type:"file"}' | jq -s .
elif [[ -f "$target" ]]; then
  cat "$target"
else
  echo "gh: Not Found (HTTP 404)" >&2; exit 1
fi
EOF
chmod +x "$tmp/stub.sh"

failed=0
CI_GROUP="\${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || github.ref }}"
CI_CANCEL="\${{ github.event_name == 'pull_request' }}"
BASE_RULES='{"release_workflows":["o/w/.github/workflows/release-tag.yml"],"agent_config":{"repo":"o/a","tag":"v1","sha":"0123456789abcdef0123456789abcdef01234567"}}'
rules() { printf '%s\n' "$1" > "$tmp/rules.json"; }
# exemptions <repo> <json>: write the repo's org-conformance.json; empty json removes it
exemptions() {
  mkdir -p "$FX/$1/.github"
  if [[ -z "$2" ]]; then rm -f "$FX/$1/.github/org-conformance.json"; else printf '%s\n' "$2" > "$FX/$1/.github/org-conformance.json"; fi
}
# run_case <label> <expected-exit> <expected-output-substring-or-empty> [args...]
run_case() {
  local label=$1 want=$2 needle=$3 out rc=0
  shift 3
  out=$(RULES_FILE="$tmp/rules.json" GH="$tmp/stub.sh" ORG=o "$project/conformance/check-concurrency.sh" "$@" 2>&1) || rc=$?
  if [[ "$rc" != "$want" ]] || { [[ -n "$needle" ]] && ! grep -qF -- "$needle" <<<"$out"; }; then
    echo "FAIL $label: exit $rc (want $want), output: $out" >&2
    failed=1
  else
    echo "ok   $label"
  fi
}
# both <label> <expected-exit> <needle> [repo]: run the case against the org and against the repo's checkout
both() {
  local repo=${4:-r}
  run_case "$1 (org)" "$2" "$3" --org
  run_case "$1 (local)" "$2" "$3" --local "$FX/$repo" --repo "$repo"
}
# workflow <repo> <file>: write a workflow (stdin) for the repo; the repo is created on first use
workflow() { mkdir -p "$FX/$1/.github/workflows"; cat > "$FX/$1/.github/workflows/$2"; }
reset() { rm -rf "$FX"; mkdir -p "$FX"; rules "$BASE_RULES"; }

reset
workflow r ci.yml <<EOF
on: {pull_request: {}}
concurrency:
  group: ci-$CI_GROUP
  cancel-in-progress: $CI_CANCEL
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
both "canonical CI form" 0 "ok   r"

workflow r ci.yml <<'EOF'
on: {pull_request: {}}
concurrency:
  group: ci-${{ github.head_ref || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
both "legacy CI form is rejected" 1 "expected CI form"

workflow r ci.yml <<EOF
on: {pull_request: {}}
concurrency:
  group: ci-$CI_GROUP
  cancel-in-progress: true
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
both "canonical group with unconditional cancellation" 1 "expected CI form"

reset
workflow r ci.yml <<'EOF'
on: {push: {}}
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
both "missing concurrency" 1 "r: ci.yml: no workflow-level concurrency"

reset
workflow r ci.yml <<EOF
on: {pull_request: {}}
concurrency:
  group: \${{ github.workflow }}-$CI_GROUP
  cancel-in-progress: $CI_CANCEL
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
both "wrong workflow stem" 1 "r: ci.yml: concurrency"

reset
workflow r deploy.yml <<'EOF'
on: {push: {}}
concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
both "queue form without exemption is rejected" 1 "expected CI form"
exemptions r '{"concurrency":{"exemptions":[{"workflow":"deploy.yml","form":"queue","reason":"deploys"}]}}'
both "queue form through a queue exemption" 0 "ok   r"
exemptions r '{"concurrency":{"exemptions":[{"workflow":"deploy.yml","form":"event","reason":"tags"}]}}'
both "ref group on an event exemption is rejected" 1 "expected event form"

reset
workflow r release.yml <<'EOF'
on: {push: {}}
concurrency:
  group: release-${{ github.sha }}
  cancel-in-progress: false
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
exemptions r '{"concurrency":{"exemptions":[{"workflow":"release.yml","form":"event","reason":"tags"}]}}'
both "event form through an event exemption" 0 "ok   r"
exemptions r '{"concurrency":{"exemptions":[{"workflow":"release.yml","form":"queue","reason":"deploys"}]}}'
both "sha group on a queue exemption is rejected" 1 "expected queue form"

reset
workflow r release.yml <<'EOF'
on: {push: {}}
concurrency:
  group: release-${{ github.sha }}
  cancel-in-progress: false
jobs:
  tag:
    uses: o/w/.github/workflows/release-tag.yml@abc123 # v1
EOF
both "event form through uses:" 0 "ok   r"

reset
workflow r release.yml <<'EOF'
on: {push: {}}
concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false
jobs:
  tag:
    uses: o/w/.github/workflows/release-tag.yml@abc123
EOF
both "ref group on a release caller is rejected" 1 "expected event form"

reset
workflow r release.yml <<'EOF'
on: {push: {}}
jobs:
  tag:
    uses: o/w/.github/workflows/release-tag.yml@abc123
  publish:
    runs-on: x
    steps: [{run: "true"}]
EOF
both "mixed jobs are not a release caller" 1 "expected CI form"

reset
workflow r reusable.yml <<'EOF'
on: workflow_call
concurrency:
  group: reusable
  cancel-in-progress: false
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
both "reusable workflow with concurrency" 1 "reusable workflow declares workflow-level concurrency"

reset
workflow r reusable.yaml <<'EOF'
on: workflow_call
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
both "reusable .yaml workflow without concurrency" 0 "ok   r"

reset
mkdir -p "$FX/empty"
both "repo without workflows" 0 "ok   empty" empty

reset
workflow r ci.yml <<EOF
on: {pull_request: {}}
concurrency:
  group: ci-$CI_GROUP
  cancel-in-progress: $CI_CANCEL
jobs: {a: {runs-on: x, steps: [{run: "true"}]}}
EOF
exemptions r '{"concurrency":{"exemptions":[{"workflow":"gone.yml","form":"queue","reason":"x"}]}}'
both "stale exemption (workflow missing)" 1 "exemption gone.yml: no such workflow"
exemptions r '{"concurency":{"exemptions":[]}}'
both "unknown top-level key" 1 'unknown top-level key "concurency"'
exemptions r '{"concurrency":{"exemption":[]}}'
both "unknown concurrency key" 1 "unknown key concurrency.exemption"
exemptions r '{"concurrency":{"exemptions":[{"workflow":"ci.yml","form":"queue","reason":"x","note":"y"}]}}'
both "unknown exemption key" 1 'unknown key "note"'
exemptions r '{"concurrency":{"exemptions":[{"workflow":"ci.yml","form":"queue","reason":" "}]}}'
both "exemption without reason" 1 "needs a workflow and a nonblank reason"
exemptions r '{"concurrency":{"exemptions":[{"workflow":"ci.yml","form":"queue","reason":"a"},{"workflow":"ci.yml","form":"queue","reason":"b"}]}}'
both "duplicate exemption" 1 "duplicate entry ci.yml"
exemptions r '{"concurrency":{"exemptions":[{"workflow":"ci.yml","reason":"x"}]}}'
both "exemption without form" 1 'needs form "queue" or "event"'
exemptions r '{"concurrency":{"exemptions":[{"workflow":"ci.yml","form":"ref","reason":"x"}]}}'
both "exemption with invalid form" 1 'needs form "queue" or "event"'
exemptions r '{"concurrency":{"exemptions":"ci.yml"}}'
both "exemptions not an array" 1 "concurrency.exemptions must be an array"
exemptions r '{'
both "org-conformance.json not JSON" 1 ".github/org-conformance.json: not valid JSON"
exemptions r '{"concurrency":{}}'
both "empty concurrency section" 0 "ok   r"
exemptions r ''

# An invalid repo file is that repo's violation only: the next repos are still evaluated.
workflow s ci.yml < "$FX/r/.github/workflows/ci.yml"
exemptions r '[]'
run_case "invalid org-conformance.json does not stop the org run" 1 "ok   s" --org
exemptions r ''

STUB_FAIL_PATH=org-conformance.json run_case "API failure on org-conformance.json" 2 "cannot read .github/org-conformance.json" --org
STUB_FAIL=1 run_case "API failure" 2 "cannot list repos" --org

rules '{"release_workflows":["o/w/x.yml@v1"],"agent_config":{"repo":"o/a","tag":"v1","sha":"0123456789abcdef0123456789abcdef01234567"}}'
run_case "release_workflows with @ref" 1 "without @ref" --org
rules '{"release_workflows":[],"agent_config":{"repo":"o/a","tag":"v1","sha":"v1"}}'
run_case "agent_config with an invalid sha" 1 "agent_config needs" --config-only
rules "$BASE_RULES"
run_case "--config-only skips GitHub" 0 "ok   " --config-only
exemptions r '{"concurrency":{"exemptions":[{"workflow":"ci.yml","form":"queue"}]}}'
run_case "--config-only validates an org-conformance.json" 1 "needs a workflow and a nonblank reason" --config-only "$FX/r/.github/org-conformance.json"
RULES_FILE="$project/conformance/rules.json" "$project/conformance/check-concurrency.sh" --config-only >/dev/null \
  || { echo "FAIL shipped conformance/rules.json is invalid" >&2; failed=1; }

run_case "missing mode" 2 "usage:"
run_case "--local without --repo" 2 "usage:" --local "$FX/r"

if [[ "$failed" != 0 ]]; then exit 1; fi
