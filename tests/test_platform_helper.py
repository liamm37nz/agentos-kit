"""The vendored helper's guard and connections, exercised the way apps use them."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

TEMPLATE = Path(str(resources.files("agentos_kit").joinpath("template")))
spec = importlib.util.spec_from_file_location("agentos_platform", TEMPLATE / "app" / "agentos_platform.py")
ap = importlib.util.module_from_spec(spec)
sys.modules["agentos_platform"] = ap  # dataclasses need the module registered
spec.loader.exec_module(ap)


def provider(grants: dict) -> TestClient:
    clients = {hashlib.sha256(tok.encode()).hexdigest(): g for tok, g in grants.items()}
    platform = ap.Platform(health=lambda: {"status": "ok"}, status=lambda: {"summary": "", "attention": False, "facts": []},
                           token="app-token", clients=json.dumps(clients))
    app = FastAPI()
    platform.install(app)

    @app.get("/connect/transactions/list")
    def listing(request: Request):
        return {"caller": ap.caller(request)}

    @app.get("/connect/payments/list")
    def payments(request: Request):
        return {"caller": ap.caller(request)}

    @app.get("/apps/finance/")
    def ui(request: Request):
        return {"user": request.headers.get("x-agentos-user")}

    return TestClient(app)


def test_connection_tokens_are_scoped():
    c = provider({"budget-token": {"app": "budget", "scopes": ["transactions"]}})
    ok = c.get("/connect/transactions/list", headers={"Authorization": "Bearer budget-token"})
    assert ok.status_code == 200 and ok.json() == {"caller": "budget"}
    assert c.get("/connect/payments/list", headers={"Authorization": "Bearer budget-token"}).status_code == 401  # other scope
    assert c.get("/connect/transactions/list", headers={"Authorization": "Bearer guess"}).status_code == 401
    assert c.get("/connect/transactions/list").status_code == 401
    # a connection token is not a proxy token or a platform token
    assert c.get("/apps/finance/", headers={"X-AgentOS-Proxy-Token": "budget-token"}).status_code == 401
    assert c.get("/platform/health", headers={"Authorization": "Bearer budget-token"}).status_code == 401


def test_proxy_token_required_for_everything_else():
    c = provider({})
    assert c.get("/apps/finance/", headers={"X-AgentOS-User": "liam"}).status_code == 401
    r = c.get("/apps/finance/", headers={"X-AgentOS-Proxy-Token": "app-token", "X-AgentOS-User": "liam"})
    assert r.status_code == 200 and r.json() == {"user": "liam"}
    assert c.get("/platform/health", headers={"Authorization": "Bearer app-token"}).json() == {"status": "ok"}


def test_bad_clients_json_accepts_nothing():
    platform = ap.Platform(health=dict, status=dict, token="t", clients="{not json")
    assert platform.connection_caller("Bearer x", "s") is None


def test_connection_helper_reads_env(monkeypatch):
    assert ap.connection("bank-sync") is None
    monkeypatch.setenv("AGENTOS_CONNECT_BANK_SYNC_URL", "http://agentos-bank-sync:8080/connect")
    monkeypatch.setenv("AGENTOS_CONNECT_BANK_SYNC_TOKEN", "tok")
    assert ap.connection("bank-sync") == ("http://agentos-bank-sync:8080/connect", "tok")


def test_template_own_tests_pass():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=TEMPLATE, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
