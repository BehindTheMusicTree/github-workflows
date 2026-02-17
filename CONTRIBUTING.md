# Contributing Guidelines

Thank you for your interest in contributing!
This project is currently maintained by a solo developer, but contributions, suggestions, and improvements are welcome.

## Table of Contents

- [Contributors vs Maintainers](#contributors-vs-maintainers)
  - [Roles Overview](#roles-overview)
  - [Infrastructure & Automation Permissions](#infrastructure--automation-permissions)
- [Development Workflow](#development-workflow)
  - [0. Fork & Clone](#0-fork--clone)
  - [1. Branching (GitHub Flow)](#1-branching-github-flow)
  - [2. Developing](#2-developing)
  - [3. Testing](#3-testing)
  - [4. Committing](#4-committing)
  - [5. Pull Request Process](#5-pull-request-process)
    - [5.1. Pre-PR Checklist](#51-pre-pr-checklist)
    - [5.2. Opening a Pull Request](#52-opening-a-pull-request)
  - [6. Releasing _(For Maintainers)_](#6-releasing-for-maintainers)
- [License & Attribution](#license--attribution)
- [Code of Conduct](#code-of-conduct)
- [Contact & Discussions](#contact--discussions)

## Contributors vs Maintainers

### Roles Overview

**Contributors**

Anyone can be a contributor by:

- Submitting bug reports or feature requests via GitHub Issues
- Proposing code changes through Pull Requests
- Improving documentation (README, CHANGELOG)
- Participating in discussions
- Testing workflows and scripts and giving feedback

**Maintainers**

The maintainer(s) are responsible for:

- Reviewing and merging Pull Requests
- Managing releases and versioning
- Ensuring code quality and project direction
- Responding to critical issues
- Maintaining the project's infrastructure (GitHub Actions)
- Moving "Unreleased" changelog entries to versioned sections during releases

**Important:** Even maintainers must go through Pull Requests. No direct commits to `main` are allowed — all changes, including those from maintainers, must be submitted via Pull Requests and go through the standard review process.

### Infrastructure & Automation Permissions

**Repository automation (maintainer-only):**

- Reusable workflows (`.github/workflows/`) — changes affect all repositories that call these workflows
- Changes to these workflows affect CI behavior across multiple repositories; contributors can suggest changes via PRs

**What contributors can do:**

- Propose changes to workflows, scripts, and docs via Pull Requests
- Report issues or suggest improvements via GitHub Issues
- Update CHANGELOG in the `[Unreleased]` section when contributing

**What contributors cannot do:**

- Merge PRs or push directly to `main`
- Modify repository or environment secrets/variables (maintainer-only)

Currently, this project has a solo maintainer, but the role may expand as the project grows.

## Development Workflow

We follow **GitHub Flow**: a single long-lived `main` branch plus short-lived feature/chore branches. All changes land via Pull Requests.

**Workflow steps:** Fork & Clone → Branching → Developing → Testing → Committing → Pull Request Process (including Pre-PR Checklist) → Releasing _(For Maintainers)_

### 0. Fork & Clone

**For contributors:**

1. Fork the repository on GitHub
2. Clone your fork:

   ```bash
   git clone https://github.com/YOUR-USERNAME/github-workflows.git
   cd github-workflows
   ```

**For maintainers:**

Clone the main repository directly:

```bash
git clone https://github.com/BehindTheMusicTree/github-workflows.git
cd github-workflows
```

### 1. Branching (GitHub Flow)

We use **GitHub Flow**: one main branch (`main`) and topic branches. No `develop` or long-lived release branches.

#### Main Branch (`main`)

- The stable, deployable branch
- All changes enter via Pull Request
- **No direct commits allowed** — including from maintainers

#### Feature Branches (`feature/<name>`)

- Use for new features or enhancements
- Include issue numbers when applicable: `feature/123-add-prod-environment`
- Examples:

  ```bash
  git checkout -b feature/add-prod-environment-support
  git checkout -b feature/123-add-webhook-retry
  ```

- Merge into `main` via Pull Request when ready

#### Chore Branches (`chore/<name>`)

- Use for maintenance, config, and docs
- Examples:

  ```bash
  git checkout -b chore/update-readme
  git checkout -b chore/align-changelog
  ```

- Merge into `main` via Pull Request when ready

### 2. Developing

- **Workflows:** Edit YAML in `.github/workflows/` (e.g. `call-redeployment-webhook.yml`). Ensure required vars and secrets are documented in README.
- **Docs:** Update [README.md](README.md) or [CHANGELOG.md](CHANGELOG.md) when you change behavior or add setup steps.

### 3. Testing

- **Workflows:** If you have access to a test environment, run the reusable workflow from a calling repository and confirm jobs succeed. Otherwise, ensure YAML is valid and steps are consistent with README/docs.
- **Docs:** Proofread and check that links and secret/variable names match the codebase.

### 4. Committing

- Use **concise** commit messages with a **type prefix** (e.g. `feat:`, `fix:`, `docs:`, `chore:`).
- Prefer one logical change per commit; use multiple commits in a PR if it helps review.
- Examples:
  - `feat: add prod environment support to redeploy webhook`
  - `docs: add webhook call vars/secrets reference`
  - `fix: handle empty variable values in config check`
  - `chore: align changelog Unreleased`

### 5. Pull Request Process

#### 5.1. Pre-PR Checklist

Before submitting a Pull Request:

**1. Code / Config**

- Workflows and scripts are consistent with README
- No secrets or sensitive values committed (use GitHub secrets/variables)
- Paths and env names match what's documented

**2. Documentation**

- [README.md](README.md) updated if you changed behavior or setup
- [CHANGELOG.md](CHANGELOG.md) updated: add your changes under the `[Unreleased]` section (see [Changelog Best Practices](CHANGELOG.md#changelog-best-practices))

**3. Git**

- Branch is up to date with `main` (rebase or merge as needed)
- No stray files or unrelated changes

#### 5.2. Opening a Pull Request

- **Title:** Short, imperative; **always use a type prefix** (`feat:`, `fix:`, `docs:`, `chore:`), same as commit messages (e.g. `feat: add prod environment support`, `docs: document webhook vars and secrets`).
- **Description:** What changed and why; link related issues if any.
- **Target:** Branch should target `main`.

After opening the PR, maintainers will review and may request changes. Once approved, a maintainer will merge.

### 6. Releasing _(For Maintainers)_

Releases are made from `main`.

1. **Ensure you're on `main` and up to date**

   ```bash
   git checkout main
   git pull origin main
   ```

2. **Update [CHANGELOG.md](CHANGELOG.md)**
   - Move entries from `[Unreleased]` into a new versioned section (e.g. `## [0.2.0] - YYYY-MM-DD`).
   - Follow [Semantic Versioning](https://semver.org/).

3. **Tag and push**

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. **Create a GitHub Release** (optional) from the tag and paste the changelog section for that version.

## License & Attribution

All contributions are made under the project's open-source license. You keep authorship of your code; the project keeps redistribution rights under the same license.

## Code of Conduct

This project aims to provide a welcoming and inclusive environment. Please be respectful and constructive when participating (issues, PRs, discussions).

## Contact & Discussions

- **Issues** — bug reports, feature requests, or questions
- **Pull Requests** — proposed changes

For setup and usage, see [README.md](README.md).

Thank you for contributing.
