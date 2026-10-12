"""Command-line entry point: `agentos check | label | new`."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from importlib import resources
from pathlib import Path

from . import __version__
from . import manifest as mf
from .check import check_live, check_repo

TEMPLATE_ID = "template-app"
TEMPLATE_NAME = "Template App"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentos", description="AgentOS app kit")
    parser.add_argument("--version", action="version", version=f"agentos-kit {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="check an app repo, and optionally a running app, against the contract")
    p.add_argument("path", nargs="?", default=".", help="app repo (default: current directory)")
    p.add_argument("--live", metavar="URL", help="also probe a running app, e.g. http://localhost:8080")
    p.add_argument("--token", help="AGENTOS_TOKEN the running app was started with (required with --live)")

    sub.add_parser("contract", help="print the AgentOS app contract (CONTRACT.md) for this kit version")

    p = sub.add_parser("label", help="print the agentos.manifest image label value")
    p.add_argument("path", nargs="?", default="agentos.yaml")

    p = sub.add_parser("new", help="create a new app from the template")
    p.add_argument("id", help="app id, e.g. gst")
    p.add_argument("--name", help="display name (default: from id)")
    p.add_argument("--dir", help="target directory (default: ./<id>)")

    args = parser.parse_args(argv)
    return {"check": _check, "contract": _contract, "label": _label, "new": _new}[args.cmd](args)


def _check(args) -> int:
    findings = check_repo(args.path)
    if args.live:
        if not args.token:
            print("error: --token is required with --live", file=sys.stderr)
            return 2
        try:
            manifest = mf.load(Path(args.path) / "agentos.yaml")
        except (mf.ManifestError, OSError) as exc:
            print(f"error: cannot run live checks without a valid manifest: {exc}", file=sys.stderr)
            return 1
        findings += check_live(args.live, args.token, manifest)

    for f in findings:
        print(f"{f.level.upper():8} {f.message}")
    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    scope = "repo + live app" if args.live else "repo"
    print(f"\nagentos check ({scope}): {'FAILED' if errors else 'passed'} — {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def _contract(args) -> int:
    packaged = resources.files("agentos_kit").joinpath("CONTRACT.md")
    source = Path(__file__).resolve().parents[2] / "CONTRACT.md"  # editable install / repo checkout
    for candidate in (packaged, source):
        if candidate.is_file():
            print(candidate.read_text())
            return 0
    print("error: CONTRACT.md not found in this installation", file=sys.stderr)
    return 1


def _label(args) -> int:
    try:
        print(mf.to_label(mf.load(args.path)))
    except mf.ManifestError as exc:
        print("\n".join(f"error: {e}" for e in exc.errors), file=sys.stderr)
        return 1
    return 0


def _new(args) -> int:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,38}[a-z0-9]", args.id):
        print("error: id must be 2-40 chars of lowercase letters, digits and hyphens", file=sys.stderr)
        return 2
    name = args.name or args.id.replace("-", " ").title()
    target = Path(args.dir or args.id)
    if target.exists() and any(target.iterdir()):
        print(f"error: {target} exists and is not empty", file=sys.stderr)
        return 1

    with resources.as_file(resources.files("agentos_kit").joinpath("template")) as src:
        shutil.copytree(src, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))
    for path in target.rglob("*"):
        if path.is_file():
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            new = text.replace(TEMPLATE_ID, args.id).replace(TEMPLATE_NAME, name)
            if new != text:
                path.write_text(new)
    print(f"Created {target}/ — next: edit agentos.yaml and AGENTS.md, then `agentos check {target}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
