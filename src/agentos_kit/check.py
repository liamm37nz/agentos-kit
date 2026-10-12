"""`agentos check`: verify an app repo (static) and a running app (live) against CONTRACT.md."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from . import manifest as mf

REQUIRED_FILES = ["agentos.yaml", "Dockerfile", "AGENTS.md", "CLAUDE.md", "README.md", ".github/workflows/agentos.yml"]
AGENTS_HEADINGS = ["Purpose", "Must never", "Commands", "Layout", "Data and secrets", "Notes"]
AGENTS_MAX_LINES = 150
HEALTH_STATES = {"ok", "degraded", "error"}
RUN_STATES = {"running", "succeeded", "failed"}


@dataclass
class Finding:
    level: str  # "error" | "warning"
    message: str


def check_repo(root: str | Path) -> list[Finding]:
    root = Path(root)
    findings: list[Finding] = []

    def err(msg: str) -> None:
        findings.append(Finding("error", msg))

    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            err(f"missing required file {name}")

    tests = root / "tests"
    if not tests.is_dir() or not any(p.is_file() for p in tests.rglob("*")):
        err("missing tests/ (CI must run tests)")

    if (root / "agentos.yaml").is_file():
        try:
            mf.load(root / "agentos.yaml")
        except mf.ManifestError as exc:
            for e in exc.errors:
                err(f"agentos.yaml: {e}")

    claude = root / "CLAUDE.md"
    if claude.is_file() and "@AGENTS.md" not in claude.read_text():
        err("CLAUDE.md must contain '@AGENTS.md'")

    agents = root / "AGENTS.md"
    if agents.is_file():
        text = agents.read_text()
        headings = {m.group(1).strip().lower() for m in re.finditer(r"^#\s+(.+)$", text, re.MULTILINE)}
        for h in AGENTS_HEADINGS:
            if h.lower() not in headings:
                err(f"AGENTS.md: missing heading '# {h}'")
        lines = len(text.splitlines())
        if lines > AGENTS_MAX_LINES:
            findings.append(Finding("warning", f"AGENTS.md is {lines} lines; keep it under ~100 and move detail to ARCHITECTURE.md"))

    for env in root.glob("*.env"):
        findings.append(Finding("warning", f"{env.name} is in the repo root — make sure it holds no secrets and is git-ignored"))
    if (root / ".env").is_file():
        findings.append(Finding("warning", ".env exists — make sure it is git-ignored"))

    return findings


def check_live(base_url: str, token: str, manifest: dict[str, Any], *, timeout: float = 5.0) -> list[Finding]:
    """Probe a running app. Never starts real jobs — only checks the API shape and auth."""
    findings: list[Finding] = []
    base_url = base_url.rstrip("/")
    auth = {"Authorization": f"Bearer {token}"}

    def err(msg: str) -> None:
        findings.append(Finding("error", msg))

    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        def get(path: str, **kw: Any) -> httpx.Response | None:
            try:
                return client.get(path, **kw)
            except httpx.HTTPError as exc:
                err(f"GET {path}: {exc.__class__.__name__}: {exc}")
                return None

        for path in ("/platform/health", "/platform/status"):
            for headers, label in (({}, "no token"), ({"Authorization": "Bearer wrong-" + secrets.token_hex(4)}, "wrong token")):
                r = get(path, headers=headers)
                if r is not None and r.status_code != 401:
                    err(f"GET {path} with {label}: expected 401, got {r.status_code}")

        r = get("/platform/health", headers=auth)
        body = _json(r, "/platform/health", err)
        if body is not None:
            if body.get("status") not in HEALTH_STATES:
                err(f"/platform/health: status must be one of {sorted(HEALTH_STATES)}, got {body.get('status')!r}")
            if "message" in body and not isinstance(body["message"], (str, type(None))):
                err("/platform/health: message must be a string")

        r = get("/platform/status", headers=auth)
        body = _json(r, "/platform/status", err)
        if body is not None:
            if not isinstance(body.get("summary"), str):
                err("/platform/status: summary must be a string")
            if not isinstance(body.get("attention"), bool):
                err("/platform/status: attention must be a boolean")
            facts = body.get("facts")
            if not isinstance(facts, list) or not all(
                isinstance(f, dict) and isinstance(f.get("label"), str) and isinstance(f.get("value"), str) for f in facts
            ):
                err("/platform/status: facts must be a list of {label: str, value: str}")

        unknown_job = "agentos-check-" + secrets.token_hex(4)
        try:
            r = client.post(f"/platform/jobs/{unknown_job}", headers=auth)
            if r.status_code != 404:
                err(f"POST /platform/jobs/<unknown>: expected 404, got {r.status_code}")
            r = client.post(f"/platform/jobs/{unknown_job}")
            if r.status_code != 401:
                err(f"POST /platform/jobs/<unknown> with no token: expected 401, got {r.status_code}")
        except httpx.HTTPError as exc:
            err(f"POST /platform/jobs: {exc}")

        r = get(f"/platform/runs/{unknown_job}", headers=auth)
        if r is not None and r.status_code != 404:
            err(f"GET /platform/runs/<unknown>: expected 404, got {r.status_code}")

        if manifest.get("ui", True):
            base_path = f"/apps/{manifest['id']}/"
            r = get(base_path, follow_redirects=True)
            if r is not None and r.status_code != 200:
                err(f"UI: GET {base_path} expected 200, got {r.status_code} (serve the UI under AGENTOS_BASE_PATH)")

    return findings


def _json(r: httpx.Response | None, path: str, err) -> dict | None:
    if r is None:
        return None
    if r.status_code != 200:
        err(f"GET {path}: expected 200, got {r.status_code}")
        return None
    try:
        body = r.json()
    except ValueError:
        err(f"GET {path}: response is not JSON")
        return None
    if not isinstance(body, dict):
        err(f"GET {path}: response must be a JSON object")
        return None
    return body
