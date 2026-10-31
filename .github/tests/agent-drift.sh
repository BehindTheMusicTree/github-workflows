#!/usr/bin/env bash
set -euo pipefail

engine="${1:?provide the path to check-project-agents.py}"
fixture="$(mktemp -d "${TMPDIR:-/tmp}/agent drift.XXXXXX")"
trap 'rm -rf "$fixture"' EXIT
printf '# Instructions\n' > "$fixture/AGENTS.md"
printf '@AGENTS.md\n' > "$fixture/CLAUDE.md"
mkdir -p "$fixture/.agents/skills/example" "$fixture/.claude/skills"
printf '%s\n' 'Example skill' > "$fixture/.agents/skills/example/SKILL.md"
ln -s ../../.agents/skills/example "$fixture/.claude/skills/example"
python3 "$engine" "$fixture"
printf '%s\n' 'extra instruction' >> "$fixture/CLAUDE.md"
if python3 "$engine" "$fixture"; then
  echo 'Drift was not detected' >&2
  exit 1
fi
printf '@AGENTS.md\n' > "$fixture/CLAUDE.md"
mkdir -p "$fixture/.agents/rules" "$fixture/.claude/rules"
printf '%s\n' 'Python rule' > "$fixture/.agents/rules/python.md"
printf '%s\n' '{"python":{"source":".agents/rules/python.md","paths":["**/*.py"]}}' > "$fixture/.agents/scopes.json"
printf '%s\n' 'Read .agents/rules/python.md for **/*.py' >> "$fixture/AGENTS.md"
printf '%s\n' '---' 'paths:' '  - "**/*.py"' '---' '' 'Python rule' > "$fixture/.claude/rules/python.md"
python3 "$engine" "$fixture"
printf '%s\n' 'modified rule' > "$fixture/.claude/rules/python.md"
if python3 "$engine" "$fixture"; then
  echo 'Scoped rule drift was not detected' >&2
  exit 1
fi
