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

The platform itself (control plane, deployer) is private. This repo has only what app repos and their CI need.
