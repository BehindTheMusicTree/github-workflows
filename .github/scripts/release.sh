#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: .github/scripts/release.sh <major|minor|patch|publish>

Example:
  .github/scripts/release.sh patch
  .github/scripts/release.sh minor

This script:
  0) Computes next semver from max(VERSION, latest vMAJOR.MINOR.PATCH tag) using bump type
  1) Adds a new release section under [Unreleased] in CHANGELOG.md
  2) Bumps VERSION
  3) Creates a commit
  4) Leaves the commit on the current feature branch for a PR

After that PR merges, run publish on updated main to tag and push the merged commit.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -ne 1 ]]; then
  usage
  exit 1
fi

bump_type="$1"
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [[ "$bump_type" == "publish" ]]; then
  if [[ "$(git branch --show-current)" != "main" ]] || [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: publish requires a clean main checkout." >&2
    exit 1
  fi
  git fetch origin main --tags
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
    echo "ERROR: main must match origin/main before publishing." >&2
    exit 1
  fi
  version="$(tr -d '[:space:]' < VERSION)"
  if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || ! grep -Fq "## [$version] - " CHANGELOG.md; then
    echo "ERROR: VERSION must match a versioned changelog entry." >&2
    exit 1
  fi
  tag="v${version}"
  if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
    echo "ERROR: tag ${tag} already exists; verify it before retrying." >&2
    exit 1
  fi
  git tag "$tag" HEAD
  git push origin "refs/tags/$tag"
  echo "Published $tag at $(git rev-parse HEAD)"
  exit 0
fi

if [[ "$bump_type" != "major" && "$bump_type" != "minor" && "$bump_type" != "patch" ]]; then
  echo "ERROR: argument must be one of: major, minor, patch (got: '$bump_type')."
  exit 1
fi

if [[ "$(git branch --show-current)" == "main" ]] || [[ -z "$(git branch --show-current)" ]]; then
  echo "ERROR: prepare the release on a feature branch for a PR." >&2
  exit 1
fi

if [[ ! -f CHANGELOG.md ]]; then
  echo "ERROR: CHANGELOG.md not found at repo root."
  exit 1
fi

if [[ ! -f VERSION ]]; then
  echo "ERROR: VERSION not found at repo root."
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: git working tree is not clean. Commit/stash changes first."
  exit 1
fi

current_version="$(tr -d '[:space:]' < VERSION)"
if [[ -z "$current_version" ]]; then
  echo "ERROR: VERSION is empty."
  exit 1
fi

if [[ ! "$current_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: VERSION must contain semver MAJOR.MINOR.PATCH (got: '$current_version')."
  exit 1
fi

latest_tag="$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | sort -V | tail -n1)"
latest_tag_version=""
if [[ -n "$latest_tag" ]]; then
  latest_tag_version="${latest_tag#v}"
  if [[ ! "$latest_tag_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    latest_tag_version=""
    latest_tag=""
  fi
fi

effective_version="$current_version"
if [[ -n "$latest_tag_version" ]]; then
  effective_version="$(printf '%s\n%s' "$current_version" "$latest_tag_version" | sort -V | tail -n1)"
fi

if [[ "$effective_version" != "$current_version" ]]; then
  echo "WARNING: VERSION file (${current_version}) is behind latest tag (${latest_tag} -> ${latest_tag_version})." >&2
  echo "WARNING: Release bump uses ${effective_version} as the current version (keep VERSION in sync with tags)." >&2
fi

IFS='.' read -r major minor patch <<< "$effective_version"
case "$bump_type" in
  major)
    major=$((major + 1))
    minor=0
    patch=0
    ;;
  minor)
    minor=$((minor + 1))
    patch=0
    ;;
  patch)
    patch=$((patch + 1))
    ;;
esac

version="${major}.${minor}.${patch}"
tag="v${version}"

if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
  echo "ERROR: tag ${tag} already exists locally."
  exit 1
fi

release_date="$(date +%Y-%m-%d)"
tmp_changelog="$(mktemp)"

set +e
awk -v version="$version" -v release_date="$release_date" '
  BEGIN {
    inserted = 0
    in_unreleased = 0
    moved_content = 0
  }
  {
    if (!inserted && $0 ~ /^## \[Unreleased\]/) {
      print $0
      print ""
      print "## [" version "] - " release_date
      print ""
      inserted = 1
      in_unreleased = 1
      next
    }

    if (in_unreleased) {
      if ($0 ~ /^## \[/) {
        in_unreleased = 0
        print $0
        next
      }

      if ($0 ~ /[^[:space:]]/) {
        moved_content = 1
      }
      print $0
      next
    }

    print $0
  }
  END {
    if (!inserted) {
      exit 2
    }
    if (!moved_content) {
      exit 3
    }
  }
' CHANGELOG.md > "$tmp_changelog"
awk_status=$?
set -e

if [[ $awk_status -eq 2 ]]; then
  rm -f "$tmp_changelog"
  echo "ERROR: could not find '## [Unreleased]' in CHANGELOG.md."
  exit 1
fi

if [[ $awk_status -eq 3 ]]; then
  rm -f "$tmp_changelog"
  echo "ERROR: [Unreleased] has no content to release."
  exit 1
fi

if [[ $awk_status -ne 0 ]]; then
  rm -f "$tmp_changelog"
  echo "ERROR: failed to update CHANGELOG.md."
  exit 1
fi

mv "$tmp_changelog" CHANGELOG.md
printf '%s\n' "$version" > VERSION

git add CHANGELOG.md VERSION
git commit -m "chore(release): ${tag}"

echo "Release prepared."
echo "- Version: ${effective_version} -> ${version} (VERSION file before bump: ${current_version})"
echo "- Commit created locally: chore(release): ${tag}"
echo "- Open a PR to main, then run .github/scripts/release.sh publish on updated main."