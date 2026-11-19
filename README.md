# GitHub Workflows

Reusable GitHub Actions workflows for the BehindTheMusicTree organization.

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Table of Contents

- [Available Workflows](#available-workflows)
  - [Agent drift](#agent-drift)
  - [Actionlint](#actionlint)
  - [Python publication](#python-publication)
  - [Call Redeployment Webhook](#call-redeployment-webhook)
  - [Set Image Tags On Server](#set-image-tags-on-server)
  - [Sync env to server](#sync-env-to-server)
  - [Trigger Coolify Deploy](#trigger-coolify-deploy)
  - [Run Coolify One-off Command](#run-coolify-one-off-command)
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

### Python publication

[`publish-python.yml`](.github/workflows/publish-python.yml) builds exactly one wheel and
one `.tar.gz` sdist from the caller's selected package directory (the repository root by
default), checks their metadata, and uploads
them with a SHA-256 manifest. It requires a tag push whose dereferenced commit is on
`origin/main`, a valid selected release policy (default `.github/release-policy.json`),
matching canonical version/mirrors,
and populated release notes. Put the exact `package-name` in the policy's
`outputs.packages` array. Only stable `X.Y.Z` versions are supported.

| Input | Required | Default | Purpose |
| --- | --- | --- | --- |
| `package-name` | Yes | — | Intended PyPI project name; must match distribution metadata and filenames |
| `package-directory` | No | `.` | Existing repository-relative build directory; symlinks and traversal are rejected |
| `release-policy-path` | No | `.github/release-policy.json` | Repository-relative policy file; paths inside the policy are also relative to the repository root |
| `python-version` | No | `3.12` | Build interpreter, Python 3.11+ required |
| `artifact-name` | No | `python-distributions` | Artifact name, unique per package in a run |

Outputs are `version`, `artifact-name`, and `foundation-sha` (the exact helper commit).
No API token or release App key is used. The build job has only `contents: read`.

PyPI Trusted Publishing must run in the caller's top-level workflow, outside the reusable
workflow ([PyPA limitation](https://github.com/pypa/gh-action-pypi-publish#trusted-publishing)).
Configure the caller repository, its existing workflow filename, and the `pypi` environment
as the [PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
Keep that workflow filename when adopting this helper so its OIDC identity is retained.
Grant `id-token: write` only to the publication job. Add this to that caller workflow,
replacing `REPLACE_WITH_MERGED_SHA` with the full merged foundation commit and
`example-pkg` with your project:

```yaml
name: Publish Python
on:
  push:
    tags: ['v*']
permissions:
  contents: read
concurrency:
  group: publish-python-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: false
jobs:
  build:
    uses: BehindTheMusicTree/github-workflows/.github/workflows/publish-python.yml@REPLACE_WITH_MERGED_SHA
    with:
      package-name: example-pkg
  publish:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/example-pkg
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v5
        with:
          repository: BehindTheMusicTree/github-workflows
          ref: ${{ needs.build.outputs.foundation-sha }}
          path: foundation
          persist-credentials: false
      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      - uses: actions/download-artifact@v4
        with:
          name: ${{ needs.build.outputs.artifact-name }}
          path: dist
      - name: Verify downloaded files and check PyPI retries
        id: retry
        env:
          VERSION: ${{ needs.build.outputs.version }}
        run: python3 foundation/release/python-artifact.py prepare example-pkg "$VERSION" dist pending
      - name: Publish missing distributions with Trusted Publishing
        if: steps.retry.outputs.upload-needed == 'true'
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: pending/
          skip-existing: false
      - name: Verify the complete published file set
        env:
          VERSION: ${{ needs.build.outputs.version }}
        run: python3 foundation/release/python-artifact.py verify example-pkg "$VERSION" dist
```

The retry helper queries the [PyPI version JSON API](https://docs.pypi.org/api/json/).
It compares every remote filename and SHA-256 digest against the intended wheel/sdist.
Identical complete releases skip uploading; partial releases stage only missing files.
Unexpected files, changed hashes, yanked files, malformed responses and network/API
errors fail; only HTTP 404 means absence. All existing files are checked before any
file is staged. `pending` must not already exist. The manifest check separately verifies
downloaded artifacts before querying PyPI. The final check requires the complete matching
release; registry visibility delays may fail it safely and require a rerun.

Rerun only the failed publication job to reuse the original build artifact. Rebuilding
must reproduce its bytes: timestamps or changed build dependencies may otherwise cause
a digest mismatch, which requires investigation. Do not enable blind `skip-existing` or
move the tag. Concurrent upload collisions fail safely; retry after checking the winning
upload. For multiple packages, use distinct artifact names and a separate caller job for
each upload. Keep a single GitHub Release owner that depends on all publication jobs;
this workflow never creates a tag or GitHub Release.

The helper is standard-library-only. Its tests also build fixture packages: install
`build twine setuptools wheel`, then run
`python3 -m unittest discover -s release -p 'test_python_artifact.py'`. The existing release
foundation CI job includes them automatically. Adoption still needs a live caller test
against its configured PyPI Trusted Publisher; local tests never perform uploads.

#### Two independently versioned packages

For `packages/alpha` at `2.3.4` and `packages/beta` at `7.0.1`, use separate policies
and tag prefixes. For example, `.github/alpha-release.json` contains:

```json
{
  "release_branch": "main",
  "version": {"path": "packages/alpha/pyproject.toml", "format": "toml", "key": "project.version"},
  "mirrors": [],
  "tag_prefix": "alpha-v",
  "changelog": "packages/alpha/CHANGELOG.md",
  "outputs": {"github_release": true, "packages": ["alpha-pkg"]}
}
```

Create `.github/beta-release.json` with `beta` paths, `beta-v`, and `beta-pkg`.
Each changelog must have nonempty notes for its own version. Keep all policy paths
relative to the repository root, including when the policy file lives inside a package.
The policies need not share a version source, mirrors, changelog or tag prefix.
Distribution filenames and embedded metadata must match the selected policy version
and `package-name`; building the wrong package fails before any upload.

In the **same caller workflow file** as the Trusted Publishing job above, replace
its tag filter and build job with the following selection and build jobs:

```yaml
on:
  push:
    tags: ['alpha-v*', 'beta-v*']
jobs:
  select:
    runs-on: ubuntu-latest
    outputs:
      package: ${{ steps.package.outputs.package }}
      directory: ${{ steps.package.outputs.directory }}
      policy: ${{ steps.package.outputs.policy }}
      artifact: ${{ steps.package.outputs.artifact }}
    steps:
      - id: package
        env:
          TAG: ${{ github.ref_name }}
        run: |
          case "$TAG" in
            alpha-v*) package=alpha ;;
            beta-v*) package=beta ;;
            *) echo 'Unexpected package tag' >&2; exit 1 ;;
          esac
          {
            echo "package=$package-pkg"
            echo "directory=packages/$package"
            echo "policy=.github/$package-release.json"
            echo "artifact=$package-distributions"
          } >> "$GITHUB_OUTPUT"
  build:
    needs: select
    uses: BehindTheMusicTree/github-workflows/.github/workflows/publish-python.yml@REPLACE_WITH_MERGED_SHA
    with:
      package-name: ${{ needs.select.outputs.package }}
      package-directory: ${{ needs.select.outputs.directory }}
      release-policy-path: ${{ needs.select.outputs.policy }}
      artifact-name: ${{ needs.select.outputs.artifact }}
```

Keep the caller's `publish` job, changing its `needs` to `[select, build]`. Use
`https://pypi.org/p/${{ needs.select.outputs.package }}` for its environment URL, set
`PACKAGE: ${{ needs.select.outputs.package }}` in the retry and final verification
steps' environments, and replace the literal `example-pkg` in those commands with
`"$PACKAGE"`. The artifact, version and foundation SHA still come from `needs.build.outputs`.
Register **both** PyPI projects with this caller workflow filename and environment.
An `alpha-v2.3.4` push validates/builds/publishes only alpha; `beta-v7.0.1` publishes
only beta, even when both tags point to the same commit. A failed beta publication
can be retried without changing alpha's version or tag.

GitHub Release creation stays in the caller and has one owner per tag. Add its job
**after** publication with `needs: [select, build, publish]`, using the default success
condition. It must validate the selected policy and use that policy's versioned
changelog section. If a tag requires additional publications (for example another
registry), include **every** publication job in `needs` and create the GitHub Release
only when all succeed, including final registry verification. Do not use `always()`
to publish a release after a failure, or race an independent tag-triggered GitHub Release
workflow against the upload jobs. The standalone `release-github.yml` is for GitHub-only
root policies and refuses package outputs; retain the caller's package release owner.

### Agent drift

Checks a caller project that has adopted the portable `AGENTS.md` / `CLAUDE.md` and skill-link conventions. It uses the public agent-config v1.1.0 engine pinned to commit `1e199e26e8c5d8778d94547b96d42d6c075bc7e7`, with read-only repository permissions and no private extension. It checks structure and configured scoped rules; it does not assess the accuracy of instructions or agent runtime loading.

Call from a workflow on pull requests and pin the reusable workflow to a released version of this repository:

```yaml
jobs:
  agent-drift:
    uses: BehindTheMusicTree/github-workflows/.github/workflows/agent-drift.yml@<release-tag-or-commit>
    permissions:
      contents: read
```

The caller checkout must contain `AGENTS.md` and a `CLAUDE.md` importing it. The check is read-only. See the [agent-config documentation](https://github.com/BehindTheMusicTree/agent-config) for the adapter contract.

### Actionlint

Runs [actionlint](https://github.com/rhysd/actionlint) on the caller repo. Uses `.github/actionlint.yaml` from the caller if present, so repo-specific ignore rules (e.g. for reusable workflow calls) apply.

**Workflow file:** `.github/workflows/actionlint.yml`

No inputs. Call from your repo on `push` or `pull_request`:

```yaml
jobs:
  actionlint:
    uses: BehindTheMusicTree/github-workflows/.github/workflows/actionlint.yml@main
```

### Call Redeployment Webhook

Triggers a server redeployment webhook. Validates configuration, ensures `env` is `prod` or `staging`, and POSTs to the webhook (optional JSON image overrides in body). The response body must start with **`Redeployment accepted`** (matches **`hooks.json`** from **BehindTheMusicTree/infrastructure** `generate-hooks-json.sh` for every stack).

**Workflow file:** `.github/workflows/call-redeployment-webhook.yml`

| Input          | Required | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| -------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `env`          | Yes      | `prod` or `staging` (lowercase)                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `images`       | No       | Optional JSON object of image overrides (e.g. `{"gateway_image": "user/repo:tag"}`). Default `{}`.                                                                                                                                                                                                                                                                                                                                                                                                        |
| `hook_id_base` | Yes      | Hook id for **`/hooks/<hook_id_base>-<env>`** (trimmed). **`X-Secret`** is chosen by exact match (trimmed): **`vars.BTMT_REDEPLOYMENT_HOOK_ID_BASE`** → **`BTMT_REDEPLOYMENT_WEBHOOK_SECRET_<env>`**; **`vars.TMD_ADMIN_API_REDEPLOYMENT_HOOK_ID_BASE`** → **`TMD_ADMIN_API_WEBHOOK_SECRET_<env>`**; **`vars.TMD_ADMIN_WEB_REDEPLOYMENT_HOOK_ID_BASE`** → **`TMD_ADMIN_WEB_WEBHOOK_SECRET_<env>`**; otherwise the workflow fails (no fallback). Use distinct hook id bases for each app on the same repo. |

### Set Image Tags On Server

Writes one pooled stack/env image-tags manifest on the server (atomic `*.new` then `mv -f`). Use this instead of per-service `set-image-tag-on-server` calls so API/DB/AFP tags are updated in one operation.

**Workflow file:** `.github/workflows/set-image-tags-on-server.yml`

| Input         | Required | Description                                               |
| ------------- | -------- | --------------------------------------------------------- |
| `env`         | Yes      | `prod` or `staging`                                       |
| `stack`       | Yes      | Stack key in filename (e.g. `btmt`, `tmd-admin`)          |
| `tags`        | Yes      | Multiline `KEY=VALUE` lines (e.g. `HTMT_API_TAG=staging`) |
| `release_id`  | No       | Optional release id metadata (`RELEASE_ID=`)              |
| `release_sha` | No       | Optional git SHA metadata (`RELEASE_SHA=`)                |

Required caller config: `vars.DEPLOY_SSH_HOST`, `vars.IMAGE_TAGS_POOL_DIR` (e.g. `/srv/btmt/image-tags`), `secrets.SERVER_DEPLOY_USERNAME`, `secrets.SERVER_DEPLOY_SSH_PRIVATE_KEY`.

### Trigger Coolify Deploy

App-agnostic composite action: trigger a Coolify application deploy via API, poll it to a terminal status (`finished`/`failed`/`cancelled-by-user`), and optionally HTTP health-check it before returning. Use this to enforce cross-application deploy ordering (e.g. deploy an API before its dependent web app) instead of relying on Coolify's native, unordered git-push auto-deploy — most useful on single-build-slot Coolify instances where two order-dependent builds triggered independently can otherwise deadlock or race.

**Action path:** `.github/actions/trigger-coolify-deploy`

| Input                             | Required | Description                                                                                                          |
| ---------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| `app_name`                         | Yes      | Coolify application name (e.g. `tmd-admin-api`)                                                                      |
| `coolify_environment`              | Yes      | Coolify environment name (`production` or `staging`)                                                                |
| `coolify_subdomain`                | Yes      | Coolify subdomain (e.g. `coolify`)                                                                                   |
| `domain`                           | Yes      | Base domain (e.g. `example.com`)                                                                                     |
| `coolify_api_token`                | Yes      | Coolify API token (composite actions have no `secrets:` block — pass via `with:`)                                     |
| `pr_number`                        | No       | PR number to target a PR-preview deployment instead of the regular one                                              |
| `force`                            | No       | Force a fresh deploy even if the commit is already deployed. Default `false`                                        |
| `poll_timeout_seconds`             | No       | Max seconds to wait for the deployment (and health check, if any) to finish. Default `1800` |
| `poll_interval_seconds`            | No       | Seconds between deployment/health-check polls. Default `15`                                                         |
| `preview_not_found_timeout_seconds`| No       | Max seconds to retry a PR-preview deploy trigger while Coolify hasn't created the preview yet. Default `180`         |
| `health_check_path`                | No       | Path (e.g. `/health`) to poll for HTTP 200 after the deployment finishes                                            |
| `health_check_base_url_override`   | No       | Base URL to health-check instead of the app's own fqdn. Required when both `pr_number` and `health_check_path` are set (Coolify's API doesn't expose a preview's fqdn) |
| `health_check_origin_ip`           | No       | Origin server IP to `curl --resolve` the health check directly to, bypassing any reverse proxy in front of the hostname. Needed for Cloudflare-proxied hostnames: Bot Fight Mode 403s GitHub Actions runner IPs on any proxied hostname and runs outside the Ruleset Engine, so no Custom Rule can exempt it |
| `stale_deployment_after_seconds`  | No       | Before triggering, cancel this app's (or PR preview's) deployments queued/in-progress longer than this, and force-stop the stale build over SSH when `server_host` is set. Must exceed every caller's `poll_timeout_seconds` for the app. Default `3600` |
| `discord_webhook_url`              | No       | Discord webhook to alert when the action fails or its job is cancelled (trigger error, deploy failure, poll timeout, job `timeout-minutes`) |

```yaml
- name: Trigger tmd-admin-api deploy
  uses: BehindTheMusicTree/github-workflows/.github/actions/trigger-coolify-deploy@v4.2.0
  with:
    app_name: tmd-admin-api
    coolify_environment: staging
    coolify_subdomain: ${{ vars.COOLIFY_API_SUBDOMAIN }}
    domain: ${{ vars.DOMAIN_NAME }}
    coolify_api_token: ${{ secrets.COOLIFY_API_TOKEN }}
    health_check_path: /health
    health_check_origin_ip: ${{ vars.APP_ORIGIN_IP }} # bypass Cloudflare proxy (Bot Fight Mode 403s CI runners)
```

### Run Coolify One-off Command

App-agnostic composite action: run a one-off command (typically database migrations) in a throwaway container on the Coolify host, from a given image, with the app's current Coolify runtime env (read from the Coolify API, so a release that adds an env var migrates with it) and the network of its running container. Use it as a release phase _before_ `trigger-coolify-deploy`, so a slow migration is not bound by Coolify's healthcheck window and can't roll the deploy back. The container's output streams into the job log and its exit code becomes the step's result.

**Action path:** `.github/actions/run-coolify-oneshot`

| Input                           | Required | Description                                                                                          |
| -------------------------------- | -------- | ------------------------------------------------------------------------------------------------------ |
| `app_name`                       | Yes      | Coolify application supplying the env (Coolify API) and network (its single running container) (e.g. `gtmt-api`) |
| `coolify_environment`            | Yes      | Coolify environment name (`production` or `staging`)                                                 |
| `coolify_subdomain`              | Yes      | Coolify API subdomain (e.g. `coolify`)                                                               |
| `domain`                         | Yes      | Base domain (e.g. `example.com`)                                                                     |
| `coolify_api_token`              | Yes      | Coolify API token allowed to read env values                                                         |
| `image`                          | Yes      | Image to run, ideally pinned by digest (`ghcr.io/org/app@sha256:...`)                                |
| `command`                        | Yes      | Command to run, split on whitespace (no quoting support)                                             |
| `server_host`                    | Yes      | VPS host to SSH into                                                                                 |
| `server_deploy_username`         | Yes      | SSH username (must be able to run `docker`)                                                          |
| `server_deploy_ssh_private_key`  | Yes      | SSH private key for `server_host`                                                                    |
| `timeout_minutes`                | No       | Max minutes before the command is stopped and the action fails. Default `60`                         |
| `discord_webhook_url`            | No       | Discord webhook to alert when the command fails, times out or the job is cancelled                   |

Fails fast if any runtime env var is multiline (not expressible in `--env-file`), or unless exactly one non-preview container matches `app_name`/`coolify_environment`. Any earlier one-off container for the same app/environment is removed first, so rely on the caller's concurrency group to serialize runs.

```yaml
- name: Run migrations
  uses: BehindTheMusicTree/github-workflows/.github/actions/run-coolify-oneshot@v4.6.0
  with:
    app_name: gtmt-api
    coolify_environment: production
    coolify_subdomain: ${{ vars.COOLIFY_API_SUBDOMAIN }}
    domain: ${{ vars.DOMAIN_NAME }}
    coolify_api_token: ${{ secrets.COOLIFY_API_TOKEN }}
    image: ghcr.io/behindthemusictree/gtmt-api@${{ needs.build.outputs.digest }}
    command: python3 manage.py migrate --no-input
    server_host: ${{ vars.DEPLOY_SSH_HOST }}
    server_deploy_username: ${{ secrets.SERVER_DEPLOY_USERNAME }}
    server_deploy_ssh_private_key: ${{ secrets.SERVER_DEPLOY_SSH_PRIVATE_KEY }}
```

### Check API Version

App-agnostic composite action: fail unless an API's health endpoint reports a version at or above a required minimum. Use it to stop a frontend release from shipping ahead of the API release it depends on. It fails on an unreachable endpoint, a missing or malformed `version`, or a version below the minimum.

**Action path:** `.github/actions/check-api-version`

| Input         | Required | Description                                                                 |
| ------------- | -------- | --------------------------------------------------------------------------- |
| `health_url`  | Yes      | Health endpoint returning JSON with a top-level semver `version`            |
| `min_version` | Yes      | Minimum acceptable API version, `X.Y.Z`                                     |
| `origin_ip`   | No       | Connect to this origin IP using the HTTPS URL's hostname and TLS verification |

When set, `origin_ip` selects the destination explicitly; the action never retries through another route after a failure.

```yaml
- uses: BehindTheMusicTree/github-workflows/.github/actions/check-api-version@v4.7.0
  with:
    health_url: https://grow-api.${{ vars.DOMAIN_NAME }}/health/
    min_version: 14.5.0
```

### Deploy App Env File

Uploads compose env files to `pool/compose/<app_name>/` on the server. Caller must upload an artifact (e.g. `app-env-files`) containing env files. Use **non-dotfile names** in the artifact (e.g. `env_api`, `env_gtmt_front`) so `upload-artifact` includes them; this workflow renames them to dotfiles (e.g. `.env_api`) before uploading.

**Workflow file:** `.github/workflows/deploy-app-env-file.yml`

| Input           | Required | Description                                               |
| --------------- | -------- | --------------------------------------------------------- |
| `env`           | Yes      | `prod` or `staging` (lowercase)                           |
| `app_name`      | Yes      | Subdir under pool/compose (e.g. `htmt-api`, `gtmt-front`) |
| `artifact_name` | No       | Artifact name; default `app-env-files`                    |

### Deploy Nginx Env Fragment

Uploads a single nginx env fragment to `pool/nginx/<app_name>.env`. Caller must upload an artifact (e.g. `nginx-env-fragment`) containing exactly one file.

**Workflow file:** `.github/workflows/deploy-nginx-env-fragment.yml`

| Input           | Required | Description                                         |
| --------------- | -------- | --------------------------------------------------- |
| `env`           | Yes      | `prod` or `staging` (lowercase)                     |
| `app_name`      | Yes      | Fragment is uploaded as `pool/nginx/<app_name>.env` |
| `artifact_name` | No       | Artifact name; default `nginx-env-fragment`         |

### Deploy Partial Docker Compose

Uploads partial docker-compose files to the server compose dir. Before upload, adds suffix `-<env>` to every `container_name` in the compose files (e.g. `gtmt-front` → `gtmt-front-staging`). Caller must upload an artifact (e.g. `compose-parts`) containing the partial YAML file(s).

**Workflow file:** `.github/workflows/deploy-docker-compose-part.yml`

| Input           | Required | Description                            |
| --------------- | -------- | -------------------------------------- |
| `env`           | Yes      | `prod` or `staging` (lowercase)        |
| `app_version`   | No       | For logging only                       |
| `artifact_name` | No       | Artifact name; default `compose-parts` |

## Usage

### Call Redeployment Webhook

```yaml
jobs:
  call-redeployment-webhook:
    name: Call Redeployment Webhook
    uses: BehindTheMusicTree/github-workflows/.github/workflows/call-redeployment-webhook.yml@main
    with:
      env: "staging" # or "prod"
      hook_id_base: ${{ vars.BTMT_REDEPLOYMENT_HOOK_ID_BASE }}
      images: "{}" # optional: {"gateway_image": "user/repo:tag"}
    secrets: inherit
```

**BTMT main stack** (e.g. hear-the-music-tree-api): pass **`hook_id_base: ${{ vars.BTMT_REDEPLOYMENT_HOOK_ID_BASE }}`** — same base string as in **`hooks.json`** on the server (from **BehindTheMusicTree/infrastructure** Server setup / Ansible).

**the-music-deck-admin**: pass **`hook_id_base: ${{ vars.TMD_ADMIN_API_REDEPLOYMENT_HOOK_ID_BASE }}`** for the admin **API** hook or **`hook_id_base: ${{ vars.TMD_ADMIN_WEB_REDEPLOYMENT_HOOK_ID_BASE }}`** for the admin **web** hook (must match infra); **`call-redeployment-webhook`** selects **`X-Secret`** by exact 3-way match (BTMT / TMD admin API / TMD admin web) and fails on unknown bases (no fallback).

**Infrastructure (two stacks):** **BehindTheMusicTree/infrastructure** `server-setup` runs two jobs with **`secrets: inherit`**: BTMT uses **`hook_id_base: ${{ vars.BTMT_REDEPLOYMENT_HOOK_ID_BASE }}`**; **The Music Deck admin** uses **`hook_id_base: ${{ vars.TMD_ADMIN_API_REDEPLOYMENT_HOOK_ID_BASE }}`** when that variable is set.

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
      env: "staging"
      hook_id_base: ${{ vars.BTMT_REDEPLOYMENT_HOOK_ID_BASE }}
    secrets: inherit
```

### Deploy workflows (caller examples)

Reference caller workflows that prepare artifacts and call the deploy reusables are in **`examples/`**:

- **`examples/deploy-htmt-api-env-and-compose.yml`** — API app: prepare nginx fragment, app env files (API/DB/AFP), and compose parts; call deploy-nginx-env-fragment, deploy-app-env-file, deploy-docker-compose-part. Copy to your htmt-api repo and adapt.
- **`examples/deploy-gtmt-front-env-and-compose.yml`** — Front app: prepare env file and compose parts; call deploy-app-env-file and deploy-docker-compose-part. Copy to your gtmt-front repo and adapt.

Caller pattern: one **prepare** job uploads artifacts (use non-dotfile names for app env files); separate jobs with `needs: [prepare]` call each reusable with `secrets: inherit`. Deploy workflows run in the **caller’s** context and need the vars/secrets listed below.

## Required Configuration

This repo only contains workflow definitions. Each repository that **calls** these workflows must configure the required secrets and variables in GitHub (repository or organization) under the environment used (`staging` or `prod`).

### Webhook (call-redeployment-webhook)

| Type     | Name                                       | Description                                                                                       |
| -------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Variable | `REDEPLOYMENT_WEBHOOK_HOST`                | VPS IP or hostname for webhook URL (use when main domain points elsewhere, e.g. Vercel)           |
| Variable | `BTMT_REDEPLOYMENT_HOOK_ID_BASE`           | Base hook id; URL path is `/hooks/<BTMT_REDEPLOYMENT_HOOK_ID_BASE>-<env>` (e.g. `myhook-staging`) |
| Secret   | `REDEPLOYMENT_WEBHOOK_PORT`                | Port the webhook service listens on                                                               |
| Secret   | `BTMT_REDEPLOYMENT_WEBHOOK_SECRET_STAGING` | Webhook secret for BTMT env `staging` (X-Secret header)                                           |
| Secret   | `BTMT_REDEPLOYMENT_WEBHOOK_SECRET_PROD`    | Webhook secret for BTMT env `prod`                                                                |

When **`hook_id_base`** equals **`TMD_ADMIN_API_REDEPLOYMENT_HOOK_ID_BASE`** (repository variable, trimmed), **`X-Secret`** uses **`TMD_ADMIN_API_WEBHOOK_SECRET_PROD`** / **`TMD_ADMIN_API_WEBHOOK_SECRET_STAGING`**. When **`hook_id_base`** equals **`TMD_ADMIN_WEB_REDEPLOYMENT_HOOK_ID_BASE`**, **`X-Secret`** uses **`TMD_ADMIN_WEB_WEBHOOK_SECRET_PROD`** / **`TMD_ADMIN_WEB_WEBHOOK_SECRET_STAGING`**. Any other `hook_id_base` fails fast (no fallback). **`REDEPLOYMENT_WEBHOOK_PORT`** is always required.

## Setup Instructions

1. **Configure secrets and variables** in the repo (or org) that calls the workflows: **Settings** → **Environments** → create or select `staging` / `prod` and add the required entries from [Required Configuration](#required-configuration).
2. **Add workflow calls** to your workflow file (see [Usage](#usage)). For deploy flows, copy and adapt a caller from `examples/`.
3. **Verify access**: Public repos can use these reusables as-is; private repos require the org to allow reusable workflows from private repos.

## Workflow Behavior

### Call Redeployment Webhook

1. **Validate env**: Ensures `env` is `prod` or `staging`.
2. **Check required config**: Validates webhook-related secrets and variables for that env.
3. **Call webhook**: POSTs to the webhook URL (optional JSON body for image overrides).
4. **Validate response**: Fails if the response body does not start with **`expected_response_prefix`** (default `Redeploying BTMT ecosystem`).

### Expected Webhook Response

- **Status code**: `200 OK`
- **Response body**: Must start with the configured prefix:
  - **BTMT** (default): `Redeploying BTMT ecosystem` (e.g. `Redeploying BTMT ecosystem (staging)`).
  - **The Music Deck admin**: pass `expected_response_prefix: "Redeploying The Music Deck admin"` (matches e.g. `Redeploying The Music Deck admin (prod)`).

### Error Handling

The webhook workflow fails with clear errors if:

- `env` is not `prod` or `staging`
- Required secrets/variables are missing
- Webhook is unreachable (e.g. connection refused)
- Response does not start with **`Redeployment accepted`** (regenerate **`hooks.json`** on the server after infra upgrades) or hook not found (404)

## Webhook Endpoint

The workflow builds the URL using **REDEPLOYMENT_WEBHOOK_HOST** (the webhook runs on the VPS; use VPS IP when the main domain points elsewhere, e.g. Vercel):

```
http://<REDEPLOYMENT_WEBHOOK_HOST>:<REDEPLOYMENT_WEBHOOK_PORT>/hooks/<BTMT_REDEPLOYMENT_HOOK_ID_BASE>-<env>
```

Example: `REDEPLOYMENT_WEBHOOK_HOST=203.0.113.10`, `REDEPLOYMENT_WEBHOOK_PORT=9000`, `BTMT_REDEPLOYMENT_HOOK_ID_BASE=btmt-redeploy`, `env=staging`

→ `http://203.0.113.10:9000/hooks/btmt-redeploy-staging`

Manual check (use the secret for the env you target):

```bash
curl -v -X POST -H "Content-Type: application/json" -H "X-Secret: YOUR_SECRET" -d '{}' --max-time 15 \
  http://<REDEPLOYMENT_WEBHOOK_HOST>:9000/hooks/btmt-redeploy-staging
```

## Troubleshooting

### "Workflow was not found" Error

- Ensure the repository is public (or your organization allows private repo access)
- Verify the workflow file exists on the `main` branch
- Check that the repository path is correct

### "Missing required config" / invalid `env` Error

- Set all required secrets and variables for the environment you use (`staging` or `prod`)
- Use `BTMT_REDEPLOYMENT_WEBHOOK_SECRET_STAGING` and `BTMT_REDEPLOYMENT_WEBHOOK_SECRET_PROD` (not a single combined secret name)
- Ensure `BTMT_REDEPLOYMENT_HOOK_ID_BASE` is set; the hook path is `<BTMT_REDEPLOYMENT_HOOK_ID_BASE>-<env>`

### "Webhook call failed" / "Connection refused" Error

- Ensure the webhook service is running on the server: `systemctl status webhook`
- Check port and firewall; `REDEPLOYMENT_WEBHOOK_PORT` must match the server
- In `hooks.json`, the hook id must be `<BTMT_REDEPLOYMENT_HOOK_ID_BASE>-<env>` (e.g. `btmt-redeploy-staging`)
- Verify the X-Secret header matches the secret for that env (`BTMT_REDEPLOYMENT_WEBHOOK_SECRET_STAGING` or `_PROD`)

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

## Release validation and tagging

The reusable [release-tag workflow](.github/workflows/release-tag.yml) validates a push to `main` and creates an annotated tag on that event's exact commit. It does not build packages, create GitHub Releases, or deploy. Existing tag-triggered publishers keep their permissions, OIDC identities and workflow filenames.

An adopter commits `.github/release-policy.json` using the [schema](release/release-policy.schema.json) and [example policy](examples/release-policy.json). The contract declares one canonical version, all mirrors, a tag prefix, a changelog and expected publication outputs. JSON and TOML sources use dot-separated keys; text files contain a version. Versions must be stable SemVer without leading zeroes. The validator enforces repository-relative paths and rejects duplicate sources. The changelog must contain exactly one `## [VERSION]` section with content beyond headings and HTML comments. The heading may carry a compare link directly after the bracket (`## [1.2.0](https://…) (2026-11-19)`, the release-please format) or a free-text suffix. For a first release without a previous tag, release-please writes the bare form `## 1.2.0 (2026-11-19)`, which is accepted too.

A repository releasing several independent components (for example `v*` and `graph-v*`) commits one policy file per component and passes `release-policy-path` to one `release-tag.yml` job per policy; GitHub-only publishers take the same input. The path defaults to `.github/release-policy.json`, and `release/github-release.py` reads it from `RELEASE_POLICY_PATH` with the same default.

Use the [caller example](examples/release-tag.yml), replacing its placeholder with a full **merged and reviewed commit SHA**. Configure `RELEASE_APP_ID` and the explicitly named `RELEASE_APP_PRIVATE_KEY` secret. Install the App on the adopting repository with Contents write permission; select only adopting repositories for organization secrets. Do not pass registry credentials or `secrets: inherit`.

Before enabling a caller, configure separate tag rulesets: creation permits the release App; update/deletion protection has no App bypass. The App must have no bypass of `main` protection. PR checks must cover the version and publisher changes before merge. If a repository also requires checks after merge, add those jobs in the caller's push workflow and make the reusable-workflow job depend on their successful completion with `needs`. Those checks must operate on `github.sha`, including reruns after a later push; a check of the latest branch tip is insufficient.

Activation and changes to the contract must land in a separate push from a version bump. Activation validates the current version, mirrors and changelog but never tags it, including an existing version with no tag. A subsequent push with no bump also produces no tag. For an established contract, a bump must increase the version and leave the policy unchanged; all mirrors and its changelog section must match. The version comparison uses the push's before/after commits, never the current branch tip. Force pushes and newly created branch events fail closed.

Prepare version and changelog in a PR using the project's own tools. In this repository, `.github/scripts/release.sh major|minor|patch` prepares a commit on a feature branch. Its legacy `publish` command remains available to repositories without the CI policy; once `.github/release-policy.json` exists, manual publication is refused. This repository declares its own `VERSION` policy and uses pinned callers for tagging and GitHub publication. Initial adoption keeps version 5.0.1 and produces no tag; App access and protections are activated separately in `github-config`.

Validation runs without App secrets and checks ancestry against fetched `origin/main`. A separate runner checks out only this repository's shared implementation at an immutable SHA, checks configuration, then requests an App token scoped to the caller repository and Contents write. The App-token action revokes it in its post step. No caller script or build runs in that job. The helper checkouts use `job.workflow_sha`, the commit of this reusable workflow that the caller pinned, after a guard step requires a 40-hex SHA and `job.workflow_repository` equal to `BehindTheMusicTree/github-workflows`. Scripts therefore always match the reviewed workflow and a Python change needs no second self-pin; each caller still pins the outer workflow independently.

Each run creates an annotated tag object, then atomically creates its ref, checking both write responses. Verification then re-reads the tag with backoff (about 23 seconds) because GitHub reads can briefly return 404 after a write; a mismatch fails immediately, and a tag still unreadable afterwards fails with a hint to rerun the job, which then reports an existing tag. An existing lightweight or annotated tag that dereferences to the same commit is a successful retry; a tag on another commit fails. Concurrent creation is accepted only after resolving the winner to the same SHA. API failures propagate. There is no global concurrency group that can discard a pending bump. A failed API response after ref creation can be retried with the same push event; never move a tag or bump again to recover.

`outputs` records the publisher contract; this tagger does not assert that those artifacts are published. For a partial publication, rerun the existing tag publisher after checking each required artifact. In a multi-package project the publisher must skip an already published identical version and distinguish registry errors from an absent package. GitHub Release creation must have one owner and wait for every required package. Do not replace a missing publisher run with an arbitrary workflow dispatch.

Run `python3 -m unittest discover -s release -p 'test_*.py'`, `bash .github/scripts/tests/release.sh`, `shellcheck .github/scripts/release.sh .github/scripts/tests/release.sh`, and `actionlint`. Tests simulate tagging and API errors without credentials or remote writes. Python 3.11+ is required. Repository-specific publisher recovery and a live App run are adoption checks, beyond the local foundation tests.

### GitHub-only publisher and package recovery

Repositories whose policy declares `github_release: true` and an empty `packages` list can
call `.github/workflows/release-github.yml` from their tag workflow. Pin the caller to a full
merged SHA, grant `contents: write`, and keep repository-specific validation jobs before it
with `needs`. The publisher checks the exact dereferenced tag, main ancestry, canonical
version, mirrors and populated changelog, then uses the ordinary workflow token to create
one stable GitHub Release. It never creates the release tag. API errors fail; only a 404
means absent. A concurrent 422 is accepted only after reading a published stable release.

A package publisher keeps its current workflow file and OIDC identity. After checking out
this foundation at an immutable SHA, it can run `release/github-release.py notes OUTPUT`
from its own checkout to validate provenance and extract notes before publishing packages.
A repository with a non-default policy must set `RELEASE_POLICY_PATH` for that command; otherwise it reads `.github/release-policy.json` and fails on the tag mismatch.
Its existing GitHub Release owner publishes those notes after every required artifact
succeeds. The standalone publisher refuses policies listing packages so it cannot bypass
that ordering. Neither entry point receives the release App key.

For npm recovery, invoke `node PATH/TO/foundation/release/npm-artifact.cjs PACKAGE VERSION
ARCHIVE` in a step with an `id`, then publish only when `steps.ID.outputs.exists != 'true'`.
The helper uses npmjs.org, requires stable SemVer, and accepts an existing artifact only
when its name, version and SHA-512 archive integrity match. Every HTTP error except 404,
invalid JSON and network failures stop the job. Run this separately for each package in
publication order, then create the GitHub Release only after all packages succeed. A
changed build environment or non-reproducible archive may require investigation; an
existing version alone is never treated as success. Keep this check in the existing
publisher job and retain its npm OIDC configuration and runtime.

## Release preparation with release-please

[`release-please.yml`](.github/workflows/release-please.yml) only *prepares* releases: it opens and updates a release PR (version, `CHANGELOG.md`, manifest) from the conventional commits merged to `main`. It never tags and never publishes. Merging the release PR is an ordinary release push, validated by the release policies and tagged by `release-tag.yml`; publication stays with the existing tag publishers.

Two Apps keep the duties apart: the tag App (`RELEASE_APP_ID`, Contents write, sole bypass of the tag-creation ruleset) and a preparation App (`RELEASE_PR_APP_ID` and the `RELEASE_PR_APP_PRIVATE_KEY` secret: Contents, Pull requests and Issues write, **no** ruleset bypass). Both are declared in `github-config`; an org admin creates and installs the preparation App. The tag rulesets must cover the prefix of every policy (for example `graph-v*`).

Each run first reconciles merged release PRs. `skip-github-release` leaves them labelled `autorelease: pending`, and release-please aborts every later run while one exists. [`release/reconcile-release-prs.py`](release/reconcile-release-prs.py) verifies, for each such merged PR, that it was squash merged into a single parent commit, that the release policies see a release on it, and that each expected tag exists on that exact commit. It then adds `autorelease: tagged` and removes `autorelease: pending`. Anything else fails the job: a missing tag means tagging failed, so rerun the tagging job and then the release-please job. Two pushes to `main` in quick succession can make the later run fail transiently while the earlier run is still tagging; rerun it. Before adopting, relabel any stale merged release PR still carrying `autorelease: pending` (for example one merged before adoption or without a squash): reconciliation fails closed on it until it is handled by hand.

Adopting:

1. Commit `release-please-config.json` and `.release-please-manifest.json` ([config](examples/release-please-config.json), [manifest](examples/.release-please-manifest.json)) with the manifest at the current versions, and one release policy per component ([root](examples/release-policy.json), [graph](examples/graph-release-policy.json)). The `.` package uses `simple` with `version-file`, `include-component-in-tag: false` and `exclude-paths` for the other components.
2. Remove the `## [Unreleased]` section from each changelog: release-please inserts its section above it, which would leave the entries stranded below.
3. Replace the `release-tag.yml` caller by the [combined caller](examples/release-please.yml): one tagging job per policy, then `release-please` with `needs` on all of them, so tags exist before reconciliation. Pin every `uses` to the same merged commit SHA.
4. Install the preparation App on the repository and set `RELEASE_PR_APP_ID` and `RELEASE_PR_APP_PRIVATE_KEY`.
5. Use squash merges with the PR title as the commit title, and conventional PR titles (`feat:`, `fix:`, `feat!:`): release-please ignores a non-conventional squash title. Merge the release PR with its title unchanged.

Release-please is the only way to prepare releases in an adopting repository: `.github/scripts/release.sh` refuses to run once `release-please-config.json` exists. The changelog is generated; edit the release PR's changelog when its wording needs a change, and do not edit `CHANGELOG.md` in feature PRs. A conventional-title check for PRs is not part of this workflow. Run `python3 -m unittest discover -s release -p 'test_*.py'` for the tests.
