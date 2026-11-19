---
paths:
  - ".github/scripts/release.sh"
  - "CHANGELOG.md"
  - "VERSION"
---

# Releases Must Use Script

When the user asks for a "new release" (or equivalent wording), always use `.github/scripts/release.sh` from the repository root.

- Determine bump type (`major`, `minor`, or `patch`) from user intent.
- If bump type is unclear, ask a single clarifying question before running the script.
- Do not manually edit `CHANGELOG.md`, `VERSION`, create tags, or craft release commits as a substitute for the script.
- Run the script as the source of truth for release preparation steps.
- Open a PR against `main`; after merge, CI alone creates the tag and publishes the GitHub release. Do not run local `publish` when the release policy is present.

Release-please repositories (a `release-please-config.json` exists at the root) prepare releases differently:

- Do not run `release.sh` (it refuses) and do not edit `CHANGELOG.md`, `VERSION` or the manifest by hand.
- A release is the review and merge of the release PR that release-please opens or updates; propose it for confirmation like any release, then squash merge it with its title. CI alone creates the tag and publishes.

Examples:
- "new release" -> ask whether `major`, `minor`, or `patch`, then run `.github/scripts/release.sh <type>`.
- "cut a patch release" -> run `.github/scripts/release.sh patch`.
