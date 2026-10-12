"""Load and validate agentos.yaml manifests (CONTRACT.md §3)."""

from __future__ import annotations

import copy
import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SUPPORTED_MAJOR = 1
LABEL = "agentos.manifest"

_SPEC_RE = re.compile(r"^agentos/v(\d+)$")
_CRON_FIELD_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_RESERVED_MOUNTS = ("/data", "/proc", "/sys", "/dev", "/etc", "/usr", "/bin", "/lib")


class ManifestError(Exception):
    """Raised when a manifest cannot be used. `errors` lists every problem found."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def schema() -> dict[str, Any]:
    text = resources.files("agentos_kit").joinpath("schema/agentos-v1.json").read_text()
    return json.loads(text)


def validate(data: Any) -> list[str]:
    """Return every problem with a parsed manifest; an empty list means valid."""
    if not isinstance(data, dict):
        return ["manifest must be a mapping"]

    spec = data.get("spec")
    match = _SPEC_RE.match(spec) if isinstance(spec, str) else None
    if not match:
        return [f"spec: expected 'agentos/v{SUPPORTED_MAJOR}', got {spec!r}"]
    if int(match.group(1)) != SUPPORTED_MAJOR:
        return [f"spec: {spec} is not supported (this kit supports agentos/v{SUPPORTED_MAJOR})"]

    errors = [
        f"{'.'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
        for e in sorted(Draft202012Validator(schema()).iter_errors(data), key=lambda e: list(e.absolute_path))
    ]
    if errors:
        return errors

    job_ids = [j["id"] for j in data.get("jobs", [])]
    for dup in sorted({j for j in job_ids if job_ids.count(j) > 1}):
        errors.append(f"jobs: duplicate id {dup!r}")
    for i, job in enumerate(data.get("jobs", [])):
        if "schedule" in job:
            errors += [f"jobs.{i}.schedule: {e}" for e in _cron_errors(job["schedule"])]

    names = [s["name"] for s in data.get("secrets", [])]
    for dup in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"secrets: duplicate name {dup!r}")
    for name in names:
        if name.startswith("AGENTOS_") or name in ("PORT", "TZ"):
            errors.append(f"secrets: {name!r} is reserved for the platform")

    mounts = [s["mount"] for s in data.get("shared", [])]
    for mount in mounts:
        if any(mount == r or mount.startswith(r + "/") for r in _RESERVED_MOUNTS):
            errors.append(f"shared: mount {mount!r} is reserved")
    for dup in sorted({m for m in mounts if mounts.count(m) > 1}):
        errors.append(f"shared: duplicate mount {dup!r}")

    if data["network"] == "internet" and not data.get("egress"):
        errors.append("egress: required when network is 'internet' — document every external host")
    return errors


def with_defaults(data: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(data)
    out.setdefault("port", 8080)
    out.setdefault("ui", True)
    out.setdefault("memory", "512m")
    for key in ("jobs", "secrets", "shared", "egress"):
        out.setdefault(key, [])
    for job in out["jobs"]:
        job.setdefault("catch_up", "skip")
        job.setdefault("timeout", "30m")
    for item in out["shared"]:
        item.setdefault("rw", False)
    return out


def parse(text: str) -> dict[str, Any]:
    """Parse and validate manifest text; return it with defaults applied."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError([f"invalid YAML: {exc}"]) from exc
    errors = validate(data)
    if errors:
        raise ManifestError(errors)
    return with_defaults(data)


def load(path: str | Path) -> dict[str, Any]:
    return parse(Path(path).read_text())


def to_label(manifest: dict[str, Any]) -> str:
    """Compact JSON stored in the image label `agentos.manifest`."""
    return json.dumps(manifest, separators=(",", ":"), sort_keys=True)


def from_label(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ManifestError([f"label {LABEL} is not valid JSON: {exc}"]) from exc
    errors = validate(data)
    if errors:
        raise ManifestError(errors)
    return with_defaults(data)


def _cron_errors(expr: str) -> list[str]:
    """Check each cron field holds numbers in range (supports *, lists, ranges and steps)."""
    errors = []
    for field, (lo, hi) in zip(expr.split(), _CRON_FIELD_RANGES):
        for part in field.split(","):
            base, _, step = part.partition("/")
            if step and not step.isdigit():
                errors.append(f"bad step in {part!r}")
            if base == "*":
                continue
            bounds = base.split("-")
            if len(bounds) > 2 or not all(b.isdigit() for b in bounds):
                errors.append(f"unsupported value {part!r} (use numbers, *, ranges, lists and steps)")
                continue
            if any(not lo <= int(b) <= hi for b in bounds):
                errors.append(f"{part!r} out of range {lo}-{hi}")
    return errors
