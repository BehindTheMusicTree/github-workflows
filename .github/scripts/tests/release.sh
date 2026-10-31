#!/usr/bin/env bash
set -euo pipefail
script="$(cd "$(dirname "$0")/.." && pwd)/release.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git init --bare -q "$tmp/remote.git"
git init -q -b main "$tmp/work"
cd "$tmp/work"
git config user.email test@example.com
git config user.name Test
git remote add origin "$tmp/remote.git"
printf '1.0.0\n' > VERSION
printf '# Changelog\n\n## [Unreleased]\n\n### Added\n\n- New behavior.\n\n## [1.0.0] - 2026-01-01\n' > CHANGELOG.md
git add VERSION CHANGELOG.md
git commit -qm initial
git push -q -u origin main
git checkout -qb release-test
bash "$script" minor
[[ "$(cat VERSION)" == '1.1.0' ]]
[[ -z "$(git tag -l v1.1.0)" ]]
if bash "$script" publish; then
  echo 'Publishing from a feature branch should fail' >&2
  exit 1
fi
git checkout -q main
git merge -q --ff-only release-test
git push -q origin main
bash "$script" publish
[[ "$(git rev-parse v1.1.0)" == "$(git rev-parse origin/main)" ]]
[[ "$(git ls-remote origin refs/tags/v1.1.0 | cut -f1)" == "$(git rev-parse HEAD)" ]]
if bash "$script" publish; then
  echo 'Publishing an existing tag should fail' >&2
  exit 1
fi
