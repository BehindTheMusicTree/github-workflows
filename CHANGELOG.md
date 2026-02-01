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
## [Unreleased]

### Added

- **Redeployment Webhook**: Added support for PROD environment
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

### Changed

- **Configuration Check**: Replaced script-based validation with inline bash in workflow
  - Workflow now validates required secrets/variables directly without requiring script file
  - Fixes issue where script was unavailable when workflow called from other repositories
  - Removed dependency on `checkout` action in check-required-config job
- **Webhook Secret**: Renamed `TEST_SERVER_REDEPLOYMENT_WEBHOOK_SECRET` to `REDEPLOYMENT_WEBHOOK_SECRET`
  - More generic naming that works across environments
  - Updated workflow and documentation to reflect new name

### Documentation

- **README**: Clarified secret and variable configuration
  - Added note that this repository doesn't need secrets/variables configured
  - Updated guidance to recommend repository-level secrets by default
  - Clarified that calling repositories must configure secrets/variables
  - Improved setup instructions with clearer organization vs repository level guidance

## [0.1.0] - 2025-02-01

### Added

- **Call Redeployment Webhook Workflow**: Reusable GitHub Actions workflow for triggering server redeployment webhooks
  - Supports both `workflow_dispatch` (manual trigger) and `workflow_call` (reusable workflow)
  - Validates required configuration (secrets and variables) before proceeding
  - Verifies environment is set to `TEST` (currently only TEST environment supported)
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
