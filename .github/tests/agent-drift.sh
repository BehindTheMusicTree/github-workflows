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
