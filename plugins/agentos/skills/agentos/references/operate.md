# Operate and debug AgentOS apps

Host access and exact commands are in the **platform repo's `AGENTS.md`** (`<owner>/agentos`). Read it first; this page explains what you're looking at.

## Where to look

| Question | Control plane (browser) | From a terminal |
|---|---|---|
| Is it deployed? Which version? | App → **Deploys** | deployer status for the app (platform `AGENTS.md`) |
| Is it healthy? | Dashboard card, sidebar dot, App → **Overview** | the app's `/platform/health` via the platform |
| Why did a deploy fail? | App → **Deploys** → Detail column | deployer app detail |
| Did a job run? | **Schedule** page, App → Overview → Recent runs | — |
| Logs | App logs (Dozzle, once available) | `docker logs agentos-<id>` on the host |
| Secrets set? | App → **Secrets** (names and set/missing only) | never read secret files |
| What happened when? | **Activity** | — |

## Deploy states

| State | Meaning | Usual fix |
|---|---|---|
| `pending` | Registered in `apps.yaml`, nothing deployed yet | Wait one cycle (~1 min); check the image exists on GHCR (CI green on `main`) |
| `deployed` | Running the latest healthy image | — |
| `missing-secrets` | Latest image declares secrets that aren't set. Any older version keeps running. | User enters them in **Secrets**; deploy proceeds automatically |
| `invalid` | Image has no/invalid `agentos.manifest` label, or its `id` doesn't match `apps.yaml` | Build with the kit workflow; fix `agentos.yaml`; push |
| `rolled-back` | New image failed its health check; the previous version is running again | Read the deploy detail and app logs, fix, push. The failed image is not retried automatically |
| `failed` | First deploy failed, or rollback also failed | As above; check health logic and startup errors |
| `removed` | Taken out of `apps.yaml`; container stopped, data and secrets kept | — |

**Health gate**: after starting a new image the deployer waits up to 120 s for `/platform/health` to return `status: ok`. `degraded` does **not** pass. Common causes: crash on startup (logs), slow startup (model loading — move to build time), a health check that calls an external service, a missing secret that the app treats as fatal.

## Health states (dashboard)

`healthy` / `degraded` / `unhealthy` (health returned `error`, timed out or bad JSON) / `starting` / `offline` (container not running) / `not deployed`. Unhealthy or offline for 5+ minutes raises a dashboard alert.

## Jobs

- Scheduled in the platform time zone from the manifest's cron. A job first seen starts counting from "now" (no backlog).
- Missed slots (host or control plane down): `catch_up: once` runs once on return; `skip` logs it.
- Run states: `running`, `succeeded`, `failed` (app reported failure, timed out, or the app restarted mid-run and lost it), `skipped` (already running).
- A job that times out may still be running inside the app; the platform can't cancel it. Make jobs check their own runtime if that matters.

## Manual controls (App → Deploys)

- **Redeploy latest**: pull `:main` again and deploy, even if it failed before.
- **Restart**: restart the container (same image, same secrets).
- **Roll back**: deploy an earlier successful image **and pause auto-deploy** so `main` doesn't immediately replace it. Resume when a fix is pushed.
- **Pause/Resume auto-deploy**.

Prefer fixing forward (push a fix to `main`) over manual controls; use rollback when the current version is causing harm.

## Things not to do

- Don't start, stop or edit app containers or generated compose files by hand; the deployer will fight you and the record will be wrong.
- Don't read or copy files in `/srv/agentos/secrets` or `/srv/agentos/state`.
- Don't change platform code from an app task. Platform changes go through the platform repo and its own tests.
