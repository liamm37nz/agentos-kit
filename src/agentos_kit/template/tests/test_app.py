import importlib
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PROXY = {"X-AgentOS-Proxy-Token": TOKEN}  # what AgentOS's proxy adds to UI requests
MANIFEST = yaml.safe_load((Path(__file__).parent.parent / "agentos.yaml").read_text())
BASE = f"/apps/{MANIFEST['id']}"


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTOS_TOKEN", TOKEN)
    monkeypatch.setenv("AGENTOS_BASE_PATH", BASE)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app.main

    return importlib.reload(app.main)


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def wait_for_run(client, run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/platform/runs/{run_id}", headers=AUTH).json()
        if run["state"] != "running":
            return run
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_platform_requires_token(client):
    assert client.get("/platform/health").status_code == 401
    assert client.get("/platform/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_health_and_status(client):
    assert client.get("/platform/health", headers=AUTH).json()["status"] == "ok"
    status = client.get("/platform/status", headers=AUTH).json()
    assert status["summary"] == "No hellos yet"
    assert status["attention"] is False


def test_job_runs_and_updates_status(client):
    r = client.post("/platform/jobs/say-hello", headers=AUTH)
    assert r.status_code == 202
    run = wait_for_run(client, r.json()["run_id"])
    assert run["state"] == "succeeded"
    facts = client.get("/platform/status", headers=AUTH).json()["facts"]
    assert facts == [{"label": "Hellos", "value": "1"}]


def test_unknown_job_and_run(client):
    assert client.post("/platform/jobs/nope", headers=AUTH).status_code == 404
    assert client.get("/platform/runs/nope", headers=AUTH).status_code == 404


def test_ui_served_under_base_path(client):
    r = client.get(BASE + "/", headers={**PROXY, "X-AgentOS-User": "liam"})
    assert r.status_code == 200
    assert "Hello, liam" in r.text


def test_requests_not_from_agentos_are_rejected(client):
    # e.g. another app on the internal network forging the user header
    assert client.get(BASE + "/", headers={"X-AgentOS-User": "liam"}).status_code == 401
    assert client.get(BASE + "/", headers={"X-AgentOS-Proxy-Token": "wrong"}).status_code == 401
    assert client.get("/anything-else").status_code == 401


def test_code_jobs_match_manifest(app_module):
    assert set(app_module.platform.jobs) == {j["id"] for j in MANIFEST.get("jobs", [])}


def test_code_secrets_match_manifest(app_module):
    assert set(app_module.REQUIRED_SECRETS) == {s["name"] for s in MANIFEST.get("secrets", [])}


def test_own_header_only_when_not_embedded(client):
    alone = client.get(BASE + "/", headers=PROXY).text
    framed = client.get(BASE + "/", headers={**PROXY, "Sec-Fetch-Dest": "iframe"}).text
    assert '<header class="own">' in alone and '<header class="own">' not in framed
    assert "agentos:location" in framed  # tells the AgentOS header which page is showing


def test_nav_paths_exist(client):
    for item in MANIFEST.get("nav", []):
        assert client.get(BASE + item["path"], headers=PROXY).status_code == 200, item


def test_follows_the_agentos_colour_scheme(client):
    for value, expected in (("dark", '<html lang="en" data-theme="dark">'), ("light", '<html lang="en" data-theme="light">'),
                            ("system", '<html lang="en">'), ("<x>", '<html lang="en">')):
        client.cookies.set("agentos-theme", value)
        assert expected in client.get(BASE + "/", headers=PROXY).text
    client.cookies.clear()
    assert '<html lang="en">' in client.get(BASE + "/", headers=PROXY).text
