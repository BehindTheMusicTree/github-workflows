# GitHub Workflows

Reusable GitHub Actions workflows for the BehindTheMusicTree organization.

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Table of Contents

- [Available Workflows](#available-workflows)
  - [Call Redeployment Webhook](#call-redeployment-webhook)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [With Dependencies](#with-dependencies)
- [Required Configuration](#required-configuration)
  - [Secrets](#secrets)
  - [Variables](#variables)
- [Setup Instructions](#setup-instructions)
- [Workflow Behavior](#workflow-behavior)
  - [Expected Webhook Response](#expected-webhook-response)
  - [Error Handling](#error-handling)
- [Webhook Endpoint](#webhook-endpoint)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Changelog](#changelog)
- [License](#license)

## Available Workflows

### Call Redeployment Webhook

A reusable workflow that triggers a server redeployment webhook. This workflow validates required configuration, verifies the environment, and calls the redeployment webhook endpoint.

**Workflow file:** `.github/workflows/call-redeployment-webhook.yml`

## Usage

### Basic Usage

Call this workflow from your repository's workflow:

```yaml
name: Release

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  call-redeployment-webhook:
    name: Call Redeployment Webhook
    uses: BehindTheMusicTree/github-workflows/.github/workflows/call-redeployment-webhook.yml@main
    with:
      env: "TEST"
    secrets: inherit
```

### With Dependencies

If you need to call the webhook after other jobs complete:

```yaml
jobs:
  build-and-push:
    name: Build and Push
    runs-on: ubuntu-latest
    steps:
      - name: Build
        run: echo "Building..."

  call-redeployment-webhook:
    name: Call Redeployment Webhook
    needs: [build-and-push]
    uses: BehindTheMusicTree/github-workflows/.github/workflows/call-redeployment-webhook.yml@main
    with:
      env: "TEST"
    secrets: inherit
```

## Required Configuration

**Note:** This repository (`github-workflows`) does not need any secrets or variables configured. It only contains the reusable workflow definition.

Each repository that **calls** this reusable workflow must configure the following secrets and variables in their GitHub repository settings (or organization settings) under the environment specified (e.g., `TEST`).

**Recommendation:** Since different repositories may deploy to different servers, configure these as **repository-level** secrets and variables by default. Use organization-level secrets/variables only if all repositories in your organization deploy to the same server/environment with identical configuration.

### Secrets

| Secret Name                   | Description                                                              | Example             |
| ----------------------------- | ------------------------------------------------------------------------ | ------------------- |
| `REDEPLOYMENT_WEBHOOK_PORT`   | Port the webhook service listens on                                      | `9000`              |
| `REDEPLOYMENT_HOOK_ID`        | Hook ID used in hooks.json and as path `/hooks/<id>` for the webhook URL | `bodzify-redeploy`  |
| `REDEPLOYMENT_WEBHOOK_SECRET` | Secret for webhook authentication (X-Secret header)                      | `your-secret-token` |

### Variables

| Variable Name | Description                                          | Example                          |
| ------------- | ---------------------------------------------------- | -------------------------------- |
| `DOMAIN_NAME` | Server hostname or IP address (used for webhook URL) | `example.com` or `192.168.1.100` |

## Setup Instructions

### 1. Configure Secrets and Variables

In each repository that calls this workflow, configure these secrets and variables at the **repository** level under the environment (e.g., `TEST`):

1. Go to your repository → **Settings** → **Environments** → **TEST** (or create it)
2. Add the required secrets and variables listed above

**Note:** If all repositories in your organization deploy to the same server, you can configure these at the **organization** level instead. Organization-level secrets/variables are inherited by all repositories, but repository-level settings override organization-level settings.

### 2. Add the Workflow Call

Add a job to your workflow file (e.g., `.github/workflows/release.yml`) that calls this reusable workflow:

```yaml
jobs:
  call-redeployment-webhook:
    name: Call Redeployment Webhook
    uses: BehindTheMusicTree/github-workflows/.github/workflows/call-redeployment-webhook.yml@main
    with:
      env: "TEST"
    secrets: inherit
```

### 3. Verify Access

Ensure your repository has access to use reusable workflows:

- For **public repositories**: No additional configuration needed
- For **private repositories**: The organization must allow reusable workflows from private repositories

## Workflow Behavior

The workflow performs the following steps:

1. **Check Required Configuration**: Validates that all required secrets and variables are set
2. **Verify Environment**: Ensures the environment is set to `TEST` (currently only TEST is supported)
3. **Call Webhook**: Sends a POST request to the webhook endpoint with authentication
4. **Validate Response**: Verifies the webhook response matches expected output

### Expected Webhook Response

The webhook endpoint should return:

- **Status Code**: `200 OK`
- **Response Body**: `Redeploying BTMT ecosystem`

### Error Handling

The workflow will fail with clear error messages if:

- Required secrets/variables are missing
- Environment is not `TEST`
- Webhook endpoint is unreachable (connection refused)
- Webhook returns an unexpected response
- Hook ID is not found (404 error)

## Webhook Endpoint

The workflow constructs the webhook URL as:

```
http://<DOMAIN_NAME>:<REDEPLOYMENT_WEBHOOK_PORT>/hooks/<REDEPLOYMENT_HOOK_ID>
```

For example, with:

- `DOMAIN_NAME`: `example.com`
- `REDEPLOYMENT_WEBHOOK_PORT`: `9000`
- `REDEPLOYMENT_HOOK_ID`: `bodzify-redeploy`

The URL would be: `http://example.com:9000/hooks/bodzify-redeploy`

## Troubleshooting

### "Workflow was not found" Error

- Ensure the repository is public (or your organization allows private repo access)
- Verify the workflow file exists on the `main` branch
- Check that the repository path is correct

### "Missing required config" Error

- Verify all required secrets are set in your environment
- Verify all required variables are set in your environment
- Check that the environment name matches (e.g., `TEST`)

### "Webhook call failed" Error

- Verify the webhook service is running on the server
- Check that the port is correct and accessible
- Ensure the hook ID matches what's configured in `hooks.json` on the server
- Verify the webhook secret matches `REDEPLOYMENT_WEBHOOK_SECRET`

### "Connection refused" Error

- Check that the webhook service is running: `systemctl status webhook`
- Verify the firewall allows the port: `ufw status` (if using ufw)
- Ensure the port in `REDEPLOYMENT_WEBHOOK_PORT` matches the server configuration

## Contributing

This repository contains reusable workflows for the BehindTheMusicTree organization.

For detailed contribution guidelines, including development workflow, branching strategy, and pull request process, see [CONTRIBUTING.md](CONTRIBUTING.md).

Quick start:

1. Create a feature branch
2. Make your changes
3. Test the workflow in a calling repository
4. Submit a pull request

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes, including version history, new features, bug fixes, and improvements.

## License

[Specify your license here]
