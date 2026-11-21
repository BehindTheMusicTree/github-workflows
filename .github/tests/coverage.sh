#!/usr/bin/env bash
# Fixture tests for the inline checker of .github/workflows/coverage.yml.
set -euo pipefail

workflow="$(cd "$(dirname "$0")/.." && pwd)/workflows/coverage.yml"
work="$(mktemp -d "${TMPDIR:-/tmp}/coverage-test.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# The checker is the heredoc body of the "Check coverage standard" step, indented by 10 spaces.
awk "/python3 - <<'PY'/{on=1;next} on&&/^ *PY\$/{exit} on{sub(/^ {10}/,\"\");print}" "$workflow" > "$work/check.py"
[ -s "$work/check.py" ] || { echo 'could not extract the checker' >&2; exit 1; }

cd "$work"
git init -q repo && cd repo
git config user.email t@example.com && git config user.name t
seq 1 10 | sed 's/^/x = /' > src.py
git add . && git commit -q -m base
git update-ref refs/remotes/origin/main HEAD
git checkout -q -b change
seq 1 10 | sed 's/^/y = /' > src.py
git commit -qam change

# cobertura LINES_COVERED(of 10) BRANCHES_COVERED(of 10) -> reports/cov.xml
cobertura() {
  mkdir -p reports && rm -f reports/*
  python3 - "$1" "$2" "$3" > reports/cov.xml <<'PY'
import sys
cov, br, with_branches = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3] == 'yes'
rows = []
for n in range(1, 11):
    cond = f' branch="true" condition-coverage="{"100" if n <= br else "0"}% ({1 if n <= br else 0}/1)"' if with_branches else ''
    rows.append(f'<line number="{n}" hits="{1 if n <= cov else 0}"{cond}/>')
print('<coverage><packages><package><classes><class filename="src.py"><lines>' + ''.join(rows) + '</lines></class></classes></package></packages></coverage>')
PY
}

# run_check EXPECT(pass|fail) NAME [ENV=VALUE...]
run_check() {
  local expect="$1" name="$2"; shift 2
  local status=0
  env LINE=80 BRANCH=70 PATCH=90 BASE_REF=main REPORTS_DIR=reports "$@" python3 "$work/check.py" > "$work/out" 2>&1 || status=$?
  if { [ "$expect" = pass ] && [ "$status" -ne 0 ]; } || { [ "$expect" = fail ] && [ "$status" -eq 0 ]; }; then
    echo "FAIL: $name (expected $expect, exit $status)" >&2
    cat "$work/out" >&2
    exit 1
  fi
  echo "ok: $name"
}

cobertura 10 10 yes; run_check pass 'above thresholds'
cobertura 7 10 yes;  run_check fail 'line coverage below 80'
cobertura 10 5 yes;  run_check fail 'branch coverage below 70'
cobertura 10 10 no;  run_check fail 'no branch data'
cobertura 8 10 yes;  run_check fail 'patch coverage below 90 (all lines changed, 80% covered)'
cobertura 8 10 yes;  run_check pass 'patch skipped without a base ref' BASE_REF=
cobertura 10 10 yes; run_check fail 'lowered line threshold' LINE=50
cobertura 10 10 yes; run_check fail 'lowered branch threshold' BRANCH=10
cobertura 10 10 yes; run_check fail 'lowered patch threshold' PATCH=0
cobertura 10 10 yes; run_check pass 'raised threshold' LINE=95
rm -rf reports; mkdir reports;  run_check fail 'no report'
printf 'SF:src.py\nDA:1,1\nDA:2,1\nBRDA:1,0,0,1\nBRDA:1,0,1,1\nend_of_record\n' > reports/lcov.info
run_check pass 'lcov report' PATCH=90 BASE_REF=
echo 'all coverage tests passed'
