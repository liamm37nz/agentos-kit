# AgentOS App Contract — v1

What an app must do to run on AgentOS. The platform talks to apps only through this contract; an app that follows it needs no platform changes to be deployed.

`agentos check` enforces everything here that can be checked automatically.

---

## 1. Rules for every app

1. **AI classifies and drafts; code acts.** Model output is structured data. It never chooses recipients, endpoints, or what gets written outside the app's own data.
2. **External data is untrusted.** Bank descriptions, emails, web pages and documents may contain instructions. Rule 1 means the worst outcome is a wrong classification, never an action.
3. **Irreversible external actions need a human step.** Submitting, publishing, paying, or sending to anyone but the owner: the app designs its own approval. The platform provides none.
4. **The repo is the memory.** Anything needed to understand, run or change the app is in the repo, not in a chat history.
5. **Secrets come from the environment.** Never in Git, images, the manifest or logs.

---

## 2. Repository

| File | Required | Notes |
|---|---|---|
| `agentos.yaml` | yes | Manifest (§3) |
| `Dockerfile` | yes | Serves on `$PORT`; works as uid 10001 |
| `AGENTS.md` | yes | §6 |
| `CLAUDE.md` | yes | Contains `@AGENTS.md` |
| `README.md` | yes | What it is, how to run it locally |
| `.github/workflows/agentos.yml` | yes | Calls the kit's reusable build workflow |
| `tests/` | yes | Run by CI |
| `ARCHITECTURE.md` | when non-trivial | The current implementation, not the original intent |
| `docs/decisions/NNNN-*.md` | optional | ADRs: Context, Decision, Consequences |

Start a new app with `agentos new <id>`.

---

## 3. Manifest — `agentos.yaml`

```yaml
spec: agentos/v1
id: gst                      # lowercase, digits, hyphens; stable forever
name: GST
description: Prepares two-monthly GST returns from bank transactions for import into Xero.

port: 8080                   # optional, default 8080
ui: true                     # optional, default true; UI served under AGENTOS_BASE_PATH
network: internet            # required: internet | none
memory: 512m                 # optional, default 512m

jobs:                        # optional
  - id: prepare-return
    name: Prepare GST return
    schedule: "0 6 1 2,4,6,8,10,12 *"   # optional 5-field cron; omit for manual-only
    catch_up: once           # once | skip (default) — run once after a missed schedule
    timeout: 30m             # optional, default 30m

secrets:                     # optional; names only
  - name: AKAHU_USER_TOKEN
    description: Akahu user token (read-only transactions)

shared:                      # optional; platform-managed host folders, read-only unless rw: true
  - path: obsidian
    mount: /vault

egress:                      # required when network is internet
  - host: api.anthropic.com
    purpose: Classify transactions
    data: merchant name, amount, date — no account numbers or names
```

- Schema: [`src/agentos_kit/schema/agentos-v1.json`](src/agentos_kit/schema/agentos-v1.json).
- Secret names must not start with `AGENTOS_`. Job ids are unique within the app.
- CI stores the manifest in the image as the label `agentos.manifest`. The platform reads it from the image.
- An unknown `spec` major version is rejected; the app is not deployed.

---

## 4. Runtime

The platform provides:

| Variable | Value |
|---|---|
| `AGENTOS_APP_ID` | the app id |
| `AGENTOS_TOKEN` | bearer token for `/platform/*` |
| `AGENTOS_BASE_PATH` | `/apps/<id>` |
| `PORT` | from the manifest |
| `TZ` | platform time zone |
| declared secrets | as environment variables |

Apps must:

- keep all persistent data in `/data` (SQLite in WAL mode is the default choice); everything else is disposable
- run as uid:gid `10001:10001` (the platform enforces it)
- log to stdout/stderr
- serve their UI under `AGENTOS_BASE_PATH` — the full path is forwarded, the prefix is not stripped
- serve `/platform/*` at the root path; it is reachable only from the platform
- become healthy within 60 seconds
- start even when secrets are missing, and report `degraded` (CI starts the app without secrets)
- trust the `X-AgentOS-User` header as the logged-in user; apps do no authentication of their own

The platform forbids privileged mode, host networking, added capabilities, and host mounts other than `/data` and declared `shared` paths.

---

## 5. Platform API

Every endpoint requires `Authorization: Bearer $AGENTOS_TOKEN` (otherwise `401`) and returns JSON.

**`GET /platform/health`** — fast; no external calls.
```json
{ "status": "ok", "message": "optional" }
```
`status`: `ok`, `degraded` or `error`.

**`GET /platform/status`** — the dashboard card.
```json
{
  "summary": "Draft return for Aug–Sep ready — emailed 1 Oct",
  "attention": false,
  "facts": [ { "label": "Transactions", "value": "214" } ]
}
```

**`POST /platform/jobs/{job_id}`** — start a job declared in the manifest. `202 {"run_id": "..."}`; `404` unknown job; `409` already running.

**`GET /platform/runs/{run_id}`**
```json
{ "state": "running", "message": "Classified 120 / 214", "started_at": "2026-10-01T06:00:00+13:00", "finished_at": null }
```
`state`: `running`, `succeeded` or `failed`. `404` for an unknown run — including runs lost when the app restarted, which the platform records as failed.

The template implements all of this in one vendored file, `app/agentos_platform.py`.

---

## 6. Documentation

`AGENTS.md` is read at the start of every coding-agent session. Keep it under about 100 lines. Required headings:

```markdown
# Purpose
# Must never
# Commands
# Layout
# Data and secrets
# Notes
```

Rules for coding agents:

1. Read `AGENTS.md`, `agentos.yaml`, and `ARCHITECTURE.md` if present, before changing code. Assume no earlier chat context.
2. Do not break this contract. If you must diverge, write an ADR.
3. Before finishing: update `AGENTS.md`, `agentos.yaml`, `README.md` and `ARCHITECTURE.md` where affected; run the tests; run `agentos check`.
4. Never commit secrets. A new secret is declared in `agentos.yaml`.

---

## 7. Build and deploy

The app's workflow calls `liamm37nz/agentos-kit/.github/workflows/build.yml`. On every push and pull request it runs `agentos check`, the tests, builds the image, starts it without secrets, and runs `agentos check --live` against it. On push to `main` it publishes `ghcr.io/<owner>/<repo>:main` and `:<git-sha>`.

The platform deploys new `:main` images automatically, health-gated with automatic rollback.
