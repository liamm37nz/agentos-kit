import shutil
import socket
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path

import httpx
import pytest

from agentos_kit import manifest as mf
from agentos_kit.check import check_live, check_repo
from agentos_kit.cli import main

TEMPLATE = Path(str(resources.files("agentos_kit").joinpath("template")))


def errors(findings):
    return [f.message for f in findings if f.level == "error"]


def test_template_passes_static_check():
    assert errors(check_repo(TEMPLATE)) == []


def test_static_check_reports_missing_pieces(tmp_path):
    shutil.copytree(TEMPLATE, tmp_path / "app")
    root = tmp_path / "app"
    (root / "CLAUDE.md").write_text("nothing here\n")
    (root / "AGENTS.md").write_text("# Purpose\nx\n")
    (root / "Dockerfile").unlink()
    found = "\n".join(errors(check_repo(root)))
    assert "missing required file Dockerfile" in found
    assert "CLAUDE.md must contain '@AGENTS.md'" in found
    assert "missing heading '# Must never'" in found


def test_new_creates_a_passing_app(tmp_path, capsys):
    assert main(["new", "gst-manager", "--dir", str(tmp_path / "gst")]) == 0
    root = tmp_path / "gst"
    assert mf.load(root / "agentos.yaml")["id"] == "gst-manager"
    assert mf.load(root / "agentos.yaml")["name"] == "Gst Manager"
    assert "/apps/gst-manager/" in (root / "AGENTS.md").read_text()
    assert errors(check_repo(root)) == []
    assert main(["check", str(root)]) == 0


def test_new_rejects_bad_id(tmp_path):
    assert main(["new", "Bad_Id", "--dir", str(tmp_path / "x")]) == 2


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_template(tmp_path):
    """Run the template app with uvicorn, as the CI live check does with the container."""
    port = _free_port()
    env = {"AGENTOS_TOKEN": "live-token", "AGENTOS_BASE_PATH": "/apps/template-app", "DATA_DIR": str(tmp_path), "PATH": ""}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=TEMPLATE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                httpx.get(url + "/platform/health", timeout=0.5)
                break
            except httpx.HTTPError:
                time.sleep(0.1)
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_template_passes_live_check(running_template):
    manifest = mf.load(TEMPLATE / "agentos.yaml")
    assert errors(check_live(running_template, "live-token", manifest)) == []


def test_live_check_catches_wrong_token(running_template):
    manifest = mf.load(TEMPLATE / "agentos.yaml")
    found = "\n".join(errors(check_live(running_template, "not-the-token", manifest)))
    assert "/platform/health: expected 200, got 401" in found


def test_contract_command(capsys):
    assert main(["contract"]) == 0
    assert "# AgentOS App Contract" in capsys.readouterr().out


def test_live_check_rejects_app_without_guard(tmp_path):
    """An app that only includes the router (the pre-guard way) fails the live check."""
    root = tmp_path / "old"
    shutil.copytree(TEMPLATE, root)
    main_py = root / "app" / "main.py"
    main_py.write_text(main_py.read_text().replace("platform.install(app)", "app.include_router(platform.router)"))
    port = _free_port()
    env = {"AGENTOS_TOKEN": "t", "AGENTOS_BASE_PATH": "/apps/template-app", "DATA_DIR": str(tmp_path), "PATH": ""}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=root, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/platform/health", timeout=0.5)
                break
            except httpx.HTTPError:
                time.sleep(0.1)
        found = "\n".join(errors(check_live(f"http://127.0.0.1:{port}", "t", mf.load(root / "agentos.yaml"))))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert "use platform.install(app)" in found
