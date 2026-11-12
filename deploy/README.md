# UAT deployment (core-007)

One app image (Meghna's UI and the Briefing API on one origin, scripted engine only, no model) and one Keycloak image (free open-source edition, no database). It runs the same way on a laptop (`docker compose`) and on Cloud Run.

| Role (Keycloak realm role) | Persona | Sees |
| :- | :- | :- |
| `briefing-analyst` | P1 Commercial Analyst | Full brief with claims and evidence; approves or rejects; can preview the leadership view |
| `briefing-director` | P3 Brand Director | Executive summary only, of briefs the analyst approved |
| `forecast-analyst` | CA Commercial Analytics Analyst | "Not available yet" (reserved; Alvin and Sienna confirm) |
| `forecast-manager` | BM Brand Manager | "Not available yet" (reserved; Alvin and Sienna confirm) |

The role-to-permission map is [`src/pharmagentics/api/roles.json`](../src/pharmagentics/api/roles.json); the realm (roles, client, UAT accounts) is [`keycloak/realm-pharmagentics.json`](keycloak/realm-pharmagentics.json), with every password and secret as a `${PLACEHOLDER}`.

## Local

```powershell
uv run python deploy/make_env.py     # once: random secrets and passwords in deploy/.env.uat (git-ignored)
docker compose up --build            # Keycloak on :8081, app on :8080
```

Open http://localhost:8080 and sign in as `uat-analyst` or `uat-director` (passwords: the `UAT_PASSWORD_*` lines in `deploy/.env.uat`). Keycloak's admin console is not used: accounts and roles are configuration, reloaded at every start.

Without Keycloak: `docker run --rm -p 8080:8080 -e PHARMAGENTICS_AUTH=dev pharmagentics:uat` gives a page of stand-in identities, one per role. Dev sign-in refuses to start on Cloud Run.

## Google Cloud

Needs: an **open** billing account, `gcloud` signed in, Docker running. Every command passes `--project`, so your default gcloud project is never changed.

```powershell
uv run python deploy/gcp.py setup    --project <new-project-id> --billing <ACCOUNT_ID>
uv run python deploy/gcp.py keycloak --project <new-project-id>
uv run python deploy/gcp.py app      --project <new-project-id>
uv run python deploy/gcp.py status   --project <new-project-id>
```

`setup` creates, in `us-central1`: the project (if new) and its billing link; an Artifact Registry repository that keeps the two newest images per name; a Cloud Storage bucket for approvals and UAT events; five secrets (session secret, OIDC client secret, rendered realm, worker token, and the shared `.env.uat` for the team), each with one active version (free tier: 6); three service accounts (app runtime, Keycloak runtime, GitHub deployer); Workload Identity Federation for GitHub Actions on `main` only; and a $1 budget with alerts at 1%, 50% and 100%. It prints four `gh variable set` lines: set them to turn on automatic deploys.

**Automatic deploys.** After the `DuckDB data foundation` checks pass on a push to `main` (tests, golden set, API, image build and content check), [`deploy-uat.yml`](../.github/workflows/deploy-uat.yml) builds the app image, checks again that it holds no `eval/`, `SoT/`, `.env` or ground-truth file, pushes it and deploys it. Only the image changes. Keycloak is never deployed from CI.

**Rollback.** `uv run python deploy/gcp.py rollback --project <id>` puts all traffic on the previous revision (no rebuild). `--service keycloak` does the same for Keycloak.

**Adding a UAT participant.** Add a user to the realm file with `"value": "${UAT_PASSWORD_<NAME>}"` and one realm role, add `UAT_PASSWORD_<NAME>=...` to `deploy/.env.uat`, then run `deploy/gcp.py env-push` and `deploy/gcp.py keycloak`. The deploy refuses a placeholder with no value. Never commit a password.

## Team access (FR-029, FR-030)

Any teammate can deploy, roll back and read the UAT passwords with their own Google account. No key file is handed out, and `deploy/.env.uat` is never committed: the whole file is kept in Secret Manager as `pa-env-uat`, readable by everyone on the team. That is a deliberate choice (2026-11-11): the team can run the deployment without the owner, and every teammate can see every UAT password and secret.

Owner, once per teammate (Columbia or Gmail accounts both work; the org allows any domain):

```powershell
uv run python deploy/gcp.py env-push --project pharmagentics --account mwc2150@columbia.edu   # first time only
uv run python deploy/gcp.py team --project pharmagentics --account mwc2150@columbia.edu --member <teammate email> [--member ...]
uv run python deploy/gcp.py team --project pharmagentics --account mwc2150@columbia.edu --remove <email>   # revoke
uv run python deploy/gcp.py team --project pharmagentics --account mwc2150@columbia.edu                   # list
```

A teammate gets: Viewer (status, logs, billing-free reads), Cloud Run Admin, Artifact Registry Writer, Secret Manager Secret Version Manager and Secret Accessor, Service Account User on the app and Keycloak runtime accounts, and read access to the UAT state bucket. Not billing, budgets, deleting the project, or granting access to anyone else; `setup` and `team` stay with the owner.

Teammate, once: install the [gcloud CLI](https://cloud.google.com/sdk/docs/install) and Docker, run `gcloud auth login`, then

```powershell
uv run python deploy/gcp.py env-pull --project pharmagentics --account <your Google account>
```

After that, every command in this README works for them with `--account <their account>`. If they change a password or add a participant, they run `env-push` before `keycloak`. `keycloak` refuses to deploy from a local `.env.uat` that differs from the shared copy, so a stale file cannot overwrite someone else's passwords; `env-pull --force` takes the shared copy.

## Live agent runs on your PC (core-007 FR-028)

The app never runs a model. When an analyst picks **Agent team**, the app queues the job; a worker on your PC takes it, runs build 3 (manager, Data Forensics, Driver Investigator) on Ollama, and posts the result. The app admits a brief only if every number in it is a claim with evidence on the app's data version.

```powershell
# Ollama running with qwen3:4b-instruct-2507-q4_K_M; the release loaded locally (same data version as the app)
uv run python agents/brand-briefing/run_worker.py --app https://pharmagentics-app-18389319270.us-central1.run.app
# or, against the local stack:
uv run python agents/brand-briefing/run_worker.py --app http://localhost:8080
```

The token comes from `PHARMAGENTICS_WORKER_TOKEN` in `deploy/.env.uat` (also a secret on Cloud Run). The worker polls every 10 s, outbound only; nothing on your PC is reachable from the internet. One job runs at a time. When the worker is stopped, the UI shows "host offline" and requests wait. Do not run evals while hosting: one 6 GB GPU serves one model run at a time.

## Cloud agent host (core-007 FR-031)

If no teammate's machine is hosting, the app starts a Cloud Run **job**, `pharmagentics-agent`: Ollama (CPU only) with the qwen3 model baked into the image, plus the same worker. It drains the queue, exits when idle, and bills only while it runs. Nothing leaves the project, so there is no external model provider.

```powershell
uv run python deploy/gcp.py agent --project pharmagentics --account <you>   # build, push, create the job, let the app start it
```

- **Size:** 8 vCPU, 8 GiB, one task, no retries, one hour at most.
- **Budget:** the app counts the job's seconds (and a fixed overhead per start) per month in the state bucket (`cloud/usage-YYYY-MM.json`) and starts nothing past `PHARMAGENTICS_CLOUD_MAX_SECONDS` (default 18,000 s: 8 vCPUs for 5 hours, 80% of the free tier's 180,000 vCPU-seconds). Set `PHARMAGENTICS_CLOUD_ETA_MINUTES` in `deploy/.env.uat` to show an estimate in the UI.
- **Slow by design:** the agent's wall-clock caps are stretched 6x (`PHARMAGENTICS_AGENT_WALL_SCALE`) so slow is not mistaken for stuck. A teammate's GPU always goes first.
- **Permissions:** the app's service account may only *start* this job (`roles/run.invoker` on it); the job's own service account may only read the worker token.
- **Storage:** the image is about 3 GB (the model). Artifact Registry keeps two versions and shares the unchanged layers.

## Cost

Everything is sized for the free tiers (core-007 SC-003: under $1 a month). Both services scale to zero and are capped (Keycloak 1 instance, app 2), so idle time costs nothing. A cold start takes about 16 s for Keycloak and 2 s for the app.

| Resource | Use | Free tier |
| :- | :- | :- |
| Cloud Run | Keycloak 1 vCPU / 1 GiB, app 1 vCPU / 512 MiB, billed per request | 180,000 vCPU-s and 360,000 GiB-s a month |
| Artifact Registry | 2 images per name (about 1 GB in all) | 0.5 GB; the rest is about $0.05 a month |
| Secret Manager | 5 active versions | 6 versions, 10,000 accesses |
| Cloud Storage | a few hundred small JSON files | 5 GB, 5,000 Class A and 50,000 Class B operations |
| GitHub Actions | build and push | the repository's Actions minutes |

## Files

| File | What it is |
| :- | :- |
| `../Dockerfile`, `../.dockerignore` | App image; the ignore file is an allow-list |
| `../compose.yaml` | Local stack |
| `keycloak/Dockerfile` | Keycloak for Cloud Run: production mode, dev-file store, realm imported at start |
| `keycloak/realm-pharmagentics.json` | Realm, roles, client, UAT accounts (placeholders only) |
| `make_env.py` | Writes `deploy/.env.uat` |
| `gcp.py`, `gcp-cleanup-policy.json` | Google Cloud setup, deploys, status, rollback |
