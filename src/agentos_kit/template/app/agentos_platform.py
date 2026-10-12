"""AgentOS platform API for FastAPI apps (AgentOS App Contract v1, §5).

Vendored from agentos-kit — copy updates from the kit rather than editing in place.

    platform = Platform(health=..., status=..., jobs={"job-id": fn})
    app.include_router(platform.router)

Job functions receive a JobContext and run in a background thread. Return a final
message (or None) to succeed; raise to fail. Runs are kept in memory, so a restart
forgets them and the platform records any in-flight run as failed.
"""

from __future__ import annotations

import hmac
import logging
import os
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("agentos.platform")

MAX_RUNS = 100


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
    ):
        self._health = health
        self._status = status
        self.jobs = dict(jobs or {})
        self._token = token if token is not None else os.environ.get("AGENTOS_TOKEN", "")
        if not self._token:
            log.warning("AGENTOS_TOKEN is not set; every /platform request will be rejected")
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._lock = threading.Lock()
        self.router = APIRouter(prefix="/platform", dependencies=[Depends(self._auth)], include_in_schema=False)
        self.router.add_api_route("/health", self._get_health, methods=["GET"])
        self.router.add_api_route("/status", self._get_status, methods=["GET"])
        self.router.add_api_route("/jobs/{job_id}", self._start_job, methods=["POST"])
        self.router.add_api_route("/runs/{run_id}", self._get_run, methods=["GET"])

    def _auth(self, request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, _, supplied = header.partition(" ")
        if not (self._token and scheme.lower() == "bearer" and hmac.compare_digest(supplied.encode(), self._token.encode())):
            raise HTTPException(status_code=401, detail="invalid or missing platform token")

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
