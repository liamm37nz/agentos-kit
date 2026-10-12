# Migrate an existing project onto AgentOS

The goal: the project ends up as a normal AgentOS app (own private repo, `agentos.yaml`, deployed by pushing to `main`, data in `/data`), with **no data lost** and the old deployment still available until the user confirms the new one works.

Work in phases and stop for the user's approval at the marked points. Never stop, delete, or change the running original without explicit agreement to that specific step.

## Phase 1: Inventory (read-only)

Find out, from the code and, if it's running, the machine it runs on:

- **How it runs today**: command, process manager (systemd unit, nohup, cron, Docker, a laptop), port and bind address, Python/Node version, how it's started after a reboot.
- **State**: every file or database it writes (SQLite, JSON, vector stores, caches, uploads, logs). Note sizes. Separate *must keep* from *rebuildable*.
- **Secrets and config**: env files, config files, token caches (e.g. OAuth refresh tokens), keychain use. Record **names only**; do not open, print or copy values into the chat.
- **External services**: every host it calls and what data it sends (this becomes `egress`). Inbound webhooks? (AgentOS apps are not publicly reachable; flag this.)
- **Schedules**: in-process schedulers (APScheduler, node-cron, `setInterval` loops), system cron, timers. Each becomes a manifest job.
- **UI**: framework, how it builds, whether it assumes it's served at `/`, absolute links, websockets.
- **Files outside the project** it reads (e.g. a notes vault) → `shared` paths.
- **Git state**: uncommitted changes, unpushed branches, which branch is actually deployed.

## Phase 2: Plan — STOP for approval

Write a short plan for the user covering:

1. App id and name; repo (existing repo or new one; keep history when possible).
2. Manifest: `network`, `egress`, `jobs` (with schedules and `catch_up`), `secrets`, `shared`.
3. Code changes: platform endpoints, base path, schedulers moved to jobs, paths moved to `/data`.
4. Data: what moves to `/srv/agentos/data/<id>/`, how it's made consistent, how big.
5. Secrets the user will need to enter, and from where.
6. Cutover sequence, how long the app is unavailable, and how to roll back.
7. Anything that can't work on AgentOS as-is (inbound webhooks, GPUs, host devices) and the proposed alternative.

## Phase 3: Adapt the code (in a branch)

- **Add the contract files** from `agentos new <id> --dir /tmp/<id>-template`: copy `agentos.yaml`, `CLAUDE.md`, `.github/workflows/agentos.yml`, `.dockerignore`, and for Python apps `app/agentos_platform.py`. Write `AGENTS.md` fresh for this project.
- **Platform API and guard**: Python/FastAPI → `Platform(health=..., status=..., jobs=...)` and `platform.install(app)`. Flask/Django/other languages → implement the four endpoints and the request guard per the contract (bearer token on `/platform/*`, proxy token on everything else, 202/404/409, in-memory or SQLite run tracking). `agentos check --live` in CI verifies the guard.
- **Data other apps need, or data from other apps**: plan connections (`provides`/`uses`) rather than shared files or databases. If the project currently bundles several concerns with different trust needs (e.g. bank access + AI classification), consider splitting along that line during the migration and say so in the plan.
- **Base path**: serve the UI under `AGENTOS_BASE_PATH` (`/apps/<id>`), full path forwarded, not stripped. FastAPI: mount routes under a prefix (as the template does). Flask: register blueprints with `url_prefix`. Static sites/SPAs: build with the base path set (Vite `base`, Next.js `basePath`, CRA `homepage`) and make API calls relative. Keep `/platform/*` at the root.
- **Paths**: every persistent path comes from one setting defaulting to `/data` (keep the old default for local runs if useful). Remove writes elsewhere.
- **Schedulers → jobs**: delete the in-process scheduler; expose each task as a job function; declare `schedule` and `catch_up` in the manifest. Keep long tasks idempotent.
- **Config**: secrets from environment variables named in `agentos.yaml`. Non-secret settings: constants or environment defaults in the Dockerfile.
- **Container**: Dockerfile from the template (slim base, non-root uid 10001, `PORT`, `/data`). Large model downloads (e.g. sentence-transformers) go into the image at build time or into `/data` on first run — never into the container's home directory at runtime.
- **Health**: `ok` only when the app can do its job; `degraded` for missing secrets or a broken integration; fast, no external calls.
- **Tests** pass and `agentos check .` passes. Push the branch and get CI green before merging.

## Phase 4: Data and cutover — STOP for approval before each step that touches the original

1. **Snapshot** the original's state without stopping it if possible (SQLite: online backup API, not `cp` of a live file). Keep the snapshot until the user signs off.
2. **Stop the original** (with agreement) so state can't diverge. Take a final consistent copy.
3. **Place the data** in `/srv/agentos/data/<id>/`, owned by `10001:10001`, using the host procedure in the platform repo's `AGENTS.md` (the data directory is root-owned; don't loosen its permissions). Shared inputs go under `/srv/agentos/shared/<name>/`.
4. **Secrets**: ask the user to enter each value in **AgentOS → app → Secrets** (they can copy from the old env file themselves). Token caches that are really state (e.g. an OAuth refresh-token file) go into `/data`, not secrets.
5. **Merge to `main`** and add the app to `apps.yaml` in the platform repo. Watch it deploy (see [operate.md](operate.md)).
6. **Verify with the user**: UI loads inside AgentOS, data is all there (compare counts), a job runs via **Run now**, status card is sensible.
7. **Decommission** the original only after the user confirms: disable its service/cron/timer, but leave its files for a while. Note in the app's `AGENTS.md` where the old copy and snapshot are and when they can be deleted.

## Rollback

Until decommissioning, rollback is: remove the app from `apps.yaml` (the platform stops it, keeps its data), restart the original. Say this in the plan.
