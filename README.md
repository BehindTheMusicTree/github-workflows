# GitHub Workflows

Reusable GitHub Actions workflows for the BehindTheMusicTree organization.

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Table of Contents

- [Available Workflows](#available-workflows)
  - [Call Redeployment Webhook](#call-redeployment-webhook)
  - [Deploy App Env File](#deploy-app-env-file)
  - [Deploy Nginx Env Fragment](#deploy-nginx-env-fragment)
  - [Deploy Partial Docker Compose](#deploy-partial-docker-compose)
- [Usage](#usage)
  - [Call Redeployment Webhook](#call-redeployment-webhook-usage)
  - [Deploy workflows (caller examples)](#deploy-workflows-caller-examples)
- [Required Configuration](#required-configuration)
  - [Webhook (call-redeployment-webhook)](#webhook-call-redeployment-webhook)
  - [Deploy workflows](#deploy-workflows)
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

Triggers a server redeployment webhook. Validates configuration, ensures `env` is `test` or `prod`, and POSTs to the webhook (optional JSON image overrides in body). Response must start with `Redeploying BTMT ecosystem`.

**Workflow file:** `.github/workflows/call-redeployment-webhook.yml`

| Input   | Required | Description |
|--------|----------|-------------|
| `env`  | Yes      | `test` or `prod` (lowercase) |
| `images` | No     | Optional JSON object of image overrides (e.g. `{"gateway_image": "user/repo:tag"}`). Default `{}`. |

### Deploy App Env File

Uploads compose env files to `pool/compose/<app_name>/` on the server. Caller must upload an artifact (e.g. `app-env-files`) containing env files. Use **non-dotfile names** in the artifact (e.g. `env_api`, `env_gtmt_front`) so `upload-artifact` includes them; this workflow renames them to dotfiles (e.g. `.env_api`) before uploading.

**Workflow file:** `.github/workflows/deploy-app-env-file.yml`

| Input | Required | Description |
|-------|----------|-------------|
| `env` | Yes | `test` or `prod` (lowercase) |
| `app_name` | Yes | Subdir under pool/compose (e.g. `htmt-api`, `gtmt-front`) |
| `artifact_name` | No | Artifact name; default `app-env-files` |

### Deploy Nginx Env Fragment

Uploads a single nginx env fragment to `pool/nginx/<app_name>.env`. Caller must upload an artifact (e.g. `nginx-env-fragment`) containing exactly one file.

**Workflow file:** `.github/workflows/deploy-nginx-env-fragment.yml`

| Input | Required | Description |
|-------|----------|-------------|
| `env` | Yes | `test` or `prod` (lowercase) |
| `app_name` | Yes | Fragment is uploaded as `pool/nginx/<app_name>.env` |
| `artifact_name` | No | Artifact name; default `nginx-env-fragment` |

### Deploy Partial Docker Compose

Uploads partial docker-compose files to the server compose dir. Before upload, adds suffix `-<env>` to every `container_name` in the compose files (e.g. `gtmt-front` → `gtmt-front-test`). Caller must upload an artifact (e.g. `compose-parts`) containing the partial YAML file(s).

**Workflow file:** `.github/workflows/deploy-docker-compose-part.yml`

| Input | Required | Description |
|-------|----------|-------------|
| `env` | Yes | `test` or `prod` (lowercase) |
| `app_version` | No | For logging only |
| `artifact_name` | No | Artifact name; default `compose-parts` |

## Usage

### Call Redeployment Webhook

```yaml
jobs:
  call-redeployment-webhook:
    name: Call Redeployment Webhook
    uses: BehindTheMusicTree/github-workflows/.github/workflows/call-redeployment-webhook.yml@main
    with:
      env: "test"   # or "prod"
      images: "{}" # optional: {"gateway_image": "user/repo:tag"}
    secrets: inherit
```

With dependencies (e.g. after build):

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
      env: "test"
    secrets: inherit
```

### Deploy workflows (caller examples)

Reference caller workflows that prepare artifacts and call the deploy reusables are in **`examples/`**:

- **`examples/deploy-htmt-api-env-and-compose.yml`** — API app: prepare nginx fragment, app env files (API/DB/AFP), and compose parts; call deploy-nginx-env-fragment, deploy-app-env-file, deploy-docker-compose-part. Copy to your htmt-api repo and adapt.
- **`examples/deploy-gtmt-front-env-and-compose.yml`** — Front app: prepare env file and compose parts; call deploy-app-env-file and deploy-docker-compose-part. Copy to your gtmt-front repo and adapt.

Caller pattern: one **prepare** job uploads artifacts (use non-dotfile names for app env files); separate jobs with `needs: [prepare]` call each reusable with `secrets: inherit`. Deploy workflows run in the **caller’s** context and need the vars/secrets listed below.

## Required Configuration

This repo only contains workflow definitions. Each repository that **calls** these workflows must configure the required secrets and variables in GitHub (repository or organization) under the environment used (e.g. `test`, `prod`).

### Webhook (call-redeployment-webhook)

| Type    | Name | Description |
|---------|------|-------------|
| Variable | `DOMAIN_NAME` | Server hostname or IP for webhook URL |
| Variable | `REDEPLOYMENT_HOOK_ID_BASE` | Base hook id; URL path is `/hooks/<REDEPLOYMENT_HOOK_ID_BASE>-<env>` (e.g. `myhook-test`) |
| Secret  | `REDEPLOYMENT_WEBHOOK_PORT` | Port the webhook service listens on |
| Secret  | `REDEPLOYMENT_WEBHOOK_SECRET_TEST` | Webhook secret for env `test` (X-Secret header) |
| Secret  | `REDEPLOYMENT_WEBHOOK_SECRET_PROD` | Webhook secret for env `prod` |

### Deploy workflows

Required by **deploy-app-env-file**, **deploy-nginx-env-fragment**, and **deploy-docker-compose-part** (caller’s environment must have these):

| Type    | Name | Description |
|---------|------|-------------|
| Variable | `WEBHOOK_DIR` | Base dir on server (e.g. `/home/deploy/`) |
| Variable | `WEBHOOK_REDEPLOYMENT_DIR_NAME_BASE` | Base name; pool/compose paths use `<base>-<env>` (e.g. `btmt-redeploy-test`) |
| Variable | `DOCKER_COMPOSE_DIR_NAME` | Compose dir name under redeploy dir |
| Variable | `DOMAIN_NAME` | Server hostname or IP for SSH |
| Secret  | `SERVER_DEPLOY_USERNAME` | SSH user for deploy |
| Secret  | `SERVER_DEPLOY_SSH_PRIVATE_KEY` | SSH private key for deploy |

## Setup Instructions

1. **Configure secrets and variables** in the repo (or org) that calls the workflows: **Settings** → **Environments** → create or select `test` / `prod` and add the required entries from [Required Configuration](#required-configuration).
2. **Add workflow calls** to your workflow file (see [Usage](#usage)). For deploy flows, copy and adapt a caller from `examples/`.
3. **Verify access**: Public repos can use these reusables as-is; private repos require the org to allow reusable workflows from private repos.

## Workflow Behavior

### Call Redeployment Webhook

1. **Validate env**: Ensures `env` is `test` or `prod`.
2. **Check required config**: Validates webhook-related secrets and variables for that env.
3. **Call webhook**: POSTs to the webhook URL (optional JSON body for image overrides).
4. **Validate response**: Fails if response does not start with `Redeploying BTMT ecosystem`.

### Expected Webhook Response

- **Status code**: `200 OK`
- **Response body**: Must start with `Redeploying BTMT ecosystem` (e.g. `Redeploying BTMT ecosystem (test)` is accepted).

### Error Handling

The webhook workflow fails with clear errors if:

- `env` is not `test` or `prod`
- Required secrets/variables are missing
- Webhook is unreachable (e.g. connection refused)
- Response does not match expected prefix or hook not found (404)

## Webhook Endpoint

The workflow builds the URL as:

```
http://<DOMAIN_NAME>:<REDEPLOYMENT_WEBHOOK_PORT>/hooks/<REDEPLOYMENT_HOOK_ID_BASE>-<env>
```

Example: `DOMAIN_NAME=example.com`, `REDEPLOYMENT_WEBHOOK_PORT=9000`, `REDEPLOYMENT_HOOK_ID_BASE=btmt-redeploy`, `env=test`  
→ `http://example.com:9000/hooks/btmt-redeploy-test`

Manual test (use the secret for the env you target):

```bash
curl -v -X POST -H "Content-Type: application/json" -H "X-Secret: YOUR_SECRET" -d '{}' --max-time 15 \
  http://example.com:9000/hooks/btmt-redeploy-test
```

## Troubleshooting

### "Workflow was not found" Error

- Ensure the repository is public (or your organization allows private repo access)
- Verify the workflow file exists on the `main` branch
- Check that the repository path is correct

### "Missing required config" / "env must be 'test' or 'prod'" Error

- Set all required secrets and variables for the environment you use (`test` or `prod`)
- Use `REDEPLOYMENT_WEBHOOK_SECRET_TEST` and `REDEPLOYMENT_WEBHOOK_SECRET_PROD` (not a single `REDEPLOYMENT_WEBHOOK_SECRET`)
- Ensure `REDEPLOYMENT_HOOK_ID_BASE` is set; the hook path is `<REDEPLOYMENT_HOOK_ID_BASE>-<env>`

### "Webhook call failed" / "Connection refused" Error

- Ensure the webhook service is running on the server: `systemctl status webhook`
- Check port and firewall; `REDEPLOYMENT_WEBHOOK_PORT` must match the server
- In `hooks.json`, the hook id must be `<REDEPLOYMENT_HOOK_ID_BASE>-<env>` (e.g. `btmt-redeploy-test`)
- Verify the X-Secret header matches the secret for that env (`REDEPLOYMENT_WEBHOOK_SECRET_TEST` or `_PROD`)

### "Artifact not found" when calling deploy workflows from another repo

- Artifacts are created in the caller’s run; reusables in another repo may not see them. Use a **single combined artifact** (e.g. one `app-env-files` with all env files) and consider inlining the deploy job in the caller if the reusable still can’t download it.
- Use **non-dotfile names** in app-env artifacts (e.g. `env_api` not `.env_api`) so `upload-artifact` includes the files; the deploy-app-env-file workflow renames them to dotfiles on the server.

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
