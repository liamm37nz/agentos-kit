# New AgentOS app

## 1. Interview before writing code

Ask only what you can't infer, but make sure you can answer all of these. Summarise the answers back to the user as a short design and get a yes before building.

| Question | Becomes |
|---|---|
| What does it do, for whom, and what does "done" look like? | `description`, `AGENTS.md` Purpose |
| What does the user look at? (dashboard, list, form, nothing) | `ui: true/false`, UI design |
| What data does it read, and from where? | integrations, `egress`, `secrets` |
| What data leaves the server, to which service? Especially to AI providers. | `egress[].data` — minimise it (no account numbers, names, balances unless essential) |
| What does it write, and where? Anything outside its own `/data`? | `network`, approval design |
| Is anything irreversible? (submit, publish, pay, email someone else, delete remote data) | a human approval step inside the app |
| What runs on a schedule, how often, and what if a run is missed? | `jobs[].schedule`, `catch_up: once` for things that must not be skipped |
| What credentials does it need? | `secrets` names and descriptions |
| Does it need files from outside the app? (e.g. a notes vault) | `shared` paths (read-only unless writing is essential) |
| Does it need data another app owns, or should other apps use its data? | `uses` / `provides` connections — never a shared database |
| What would make the owner need to look at it? | `/platform/status` `attention` and `facts` |

## 2. Create the repo

```bash
agentos new <id> --name "<Display Name>"   # id: lowercase, digits, hyphens; permanent
cd <id>
```

The template is a working FastAPI app: the four `/platform/*` endpoints (vendored in `app/agentos_platform.py`; don't edit it), an example job, a UI under `AGENTOS_BASE_PATH`, tests, Dockerfile and CI workflow. Prefer extending it over replacing it. If the app must use another language or framework, keep the same files and implement the contract's platform API yourself.

## 3. Build it

- **Manifest first.** Fill `agentos.yaml` from the interview: description, `network` (`none` unless it truly needs the internet), every `egress` host with its purpose and the data sent, `jobs`, `secrets`.
- **Jobs**: one function per declared job, registered in `Platform(jobs={...})`. Report progress with `ctx.progress()`. Return a short result message; raise on failure. Jobs must be safe to re-run (idempotent) because catch-up and Run now exist.
- **Secrets**: list them in `REQUIRED_SECRETS`. With any missing, `/platform/health` returns `degraded` and the app still starts; CI relies on this.
- **Status card**: `summary` is one line the owner reads on the dashboard; `facts` are 2–4 short label/value pairs; set `attention: true` only when the owner should act.
- **UI**: every route under `AGENTOS_BASE_PATH`; use relative links or prefix with the base path. The logged-in user is in the `X-AgentOS-User` header; do no authentication of your own. Server-rendered HTML is the default; vendor any JS/CSS (no CDNs).
- **AI calls**: request structured output (JSON schema / tool calls), validate it in code, and keep the model away from decisions about where data goes. Put prompts and model names in code, not secrets.
- **Data**: SQLite under `/data` (`DATA_DIR` locally) in WAL mode. Write schema creation/migration so a fresh `/data` works.
- **Request guard**: keep `platform.install(app)` from the template. Test clients for UI routes must send `X-AgentOS-Proxy-Token: <AGENTOS_TOKEN>` (the template's tests show how), and keep a test that requests without it get `401`.
- **Tests**: cover the jobs, the status/health logic, and anything that parses external data. Mock external services.

### Connections to other apps

Use when data belongs to one app but another needs it (e.g. a bank-sync app owns transactions; budget and GST apps read them). Read the contract's Connections section first (`agentos contract`).

- **Split by trust, not by feature.** The app holding a credential (e.g. a bank token) should be the only one that does; consumers get just the scope they need and often need no internet at all (`network: none`).
- **Provider**: declare `provides: [{id, description}]`. Serve the API under `/connect/<scope>/…` at the root path (not under the base path). The guard only lets in callers granted that scope; `caller(request)` tells you which app is calling. Default to read-only; return only what the description promises; never let a caller trigger an irreversible external action.
- **Consumer**: declare `uses: [{app, scope, reason}]` (`optional: true` if the app can run without it). `connection("<app>")` returns `(url, token)` or `None`. Call with `Authorization: Bearer <token>`, short timeouts, and handle the provider being down by setting `attention` in `/platform/status` — never by failing `/platform/health`.
- **Treat provider data as untrusted input** like any external data (it may contain text from banks, emails, etc.).
- Version the API by adding scopes or fields; don't break existing consumers. Changing a scope's meaning needs the owner to re-grant.
- Test both sides: the provider with a fake grant (`Platform(..., clients=...)`), the consumer against a stubbed provider.

## 4. Document it

`AGENTS.md` (required headings: Purpose, Must never, Commands, Layout, Data and secrets, Notes) under ~100 lines. Put the app's own "must never" rules there (e.g. "never submit the return to Xero"). Add `ARCHITECTURE.md` when there's more than one moving part. Record non-obvious decisions as ADRs in `docs/decisions/`.

## 5. Ship it

```bash
pytest -q && agentos check .
gh repo create <owner>/<id> --private --source . --push
gh run watch "$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

Then register it in the platform repo (`<owner>/agentos`): add to `apps.yaml`

```yaml
  - id: <id>
    image: ghcr.io/<owner>/<id>
```

commit with a clear message and push. The deployer reads `apps.yaml` within a minute.

## 6. Hand over

- If it requires connections, it shows **awaiting connections** until the owner grants them on the **Connections** page. Say which, and why each is needed.
- If it declares secrets, it will show **missing secrets** until they're entered. Tell the user each secret's name, what it is, where to get it, and to enter it at **AgentOS → app → Secrets**. It deploys automatically once they're all set.
- Verify on the platform as described in [operate.md](operate.md): deployed, healthy, status card sensible, jobs listed on the Schedule page with the expected next run. Use **Run now** (or ask the user to) for a first job run if it's safe.
- Report: repo URL, what's verified, what's waiting on the user.
