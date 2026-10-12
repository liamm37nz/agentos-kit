# Purpose
Template App: a minimal AgentOS app. Replace this with one paragraph on what the app does and for whom.

This app runs on AgentOS and must follow the AgentOS App Contract:
https://github.com/liamm37nz/agentos-kit/blob/main/CONTRACT.md

# Must never
- Let model output choose recipients, endpoints or external writes (AI classifies and drafts; code acts).
- Take an irreversible external action (submit, publish, pay, send to anyone but the owner) without a human step.
- Commit secrets, or keep persistent data anywhere but `/data`.

# Commands
- Install: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt`
- Test: `pytest -q`
- Run locally: `AGENTOS_TOKEN=dev DATA_DIR=./data uvicorn app.main:app --reload --port 8080`, then open http://localhost:8080/apps/template-app/
- Check the contract: `pip install git+https://github.com/liamm37nz/agentos-kit && agentos check .`

# Layout
- `agentos.yaml` — manifest: jobs, secrets, network, egress
- `app/main.py` — app, UI, jobs, health and status
- `app/agentos_platform.py` — vendored platform API; do not edit, update from agentos-kit
- `tests/` — run in CI on every push

# Data and secrets
- Persistent data: `/data` (`DATA_DIR` locally). Currently `hello.log`.
- Secrets: none. Declare new ones in `agentos.yaml` and `REQUIRED_SECRETS` in `app/main.py`.

# Notes
- Push to `main` deploys automatically once the app is listed in AgentOS `apps.yaml`.
- Before finishing a change: update this file, `agentos.yaml` and README if affected; run tests and `agentos check`.
