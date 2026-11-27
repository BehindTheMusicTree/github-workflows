# GitHub Workflows

This repository maintains reusable GitHub Actions workflows and composite actions. Follow [CONTRIBUTING.md](CONTRIBUTING.md) for GitHub Flow, testing, and changelog requirements. Changes to reusable workflows can affect all callers.

Run `actionlint` for workflow changes and the relevant tests in `.github/actions/*/tests/`. Before changing `.github/scripts/release.sh`, `CHANGELOG.md` or `VERSION`, or for any release, read `.agents/rules/releases-use-script.md` and follow the documented procedure for the repository's release configuration.
