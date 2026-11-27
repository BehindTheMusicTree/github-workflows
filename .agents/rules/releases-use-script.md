# Release preparation

This repository uses Release Please. The script procedure below applies to legacy callers without a root `release-please-config.json`.

- Determine bump type (`major`, `minor`, or `patch`) from user intent.
- If bump type is unclear, ask a single clarifying question before running the script.
- Do not manually edit `CHANGELOG.md`, `VERSION`, create tags, or craft release commits as a substitute for the script.
- Run the script as the source of truth for release preparation steps.
- Open a PR against `main`; after merge, CI alone creates the tag and publishes the GitHub release. Do not run local `publish` when the release policy is present.

Release-please repositories (a `release-please-config.json` exists at the root) prepare releases differently:

- Do not run `release.sh` (it refuses) and do not edit `CHANGELOG.md`, `VERSION` or the manifest by hand.
- A release is the review and merge of the release PR that release-please opens or updates; propose it for confirmation like any release, then squash merge it with its title. CI alone creates the tag and publishes.
- Exception: for a repository declared `release_pr` in `github-config`'s `release-automation.json`, the `release-please` job of its caller sets `auto-merge: true`, and CI merges the release PR itself (squash only, `pr-title / check` required). Merging a `feat:`/`fix:` PR there therefore starts a release without a further confirmation: do not merge the release PR yourself, report the expected publication instead, and choose the PR title carefully since it sets the version (`!` for a breaking change).
- If auto-merge is refused or stays blocked, never merge the release PR directly without the user's agreement.
- The exception covers only that auto-merge. Releases made with `release.sh`, pin bumps, manual tags and other repositories keep the confirmation rule above.

Examples for legacy script callers:
- "new release" -> ask whether `major`, `minor`, or `patch`, then run `.github/scripts/release.sh <type>`.
- "cut a patch release" -> run `.github/scripts/release.sh patch`.
