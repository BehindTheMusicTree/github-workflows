#!/usr/bin/env bash
# Verify every workflow triggered by push or pull_request declares the canonical workflow-level
# concurrency, so superseded runs stop consuming Actions minutes. Read-only: it never writes to a repo.
#
# `<stem>` is the workflow file name without `.yml`/`.yaml`; it is used instead of `github.workflow`,
# which holds the caller's name when the workflow runs through `workflow_call` and would collide with
# the caller's group.
#   CI form:      group: <stem>-${{ github.head_ref || github.ref }}
#                 cancel-in-progress: ${{ github.event_name == 'pull_request' }}
#   Event form:   group: <stem>-${{ github.sha }}
#                 cancel-in-progress: false
#   Queue form:   group: <stem>-${{ github.ref }}
#                 cancel-in-progress: false
# With a ref group, GitHub keeps one pending run and replaces it with the next one. release-tag only
# validates `before..after` of the run it is called from, so a version bump carried by a replaced run
# would never be tagged. The event form gives each push its own group: nothing is cancelled or
# replaced. It applies to workflows whose every job calls one of RULES_FILE's `release_workflows`
# (matched without the `@ref`) and to exemptions declared with `"form": "event"`. The queue form
# serializes runs of a ref (deploys, publications) and applies to exemptions declared with
# `"form": "queue"`.
# Exemptions live in each repo's `.github/org-conformance.json`:
#   {"concurrency": {"exemptions": [{"workflow": "deploy.yml", "form": "queue", "reason": "..."}]}}
# Every exemption needs a reason and a form; there is no default. A missing file means no exemption.
# Values are compared as text after YAML parsing; nothing looser is accepted. A workflow triggered
# only by workflow_call must not declare workflow-level concurrency: its callers do.
# Stale (missing workflow, no push/pull_request trigger, already a release caller), duplicate or
# reasonless exemptions and unknown keys are violations.
#
# Usage:
#   check-concurrency.sh --local <dir> --repo <name>   checkout of one repo (pull request check)
#   check-concurrency.sh --org                         default branch of every non-archived repo of ORG
#   check-concurrency.sh --config-only [<file>]        RULES_FILE and an optional org-conformance.json
# Requires jq, and yq (mikefarah) except for --config-only. GH overrides the `gh` command (fixtures).
# Exit codes: 0 ok, 1 violation found, 2 API, tooling or usage failure.
set -euo pipefail
shopt -s inherit_errexit 2>/dev/null || true

ORG="${ORG:-BehindTheMusicTree}"
RULES_FILE="${RULES_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rules.json}"
GH="${GH:-gh}"
REPO_CONFIG=.github/org-conformance.json

usage() { echo "usage: $0 --local <dir> --repo <name> | --org | --config-only [<file>]" >&2; exit 2; }

mode="" local_dir="" repo_name="" config_file=""
case "${1:-}" in
  --local)
    mode=local local_dir=${2:-}
    [[ "${3:-}" == "--repo" && -n "${4:-}" && -n "$local_dir" && $# -eq 4 ]] || usage
    repo_name=$4
    [[ -d "$local_dir" ]] || { echo "FAIL: $local_dir is not a directory" >&2; exit 2; }
    ;;
  --org) [[ $# -eq 1 ]] || usage; mode=org ;;
  --config-only) [[ $# -le 2 ]] || usage; mode=config config_file=${2:-} ;;
  *) usage ;;
esac

command -v jq >/dev/null || { echo "FAIL: jq is required" >&2; exit 2; }

violations=0
errors=0

rules_errors=$(jq -r '
  def nonblank: type == "string" and test("\\S");
  (if (.release_workflows | type) == "array" and all(.release_workflows[]; nonblank and (contains("@") | not)) then empty
   else "release_workflows must be an array of owner/repo/path strings without @ref" end),
  (if (.agent_config | type) == "object" and (.agent_config.repo | nonblank) and (.agent_config.tag | nonblank)
      and (.agent_config.sha | type == "string" and test("^[0-9a-f]{40}$")) then empty
   else "agent_config needs a nonblank repo and tag and a 40-hex sha" end)
' "$RULES_FILE") || { echo "FAIL: cannot parse $RULES_FILE" >&2; exit 2; }
if [[ -n "$rules_errors" ]]; then
  while IFS= read -r line; do echo "FAIL config: $line"; done <<<"$rules_errors"
  exit 1
fi

# Slurped so that an empty file or several documents are rejected instead of read as no exemption.
read -r -d '' REPO_CONFIG_CHECK <<'JQ' || true
def nonblank: type == "string" and test("\\S");
if length != 1 or (.[0] | type) != "object" then "must hold a single JSON object"
else .[0]
  | ((keys - ["concurrency"])[] | "unknown top-level key \(tojson)"),
    (select(has("concurrency")) | .concurrency
     | if type != "object" then "concurrency must be an object"
       else ((keys - ["exemptions"])[] | "unknown key concurrency.\(.)"),
         (select(has("exemptions")) | .exemptions
          | if type != "array" then "concurrency.exemptions must be an array"
            elif any(.[]; type != "object") then "concurrency.exemptions entries must be objects"
            else
              (.[] | (keys - ["workflow", "form", "reason"])[] as $k
               | "concurrency.exemptions: unknown key \($k | tojson)"),
              (.[] | select(((.workflow | nonblank) and (.reason | nonblank)) | not)
               | "concurrency.exemptions: entry \(tojson) needs a workflow and a nonblank reason"),
              (.[] | select((.form == "queue" or .form == "event") | not)
               | "concurrency.exemptions: entry \(tojson) needs form \"queue\" or \"event\""),
              (group_by(.workflow)[] | select(length > 1)
               | "concurrency.exemptions: duplicate entry \(.[0].workflow)")
            end)
       end)
end
JQ

# check_repo_config <file> <prefix>: print violations of an org-conformance.json; return 1 if any.
check_repo_config() {
  local out
  out=$(jq -rs "$REPO_CONFIG_CHECK" "$1" 2>/dev/null) || out="not valid JSON"
  [[ -z "$out" ]] && return 0
  while IFS= read -r line; do echo "$2: $line"; done <<<"$out"
  return 1
}

if [[ "$mode" == config ]]; then
  if [[ -n "$config_file" ]]; then
    check_repo_config "$config_file" "FAIL config: $config_file" || exit 1
    echo "ok   $config_file"
  fi
  echo "ok   $RULES_FILE"
  exit 0
fi

yq --version 2>/dev/null | grep -q mikefarah || { echo "FAIL: yq (mikefarah) is required" >&2; exit 2; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

read -r -d '' ANALYSIS <<'JQ' || true
def triggers: (.on // .["true"] // {})
  | if type == "string" then [.] elif type == "array" then . elif type == "object" then keys else [] end;
def ci_triggered: triggers | any(. == "push" or . == "pull_request");
def stem: sub("\\.ya?ml$"; "");
def release_caller: [(.jobs // {})[]] as $jobs
  | ($jobs | length) > 0
    and all($jobs[]; (.uses // "" | sub("@.*$"; "")) as $u | ($rules.release_workflows | index($u)) != null);
($wfs[] as $w
 | ($w.file | stem) as $s
 | if ($w.doc | ci_triggered) then
     ([$ex[] | select(.workflow == $w.file)][0]) as $x
     | (if ($w.doc | release_caller) or ($x != null and $x.form == "event")
      then {kind: "event", group: "\($s)-${{ github.sha }}", cancel: false}
      elif $x != null
      then {kind: "queue", group: "\($s)-${{ github.ref }}", cancel: false}
      else {kind: "CI", group: "\($s)-${{ github.head_ref || github.ref }}", cancel: "${{ github.event_name == 'pull_request' }}"} end) as $e
     | $w.doc.concurrency as $c
     | "expected \($e.kind) form: group \($e.group | tojson), cancel-in-progress \($e.cancel | tojson)" as $want
     | if $c == null then "\($w.file): no workflow-level concurrency (\($want))"
       elif ($c | type) != "object" or $c.group != $e.group or $c["cancel-in-progress"] != $e.cancel
       then "\($w.file): concurrency \($c | tojson) (\($want))"
       else empty end
   elif ($w.doc | triggers) == ["workflow_call"] and $w.doc.concurrency != null
   then "\($w.file): reusable workflow declares workflow-level concurrency, which collides with its callers (declare it in the callers)"
   else empty end),
($ex[] as $x
 | [$wfs[] | select(.file == $x.workflow)][0] as $w
 | if $w == null then "exemption \($x.workflow): no such workflow"
   elif ($w.doc | ci_triggered | not) then "exemption \($x.workflow): not triggered by push or pull_request"
   elif ($w.doc | release_caller) then "exemption \($x.workflow): already a release by its uses: target"
   else empty end)
JQ

# parse_workflow <name> <yaml-file>: append {file, doc} to $tmp/docs.jsonl.
parse_workflow() {
  yq -o=json '.' "$2" | jq -c --arg f "$1" '{file:$f, doc:.}' >>"$tmp/docs.jsonl"
}

# evaluate <repo> <workflows.json> [<org-conformance.json>]: print ok or the repo's violations.
evaluate() {
  local repo=$1 wfs=$2 cfg=${3:-} ex='[]' out
  if [[ -n "$cfg" ]]; then
    if ! check_repo_config "$cfg" "FAIL $repo: $REPO_CONFIG"; then violations=1; return 0; fi
    ex=$(jq -cs '.[0].concurrency.exemptions // []' "$cfg")
  fi
  out=$(jq -rn --slurpfile rules "$RULES_FILE" --argjson ex "$ex" --slurpfile wfs "$wfs" \
    "\$rules[0] as \$rules | \$wfs[0] as \$wfs | $ANALYSIS") \
    || { echo "FAIL $repo: analysis error" >&2; errors=1; return 0; }
  if [[ -n "$out" ]]; then
    while IFS= read -r line; do echo "FAIL $repo: $line"; done <<<"$out"
    violations=1
  else
    echo "ok   $repo"
  fi
}

if [[ "$mode" == local ]]; then
  : >"$tmp/docs.jsonl"
  shopt -s nullglob
  for path in "$local_dir"/.github/workflows/*.yml "$local_dir"/.github/workflows/*.yaml; do
    parse_workflow "${path##*/}" "$path" || { echo "FAIL $repo_name: cannot parse ${path##*/}" >&2; exit 2; }
  done
  jq -cs . "$tmp/docs.jsonl" >"$tmp/workflows.json"
  cfg=""
  [[ -f "$local_dir/$REPO_CONFIG" ]] && cfg="$local_dir/$REPO_CONFIG"
  evaluate "$repo_name" "$tmp/workflows.json" "$cfg"
  ((errors)) && exit 2
  ((violations)) && exit 1
  exit 0
fi

fetch_workflows() { # <repo> -> JSON array of {file, doc}; return 2 on API failure
  local repo=$1 names f
  if ! $GH api "repos/$ORG/$repo/contents/.github/workflows" >"$tmp/list.json" 2>"$tmp/err"; then
    grep -q 'HTTP 404' "$tmp/err" && { echo '[]'; return 0; }
    echo "FAIL $repo: cannot list workflows: $(cat "$tmp/err")" >&2; return 2
  fi
  names=$(jq -r '.[]|select(.type=="file")|.name' "$tmp/list.json") \
    || { echo "FAIL $repo: unexpected workflow listing" >&2; return 2; }
  : >"$tmp/docs.jsonl"
  for f in $names; do
    case "$f" in *.yml | *.yaml) ;; *) continue ;; esac
    $GH api -H "Accept: application/vnd.github.raw+json" "repos/$ORG/$repo/contents/.github/workflows/$f" >"$tmp/wf.yml" 2>"$tmp/err" \
      || { echo "FAIL $repo: cannot read $f: $(cat "$tmp/err")" >&2; return 2; }
    parse_workflow "$f" "$tmp/wf.yml" || { echo "FAIL $repo: cannot parse $f" >&2; return 2; }
  done
  jq -cs . "$tmp/docs.jsonl"
}

fetch_repo_config() { # <repo> -> writes $tmp/repo-config.json, absent when the repo has none; return 2 on API failure
  rm -f "$tmp/repo-config.json"
  $GH api -H "Accept: application/vnd.github.raw+json" "repos/$ORG/$1/contents/$REPO_CONFIG" >"$tmp/repo-config.json" 2>"$tmp/err" \
    && return 0
  rm -f "$tmp/repo-config.json"
  grep -q 'HTTP 404' "$tmp/err" && return 0
  echo "FAIL $1: cannot read $REPO_CONFIG: $(cat "$tmp/err")" >&2; return 2
}

repos=$($GH repo list "$ORG" --limit 500 --no-archived --json name --jq '.[].name' 2>"$tmp/err") \
  || { echo "FAIL $ORG: cannot list repos: $(cat "$tmp/err")" >&2; exit 2; }

for repo in $repos; do
  if ! fetch_workflows "$repo" >"$tmp/workflows.json"; then errors=1; continue; fi
  if ! fetch_repo_config "$repo"; then errors=1; continue; fi
  cfg=""
  [[ -f "$tmp/repo-config.json" ]] && cfg="$tmp/repo-config.json"
  evaluate "$repo" "$tmp/workflows.json" "$cfg"
done

((errors)) && exit 2
((violations)) && exit 1
exit 0
