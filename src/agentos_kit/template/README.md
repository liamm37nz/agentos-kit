# Template App

A minimal AgentOS app. Replace this with what the app does.

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
AGENTOS_TOKEN=dev DATA_DIR=./data uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080/apps/template-app/. Platform endpoints need `Authorization: Bearer dev`.

## Deploy

Push to `main`. CI checks, tests and publishes the image; AgentOS deploys it.
