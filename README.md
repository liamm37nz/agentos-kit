# agentos-kit

Tooling for building apps that run on AgentOS, a self-hosted platform for personal apps and agents.

- **[CONTRACT.md](CONTRACT.md)**: what an app must do to run on AgentOS
- **`agentos check`**: validates an app repo, and a running app, against the contract
- **`agentos new <id>`**: creates a new app from the [template](src/agentos_kit/template/)
- **[Reusable build workflow](.github/workflows/build.yml)**: check, test, build, live-check and publish to GHCR

```bash
pip install git+https://github.com/liamm37nz/agentos-kit
agentos new my-app
cd my-app && agentos check .
```

## The `agentos` skill (Claude Code and Codex)

Teaches a coding agent to build new AgentOS apps, migrate existing projects onto AgentOS, and operate them. Source: [`plugins/agentos/skills/agentos/`](plugins/agentos/skills/agentos/).

**Claude Code** (once per machine):

```text
/plugin marketplace add liamm37nz/agentos-kit
/plugin install agentos@agentos-kit
```

Then `/plugin` → Marketplaces → agentos-kit → Enable auto-update, or update by hand with `/plugin marketplace update agentos-kit`. Use it by asking for an AgentOS task, or with `/agentos`.

**Codex** reads skills from `~/.agents/skills`:

```bash
git clone https://github.com/liamm37nz/agentos-kit ~/.agentos-kit
mkdir -p ~/.agents/skills && ln -s ~/.agentos-kit/plugins/agentos/skills/agentos ~/.agents/skills/agentos
```

Update with `git -C ~/.agentos-kit pull`.

The platform itself (control plane, deployer) is private. This repo has only what app repos, their CI and coding agents need.
