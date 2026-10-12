# Purpose
Public half of AgentOS: the app contract (CONTRACT.md), manifest JSON Schema, `agentos check`, the app template, and the reusable CI workflow that every app repo calls. The private `agentos` repo holds the platform itself.

# Must never
- Contain anything about the host, network, secrets or the private platform internals. This repo is public.
- Change the contract without updating CONTRACT.md, the schema, `agentos check`, the template and tests together.
- Break existing apps: contract changes within v1 must be backwards compatible.

# Commands
- Setup: `uv venv -p 3.12 .venv && uv pip install -p .venv -e '.[dev]'`
- Test: `.venv/bin/pytest -q` (includes a live check of the template app)
- Try the CLI: `.venv/bin/agentos new demo --dir /tmp/demo && .venv/bin/agentos check /tmp/demo`

# Layout
- `CONTRACT.md`: the app contract (source of truth)
- `src/agentos_kit/schema/agentos-v1.json`: manifest schema
- `src/agentos_kit/manifest.py`: load, validate and label manifests (also used by the platform)
- `src/agentos_kit/check.py`: static and live checks
- `src/agentos_kit/template/`: the app template copied by `agentos new` (ids `template-app` / `Template App` are replaced)
- `.github/workflows/build.yml`: reusable workflow called by apps; `ci.yml` tests the kit
- `.claude-plugin/marketplace.json` + `plugins/agentos/`: the `agentos` skill as a Claude Code plugin (Codex uses the same `SKILL.md`). Validate with `claude plugin validate .`

# Data and secrets
None. The build workflow only uses the caller's `GITHUB_TOKEN` to push to GHCR.

# Notes
- Apps call `build.yml@main`, so a push here affects every app's next build. Run the tests first.
- `template/app/agentos_platform.py` is vendored into each app; apps update it by copying the new version.
- The skill must stay generic (public repo): host-specific steps live in the private platform repo's AGENTS.md, which the skill tells agents to read. Keep SKILL.md short; detail goes in `references/`.
- `plugin.json` deliberately has no `version`, so installs track the latest commit.
