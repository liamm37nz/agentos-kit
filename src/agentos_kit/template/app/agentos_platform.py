"""AgentOS platform API and request guard for FastAPI apps (AgentOS App Contract v1, §4–§6).

Vendored from agentos-kit — copy updates from the kit rather than editing in place.

    platform = Platform(health=..., status=..., jobs={"job-id": fn})
    platform.install(app)          # adds /platform/* AND the guard below — required

The guard rejects every request that didn't come through the platform:
  /platform/*         needs `Authorization: Bearer $AGENTOS_TOKEN` (the platform itself)
  /connect/<scope>/*  needs a connection token granted to the calling app for <scope>
  everything else     needs the `X-AgentOS-Proxy-Token` header the platform's proxy adds
Only then is `X-AgentOS-User` trustworthy.

Job functions receive a JobContext and run in a background thread. Return a final
message (or None) to succeed; raise to fail. Runs are kept in memory, so a restart
forgets them and the platform records any in-flight run as failed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("agentos.platform")

MAX_RUNS = 100
PROXY_HEADER = b"x-agentos-proxy-token"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Run:
    id: str
    job_id: str
    state: str = "running"
    message: str = ""
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None

    def as_dict(self) -> dict:
        return {"state": self.state, "message": self.message, "started_at": self.started_at, "finished_at": self.finished_at}


class JobContext:
    def __init__(self, run: Run):
        self._run = run

    @property
    def run_id(self) -> str:
        return self._run.id

    def progress(self, message: str) -> None:
        """Update the message the platform shows while the job runs."""
        self._run.message = message


class Platform:
    def __init__(
        self,
        *,
        health: Callable[[], dict],
        status: Callable[[], dict],
        jobs: dict[str, Callable[[JobContext], str | None]] | None = None,
        token: str | None = None,
        clients: str | None = None,
    ):
        self._health = health
        self._status = status
        self.jobs = dict(jobs or {})
        self._token = token if token is not None else os.environ.get("AGENTOS_TOKEN", "")
        if not self._token:
            log.warning("AGENTOS_TOKEN is not set; every request will be rejected")
        # Connection grants for apps calling this one: {sha256(token): {"app": id, "scopes": [...]}}
        raw = clients if clients is not None else os.environ.get("AGENTOS_CONNECT_CLIENTS", "")
        try:
            self._clients: dict = json.loads(raw) if raw else {}
        except ValueError:
            log.error("AGENTOS_CONNECT_CLIENTS is not valid JSON; no connections accepted")
            self._clients = {}
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._lock = threading.Lock()
        self.router = APIRouter(prefix="/platform", dependencies=[Depends(self._auth)], include_in_schema=False)
        self.router.add_api_route("/health", self._get_health, methods=["GET"])
        self.router.add_api_route("/status", self._get_status, methods=["GET"])
        self.router.add_api_route("/jobs/{job_id}", self._start_job, methods=["POST"])
        self.router.add_api_route("/runs/{run_id}", self._get_run, methods=["GET"])

    def install(self, app: FastAPI) -> None:
        """Add the /platform API and the request guard to the app."""
        app.include_router(self.router)
        app.add_middleware(_Guard, platform=self)

    # ---- authentication --------------------------------------------------------------

    def _auth(self, request: Request) -> None:
        if not self.platform_token_ok(request.headers.get("authorization", "")):
            raise HTTPException(status_code=401, detail="invalid or missing platform token")

    def platform_token_ok(self, header: str) -> bool:
        scheme, _, supplied = header.partition(" ")
        return bool(self._token and scheme.lower() == "bearer" and hmac.compare_digest(supplied.encode(), self._token.encode()))

    def proxy_token_ok(self, supplied: str) -> bool:
        return bool(self._token and supplied and hmac.compare_digest(supplied.encode(), self._token.encode()))

    def connection_caller(self, header: str, scope: str) -> str | None:
        """The app id behind a connection token, if it was granted `scope`."""
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not supplied:
            return None
        grant = self._clients.get(hashlib.sha256(supplied.encode()).hexdigest())
        if not grant or scope not in grant.get("scopes", []):
            return None
        return grant.get("app")

    # ---- platform API ------------------------------------------------------------------

    def _get_health(self) -> dict:
        try:
            return self._health()
        except Exception as exc:  # health must always answer
            log.exception("health check failed")
            return {"status": "error", "message": f"health check raised {exc.__class__.__name__}"}

    def _get_status(self) -> dict:
        return self._status()

    def _start_job(self, job_id: str):
        fn = self.jobs.get(job_id)
        if fn is None:
            raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
        with self._lock:
            if any(r.job_id == job_id and r.state == "running" for r in self._runs.values()):
                raise HTTPException(status_code=409, detail=f"job {job_id!r} is already running")
            run = Run(id=uuid.uuid4().hex, job_id=job_id)
            self._runs[run.id] = run
            while len(self._runs) > MAX_RUNS:
                self._runs.popitem(last=False)
        threading.Thread(target=self._execute, args=(fn, run), name=f"job-{job_id}", daemon=True).start()
        return JSONResponse({"run_id": run.id}, status_code=202)

    def _execute(self, fn: Callable[[JobContext], str | None], run: Run) -> None:
        log.info("job %s started (run %s)", run.job_id, run.id)
        try:
            result = fn(JobContext(run))
            run.message = result if result is not None else run.message
            run.state = "succeeded"
        except Exception as exc:
            log.exception("job %s failed (run %s)", run.job_id, run.id)
            run.message = f"{exc.__class__.__name__}: {exc}"
            run.state = "failed"
        run.finished_at = _now()
        log.info("job %s %s (run %s)", run.job_id, run.state, run.id)

    def _get_run(self, run_id: str) -> dict:
        run = self._runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run")
        return run.as_dict()


def caller(request: Request) -> str:
    """In a /connect/<scope>/ route: the id of the app making the call (checked by the guard)."""
    return request.state.agentos_caller


def connection(app_id: str) -> tuple[str, str] | None:
    """For calling another app: (base URL of its /connect API, token), or None if not granted."""
    key = app_id.upper().replace("-", "_")
    url, token = os.environ.get(f"AGENTOS_CONNECT_{key}_URL"), os.environ.get(f"AGENTOS_CONNECT_{key}_TOKEN")
    return (url, token) if url and token else None


class _Guard:
    """ASGI middleware: reject anything that didn't come from the platform (see module docstring)."""

    def __init__(self, app, platform: Platform):
        self.app, self.platform = app, platform

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        headers = {k.lower(): v for k, v in scope.get("headers", [])}

        if path == "/platform" or path.startswith("/platform/"):
            return await self.app(scope, receive, send)  # the router checks the platform token

        if path.startswith("/connect/"):
            grant_scope = path.split("/")[2]
            who = self.platform.connection_caller(headers.get(b"authorization", b"").decode("latin-1"), grant_scope)
            if who is None:
                return await _deny(scope, send, 401, "connection not granted")
            scope.setdefault("state", {})["agentos_caller"] = who
            return await self.app(scope, receive, send)

        if not self.platform.proxy_token_ok(headers.get(PROXY_HEADER, b"").decode("latin-1")):
            return await _deny(scope, send, 401, "requests must come through AgentOS")
        return await self.app(scope, receive, send)


async def _deny(scope, send, status: int, message: str) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    body = json.dumps({"detail": message}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
