<div align="center">
  <a target="_blank" href="https://skilldock.io/?utm_source=github&utm_medium=readme">
   <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=200&section=header&text=SkillDock.io&fontSize=50&fontAlignY=35&animation=fadeIn&fontColor=FFFFFF&descAlignY=55&descAlign=62" alt="SkillDock" width="100%" />
  </a>
</div>

[![PyPI version](https://badge.fury.io/py/skilldock.svg)](https://badge.fury.io/py/skilldock)
[![License: MIT](https://img.shields.io/badge/License-Apache2.0-green.svg)](https://opensource.org/license/apache-2-0)
[![Downloads](https://static.pepy.tech/badge/skilldock)](https://pepy.tech/project/skilldock)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-blue)](https://www.linkedin.com/in/eugene-evstafev-716669181/)

# SkillDock Python SDK and CLI

`skilldock` is an OpenAPI-driven Python client (and a simple CLI) for the SkillDock API.

It loads the OpenAPI spec at runtime and exposes:
- A Python `SkilldockClient` that can call any `operationId`
- A CLI that can list available operations and call them from your terminal

## Install

```bash
pip install skilldock
```

## Quickstart (CLI)

List operations from the OpenAPI spec:

```bash
skilldock ops
```

The first column is a python-friendly `python_name` you can use as `client.ops.<python_name>(...)`.

Authenticate (browser login + polling):

```bash
skilldock auth login
```

This starts a CLI auth session on the API, prints an `auth_url`, opens it in your browser, then polls until it receives an app-issued `access_token` and saves it as the CLI token.
Access tokens are short-lived; if you see auth errors later, run `skilldock auth login` again.

Create a long-lived personal API token (recommended for CI and to avoid short-lived JWT expiry):

```bash
# Prints the token (shown only once by the API) and saves it into the CLI config.
skilldock tokens create --save

# List your tokens
skilldock tokens list
```

Call an endpoint by `operationId`:

```bash
skilldock call SomeOperationId --param foo=bar --json '{"hello":"world"}'
```

Search skills:

```bash
skilldock skills search "docker"
```

`skills search` uses `POST /v2/search` and returns the same listing contract shape (`page`, `per_page`, `items`, `has_more`).

Search output includes `LATEST_VERSIONS` from each skill's embedded `latest_releases` (up to 5 items).

Get a single skill (latest metadata + latest description source):

```bash
skilldock skills get acme/my-skill
```

Get one exact release by version (source of truth for versioned descriptions):

```bash
skilldock skills release acme/my-skill 0.1.0
```

Browse release history page-by-page:

```bash
skilldock skills releases acme/my-skill --page 1 --per-page 10
```

Commerce sell/buy flow (TON):

```bash
# 1) Seller setup
skilldock skills set-ton-wallet --ton-wallet-address UQ...
skilldock skills set-commerce acme/my-skill --is-for-sale true --visibility private --selling-description-md "What buyer sees"
skilldock skills set-price acme/my-skill --pricing-mode fixed_ton --price-ton 2.750000000

# 2) Buyer invoice create/reuse (TON provider required by current backend)
skilldock skills buy acme/my-skill --payment-provider ton --referral-code a

# 3) Poll invoice until paid/expired/cancelled
skilldock skills buy acme/my-skill --payment-provider ton --poll
# or check a known invoice id
skilldock skills invoice <invoice_id>

# 4) Confirm inventory
skilldock skills bought --page 1 --per-page 20
```

Get author profile details and authored skills (paginated):

```bash
skilldock users get 123 --page 1 --per-page 20
```

Install a skill locally (default destination is `./skills`, with recursive dependency resolution):

Public skills can be installed without auth. If a token is configured, the CLI sends it for skill discovery/install flows so private skills can be resolved when authorized.

```bash
# latest
skilldock install acme/my-skill

# exact version
skilldock i acme/my-skill --version 1.2.3

# custom local destination
skilldock install acme/my-skill --skills-dir /path/to/project/skills
```

Uninstall a direct skill and reconcile/remove no-longer-needed dependencies:

```bash
skilldock uninstall acme/my-skill
```

Verify a local skill folder (packages a zip and prints sha256/size):

```bash
skilldock skill verify .
```

Upload a new skill release:

```bash
skilldock skill upload --namespace myorg --slug my-skill --version 1.2.3 --path .

# Explicit private publish
skilldock skill upload --namespace myorg --slug my-skill --version 1.2.3 --path . --visibility private
```

This packages the folder into a zip and uploads it as multipart form field `file`.
For this registry, tags are read by the backend from `SKILL.md` frontmatter inside the uploaded zip.
There is no separate upload `tags` field (or CLI `--tag` flag) for publish.
Release versions are immutable: if you change `SKILL.md` (including description), publish a new version.
Re-publishing the same version for the same skill returns a conflict.

```md
---
name: my-skill
description: Does X
version: 1.2.0
tags:
  - productivity
  - automation
  - cli
---
```

Tag values should be strings; non-string values are ignored by the backend.
The CLI packages upload archives with top-level folder name equal to `--slug`, so keep frontmatter `name` aligned with your slug.

If your API supports release dependencies, you can pass them from CLI too:

```bash
# Repeatable string form:
skilldock skill upload --namespace myorg --slug my-skill --path . \
  --dependency "core/base-utils@^1.2.0" \
  --dependency "tools/lint@>=2.0.0 <3.0.0"

# JSON form (array or map), inline or from file:
skilldock skill upload --namespace myorg --slug my-skill --path . \
  --dependencies-json @dependencies.json
```

If you haven't created the namespace yet:

```bash
skilldock namespaces create myorg
skilldock namespaces list
```

Low-level request (method + path, bypassing `operationId`):

```bash
skilldock request GET /health
```

## Quickstart (Python)

```python
from skilldock import SkilldockClient

client = SkilldockClient(
    # Optional: override if needed
    openapi_url="https://api.skilldock.io/openapi.json",
    # base_url="https://api.skilldock.io",
    token=None,  # set after `skilldock auth login`
)

ops = client.operation_ids()
print("operations:", len(ops))

# Call by operationId (params are split into path/query/header based on OpenAPI metadata)
result = client.call_operation("SomeOperationId", params={"id": "123"})
print(result)

# Or call by a generated python-friendly name:
# (see `skilldock ops` output and use the `python_name`-like identifier)
# result = client.ops.someoperationid(id="123")

client.close()
```

## Description Versioning

The registry now stores `description_md` per release version.

- Publish flow:
  - Build/upload the zip with the intended `SKILL.md` content for that version.
  - Publish a new version each time description changes (for example, `0.1.0` -> `0.1.1`).
- Read flow:
  - Exact version description: `GET /v1/skills/{namespace}/{slug}/releases/{version}` and use `release.description_md`.
  - Latest overview: `GET /v1/skills/{namespace}/{slug}` and prefer `latest_release.description_md`.
- Backward compatibility:
  - `skill.description_md` still reflects current/latest description.
  - Fallback order when release description is empty:
    1. `release.description_md`
    2. `skill.description_md`
    3. empty state

## Configuration

The CLI stores config (including token) in a local JSON file:

```bash
skilldock config path
skilldock config show
```

You can set config values:

```bash
skilldock config set --base-url https://api.skilldock.io --openapi-url https://api.skilldock.io/openapi.json
skilldock config set --token "YOUR_TOKEN"
```

Environment variables (override config):
- `SKILLDOCK_OPENAPI_URL`
- `SKILLDOCK_BASE_URL`
- `SKILLDOCK_TOKEN`
- `SKILLDOCK_TIMEOUT_S`

## Authentication Notes (Google)

This SDK assumes the API accepts a token in an HTTP header (usually `Authorization: Bearer <token>`).
The exact details are derived from the OpenAPI `securitySchemes` when present.

The SkillDock API can accept (depending on server configuration):
- Google ID token (JWT)
- App-issued access token (JWT, returned by the CLI OAuth flow)
- Personal API token (opaque string, created via `skilldock tokens create`)

`skilldock auth login` works like this:
1. Creates a CLI auth session via `POST /auth/cli/sessions`
2. Prints the returned `auth_url` and opens it in your browser
3. After you complete Google login, the backend approves the session
4. The CLI polls `GET /auth/cli/sessions/{session_id}` until it receives an app-issued `access_token`, then saves it as the configured API token

If you want to set a token manually:

```bash
skilldock auth set-token "PASTE_TOKEN_HERE"
```

To create a personal API token (recommended for longer-lived auth):

```bash
skilldock tokens create --save
```

## Development

Run the small unit test suite:

```bash
python -m unittest discover -s tests
```
