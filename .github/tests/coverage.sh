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

# multi_report FILE=HITS... -> reports/cov.xml: 10 lines per file (HITS 1 covered, 0 not) plus a covered filler
multi_report() {
  mkdir -p reports && rm -f reports/*
  PYTHONIOENCODING=utf-8 python3 - "$@" > reports/cov.xml <<'PY'
import sys
from xml.sax.saxutils import quoteattr
classes = [('filler.py', 1, 300)] + [(a.rsplit('=', 1)[0], int(a.rsplit('=', 1)[1]), 10) for a in sys.argv[1:]]
out = []
for name, hits, count in classes:
    rows = ''.join(f'<line number="{n}" hits="{hits}" branch="true" condition-coverage="{100 if hits else 0}% ({1 if hits else 0}/1)"/>' for n in range(1, count + 1))
    out.append(f'<class filename={quoteattr(name)}><lines>{rows}</lines></class>')
print('<coverage><packages><package><classes>' + ''.join(out) + '</classes></package></packages></coverage>')
PY
}

# scenario BASE_FILE... -- CHANGED_FILE... : fresh repo with the base files committed, then the changed files
# (existing or new) rewritten and committed on a branch compared with origin/main.
scenario() {
  local f
  cd "$work" && rm -rf scenario && git init -q scenario && cd scenario
  git config user.email t@example.com && git config user.name t
  echo base > README.md
  while [ "$1" != -- ]; do mkdir -p "$(dirname "$1")" && seq 1 10 | sed 's/^/x = /' > "$1"; shift; done; shift
  git add . && git commit -q -m base
  git update-ref refs/remotes/origin/main HEAD
  git checkout -q -b change
  for f in "$@"; do mkdir -p "$(dirname "$f")" && seq 1 10 | sed 's/^/y = /' > "$f"; done
  git add . && git commit -q --allow-empty -m change
}

scenario -- new.py;                  multi_report other.py=1;           run_check fail 'new source file absent from the reports'
scenario -- new.py;                  multi_report new.py=1;             run_check pass 'new source file present in the reports'
scenario -- new.py;                  multi_report /app/other.py=1;      run_check fail 'new file flagged with out-of-workspace absolute report paths'
scenario -- tests/new.py;            multi_report other.py=1;           run_check pass 'new file outside the reported directories is not flagged'
scenario -- 'a*b.py';                multi_report 'a*b.py=1';           run_check pass 'path with glob characters'
scenario -- ;                        : > empty.py; git add . && git commit -q -m empty; multi_report other.py=1; run_check pass 'new empty file is not flagged'
scenario -- new.md;                  multi_report other.py=1;           run_check pass 'new non-source file is not flagged'
scenario old.py -- old.py;           multi_report other.py=1;           run_check pass 'modified file absent from the reports is skipped'
scenario util.py -- util.py;         multi_report api/util.py=1 web/util.py=1; run_check pass 'longer report paths collapse onto the tracked file'
scenario pkg/a/util.py pkg/b/util.py -- pkg/a/util.py; multi_report util.py=1; run_check fail 'ambiguous suffix match against tracked files'
grep -q 'matches several tracked files' "$work/out" || { echo 'FAIL: ambiguous suffix message' >&2; cat "$work/out" >&2; exit 1; }
scenario pkg/a/util.py -- pkg/a/util.py; multi_report util.py=0; run_check fail 'unique suffix match resolves the changed file'
scenario pkg/web/util.py -- pkg/web/util.py; multi_report util.py=0 web/util.py=1; run_check pass 'longest suffix match wins'
scenario web/util.py -- web/util.py; multi_report util.py=0 web/util.py=1; run_check pass 'exact match wins over a suffix match'
scenario 'dir é/a b.py' -- 'dir é/a b.py'; multi_report 'dir é/a b.py=0'; run_check fail 'uncovered changes in a path with spaces and non-ASCII'
scenario 'dir é/a b.py' -- 'dir é/a b.py'; multi_report 'dir é/a b.py=1'; run_check pass 'covered changes in a path with spaces and non-ASCII'
cobertura 10 10 yes; printf '<testsuites/>' > reports/junit.xml; run_check fail 'non-Cobertura XML in the reports'
grep -q 'not a Cobertura report' "$work/out" || { echo 'FAIL: non-Cobertura message' >&2; cat "$work/out" >&2; exit 1; }
cobertura 10 10 yes; printf '<coverage' > reports/bad.xml; run_check fail 'invalid XML in the reports'
grep -q 'not valid XML' "$work/out" || { echo 'FAIL: invalid XML message' >&2; cat "$work/out" >&2; exit 1; }
scenario util.py pkg/util.py -- pkg/util.py
multi_report util.py=1
sed -i.bak "s|<packages>|<sources><source>$(pwd -P)/pkg</source></sources><packages>|" reports/cov.xml; rm -f reports/cov.xml.bak
run_check pass 'source root resolves the covered file'
multi_report util.py=0
sed -i.bak "s|<packages>|<sources><source>$(pwd -P)/pkg</source></sources><packages>|" reports/cov.xml; rm -f reports/cov.xml.bak
run_check fail 'source root wins over a same-named file at the root'
echo 'all coverage tests passed'
