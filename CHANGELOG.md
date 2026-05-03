# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Changelog Best Practices

### General Principles

- Changelogs are for humans, not machines.
- Include an entry for every version, with the latest first.
- Group similar changes under: Added, Changed, Improved, Deprecated, Removed, Fixed, Documentation, Performance, CI.
- **"Test" is NOT a valid changelog category** - tests should be mentioned within the related feature or fix entry, not as standalone entries.
- Use an "Unreleased" section for upcoming changes.
- Follow Semantic Versioning where possible.
- Use ISO 8601 date format: YYYY-MM-DD.
- Avoid dumping raw git logs; summarize notable changes clearly.

### Guidelines for Contributors

All contributors (including maintainers) should update `CHANGELOG.md` when creating PRs:

1. **Add entries to the `[Unreleased]` section** - Add your changes under the appropriate category (Added, Changed, Improved, Deprecated, Removed, Fixed, Documentation, Performance, CI)
2. **Follow the changelog format** - See examples below for structure and style
3. **Group related changes** - Similar changes should be grouped together
4. **Be descriptive** - Write clear, user-focused descriptions of what changed
5. **Mention tests when relevant** - Tests should be mentioned within the related feature or fix entry, not as standalone entries
6. **Category order** - Use this order in each version section: Added, Changed, Improved, Deprecated, Removed, Fixed, Documentation, Performance, CI (omit empty)

**Example:**

```markdown
### Added

- **Redeployment Webhook**: Added support for prod environment
  - New environment input validation and webhook URL construction

### Fixed

- **Configuration Check**: Fixed script handling of empty variable values
  - Script now properly detects unset variables vs empty strings

### CI

- **Workflow**: Added workflow_dispatch trigger for manual testing
  - Allows manual testing of webhook calls from GitHub Actions UI
```

**Note:** During releases, maintainers will move entries from `[Unreleased]` to a versioned section (e.g., `## [0.2.0] - 2025-02-XX`).

## [Unreleased]

## [1.0.1] - 2026-05-03


### Fixed

- **release.sh**: Release bumps now use the semver-wise maximum of **`VERSION`** and the latest matching **`v*.*.*`** tag as the current version (instead of the file alone). Emits a warning when **`VERSION`** lags behind tags so patch/minor bumps match published releases and the summary reflects the real base.

## [1.0.0] - 2026-05-03


- **call-redeployment-webhook**: Rename _`REDEPLOYMENT_HOOK_ID_BASE`_ to _`BTMT_REDEPLOYMENT_HOOK_ID_BASE`_ for BTMT stack.

## [0.3.0] - 2026-05-02

### Changed

- **call-redeployment-webhook** (**breaking**): BTMT stack webhook secrets renamed from **`REDEPLOYMENT_WEBHOOK_SECRET_{PROD,STAGING}`** to **`BTMT_REDEPLOYMENT_WEBHOOK_SECRET_{PROD,STAGING}`** in **`workflow_call`** / **`workflow_dispatch`**. **`TMD_ADMIN_WEBHOOK_SECRET_*`** and hook selection by **`hook_id_base`** are unchanged. Callers must rename GitHub secrets (same values) and bump **`uses:`** to **`@v0.3.0`**.

## [0.2.0] - 2026-05-02

### Changed

- **call-redeployment-webhook** (**breaking**): Input **`hook_id_base`** is **required** (trimmed non-empty). URL is always **`/hooks/<hook_id_base>-<env>`**. **`X-Secret`** is **`TMD_ADMIN_WEBHOOK_SECRET_<env>`** when **`hook_id_base`** equals **`vars.TMD_ADMIN_REDEPLOYMENT_HOOK_ID_BASE`** (both trimmed, TMD var non-empty); otherwise **`REDEPLOYMENT_WEBHOOK_SECRET_<env>`**. Removed **`redeployment_webhook_secret`**. Callers must pass **`hook_id_base`** (e.g. **`${{ vars.REDEPLOYMENT_HOOK_ID_BASE }}`** for BTMT, **`${{ vars.TMD_ADMIN_REDEPLOYMENT_HOOK_ID_BASE }}`** for **The Music Deck admin** on infrastructure). **`secrets: inherit`** is enough for infrastructure’s second job. Unknown hook id still fails at the server (**404** / body check).

## [0.1.7] - 2026-05-02

### Added

- **call-redeployment-webhook** (`workflow_call` / `workflow_dispatch`): Optional input **`hook_id_base`** and optional secret **`redeployment_webhook_secret`**. When **`hook_id_base`** is non-empty after trim, the workflow validates **`SERVER_HOST`**, **`REDEPLOYMENT_WEBHOOK_PORT`**, **`hook_id_base`**, and **`redeployment_webhook_secret`**, then POSTs **`/hooks/<hook_id_base>-<env>`** with **`X-Secret`** from **`redeployment_webhook_secret`** (same **`Redeployment accepted`** body check). **BehindTheMusicTree/infrastructure** uses this for **The Music Deck admin** staging after **`provision`**, passing **`hook_id_base`** from **`TMD_ADMIN_REDEPLOYMENT_HOOK_ID_BASE`**. BTMT callers stay unchanged: omit **`hook_id_base`** (or pass empty) and use **`secrets: inherit`** with **`REDEPLOYMENT_HOOK_ID_BASE`** / **`REDEPLOYMENT_WEBHOOK_SECRET_*`**. Declared **`workflow_call`** secrets: **`REDEPLOYMENT_WEBHOOK_PORT`**, **`REDEPLOYMENT_WEBHOOK_SECRET_PROD`**, **`REDEPLOYMENT_WEBHOOK_SECRET_STAGING`**, **`redeployment_webhook_secret`** (all optional for **`inherit`**; TMD-only callers pass **`REDEPLOYMENT_WEBHOOK_PORT`** + **`redeployment_webhook_secret`** explicitly).

## [0.1.5] - 2026-04-28

### CI

- **Release process**: Added a Cursor project rule to always run `.github/scripts/release.sh` when the user asks for a new release

## [0.1.4] - 2026-04-28

### Documentation

- **Variable naming**: Replaced the last `VPS_IP` reference in docs/changelog with `SERVER_HOST` for consistent terminology

## [0.1.3] - 2026-04-18

### Changed

- **call-redeployment-webhook**: Standardized on `SERVER_HOST` variable naming for consistency across workflows

## [0.1.2] - 2026-04-18

### Added

- **Staging vs prod only**: `call-redeployment-webhook` and `set-image-tag-on-server` accept `env: prod` or `env: staging` only (no `test`). Staging uses `REDEPLOYMENT_WEBHOOK_SECRET_STAGING` and hook path `...-staging`. GitHub **Environments** should be `staging` and `prod`.

### Changed

- **Webhook URL construction**: Host IP variable is now named `SERVER_HOST` instead of `VPS_IP`.

- **Webhook and SSH use SERVER_HOST**: call-redeployment-webhook and set-image-tag-on-server now use variable **SERVER_HOST** (instead of DOMAIN_NAME) for the webhook URL host and SSH destination. Use when the main domain points elsewhere (e.g. Vercel). Callers must set **SERVER_HOST** in the environment (repo or org variables).

- **Webhook ID**: REDEPLOYMENT_HOOK_ID is no longer a secret but now a var

- **Set image tag on server**: Input renamed `service` → `app_name`, now required (no default)
  - Callers must pass explicit service/app name (e.g. htmt-api, htmt-db, afp); filename on server is `${app_name}-tag`
  - Updated workflow comment and tag description examples

### CI

- **Release automation**: Added `.github/scripts/release.sh` and `VERSION` file to automate release chores
  - Script inserts the release section under `[Unreleased]`, bumps `VERSION`, commits, tags, and pushes the tag

## [0.1.1] - 2025-02-17

### Changed

- **Configuration Check**: Replaced script-based validation with inline bash in workflow
  - Workflow now validates required secrets/variables directly without requiring script file
  - Fixes issue where script was unavailable when workflow called from other repositories
  - Removed dependency on `checkout` action in check-required-config job
- **Webhook Secret**: Renamed `TEST_SERVER_REDEPLOYMENT_WEBHOOK_SECRET` to `REDEPLOYMENT_WEBHOOK_SECRET`
  - More generic naming that works across environments
  - Updated workflow and documentation to reflect new name

### Removed

- **Configuration Check Script**: Removed `.github/scripts/check-required-config.sh`
  - No longer needed since validation is now inline in the workflow
  - Script was not accessible when workflow called from other repositories

### Documentation

- **README**: Clarified secret and variable configuration
  - Added note that this repository doesn't need secrets/variables configured
  - Updated guidance to recommend repository-level secrets by default
  - Clarified that calling repositories must configure secrets/variables
  - Improved setup instructions with clearer organization vs repository level guidance
  - Added manual webhook call example with curl command for testing

## [0.1.0] - 2025-02-01

### Added

- **Call Redeployment Webhook Workflow**: Reusable GitHub Actions workflow for triggering server redeployment webhooks
  - Supports both `workflow_dispatch` (manual trigger) and `workflow_call` (reusable workflow)
  - Validates required configuration (secrets and variables) before proceeding
  - Verifies environment is set to `test` (currently only test environment supported)
  - Calls redeployment webhook endpoint with authentication
  - Validates webhook response matches expected output
  - Provides clear error messages for common failure scenarios
- **Configuration Check Script**: `.github/scripts/check-required-config.sh` for validating required secrets and variables
  - Accepts arguments in format `s:NAME` (secret) or `v:NAME` (variable)
  - Reports missing configuration with clear error messages
  - Supports both command-line arguments and stdin input

### Documentation

- **README**: Comprehensive documentation for reusable workflows
  - Usage examples (basic and with dependencies)
  - Required configuration (secrets and variables tables)
  - Setup instructions
  - Workflow behavior and error handling details
  - Webhook endpoint construction
  - Troubleshooting guide
  - Contributing guidelines
- **CHANGELOG**: Initial changelog following Keep a Changelog format with contributor guidelines
