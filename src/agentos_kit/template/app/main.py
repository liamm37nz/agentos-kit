"""Template App — a minimal AgentOS app. Replace the example job and UI with your own."""

from __future__ import annotations

import html
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .agentos_platform import JobContext, NAV_SCRIPT, Platform, embedded, theme

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

BASE_PATH = os.environ.get("AGENTOS_BASE_PATH", "/apps/template-app").rstrip("/")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
REQUIRED_SECRETS: list[str] = []  # keep in sync with `secrets` in agentos.yaml
LOG_FILE = DATA_DIR / "hello.log"


def say_hello(ctx: JobContext) -> str:
    ctx.progress("Saying hello…")
    time.sleep(1)
    with LOG_FILE.open("a") as f:
        f.write(datetime.now().astimezone().isoformat(timespec="seconds") + "\n")
    return "Said hello"


def _hellos() -> list[str]:
    return LOG_FILE.read_text().splitlines() if LOG_FILE.exists() else []


def health() -> dict:
    if not os.access(DATA_DIR, os.W_OK):
        return {"status": "error", "message": f"{DATA_DIR} is not writable"}
    missing = [name for name in REQUIRED_SECRETS if not os.environ.get(name)]
    if missing:
        return {"status": "degraded", "message": "missing secrets: " + ", ".join(missing)}
    return {"status": "ok"}


def status() -> dict:
    hellos = _hellos()
    return {
        "summary": f"Last hello {hellos[-1]}" if hellos else "No hellos yet",
        "attention": False,
        "facts": [{"label": "Hellos", "value": str(len(hellos))}],
    }


platform = Platform(health=health, status=status, jobs={"say-hello": say_hello})

app = FastAPI(title="Template App", docs_url=None, redoc_url=None, openapi_url=None)
platform.install(app)  # /platform API + guard: only requests via AgentOS get through


@app.get(BASE_PATH, include_in_schema=False)
def ui_redirect() -> RedirectResponse:
    return RedirectResponse(BASE_PATH + "/")


# Colours as variables: light by default, dark when AgentOS says so or (with no choice made) when the system is dark.
_DARK = "--bg:#0f1216;--text:#e6e9ed;--line:#2a3038;--link:#7aa2ff;color-scheme:dark;"
STYLE = f"""
:root{{--bg:#fff;--text:#1b1f24;--line:#ddd;--link:#2457c5;color-scheme:light}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{{_DARK}}}}}
:root[data-theme="dark"]{{{_DARK}}}
body{{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.5;background:var(--bg);color:var(--text)}}
a{{color:var(--link)}}
.own{{display:flex;gap:1rem;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:.5rem;margin-bottom:1rem}}"""


def page(request: Request, title: str, body: str) -> str:
    """Wrap page content. Inside AgentOS the header and menu come from AgentOS (`nav:` in agentos.yaml),
    so the app's own header is only drawn when it's opened on its own."""
    own_header = "" if embedded(request) else f"""<header class="own">
  <strong>Template App</strong>
  <nav><a href="{BASE_PATH}/">Home</a> <a href="{BASE_PATH}/about">About</a></nav>
</header>"""
    scheme = theme(request)  # 'light' / 'dark' when picked in AgentOS, '' to follow the system
    return f"""<!doctype html>
<html lang="en"{f' data-theme="{scheme}"' if scheme else ""}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{html.escape(title)} · Template App</title>
<style>{STYLE}</style>
</head><body>
{own_header}
{body}
{NAV_SCRIPT}
</body></html>"""


@app.get(BASE_PATH + "/", response_class=HTMLResponse)
def ui_home(request: Request) -> str:
    user = html.escape(request.headers.get("x-agentos-user", "there"))
    rows = "".join(f"<li>{html.escape(h)}</li>" for h in reversed(_hellos()[-20:])) or "<li>None yet</li>"
    return page(request, "Home", f"<h1>Hello, {user}</h1><p>This is the AgentOS app template. Recent hellos:</p><ul>{rows}</ul>")


@app.get(BASE_PATH + "/about", response_class=HTMLResponse)
def ui_about(request: Request) -> str:
    return page(request, "About", "<h1>About</h1><p>A minimal AgentOS app. Replace this page.</p>")
