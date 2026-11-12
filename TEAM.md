# PharmAgentics team guide

How to use, host, run and deploy the PharmAgentics web app. For the design behind it, see `specs/core-007-rbac-uat-deployment/` (accounts, roles, deployment) and `specs/brief-002-triage-investigation/` (triage review, the agent team). Deeper deployment detail is in [`deploy/README.md`](deploy/README.md).

## What is live

**App:** https://pharmagentics-app-18389319270.us-central1.run.app (Google Cloud project `pharmagentics`, us-central1). Synthetic data only.

| Sign-in account | Role | What it sees |
| :- | :- | :- |
| `uat-analyst` | Commercial Analyst (P1) | Runs briefs, reviews the triage plan, sees every number's source, approves or rejects |
| `uat-director` | Brand Director (P3) | Executive summaries of approved briefs only; no evidence |
| `uat-forecast-analyst` | Commercial Analytics Analyst (CA) | Forecast section (coming soon) |
| `uat-forecast-manager` | Brand Manager (BM) | Forecast section (coming soon) |

Passwords are the `UAT_PASSWORD_*` lines in `deploy/.env.uat` (see setup below). Never commit that file or paste passwords into chat, issues or slides.

After the app has been idle, the first sign-in takes 15 to 30 seconds while the sign-in service wakes up. A "Starting the sign-in service" page retries by itself.

## One-time setup

1. **Repository.** Clone it, install [uv](https://docs.astral.sh/uv/getting-started/installation/), run `uv sync`, then load the data: `uv run python src/pharmagentics/data/load_duckdb.py`.
2. **Tools.** Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and the [gcloud CLI](https://cloud.google.com/sdk/docs/install).
3. **Google access.** Send Michael the Google account you want to use (Columbia or Gmail). He grants it with `deploy/gcp.py team`. Then run `gcloud auth login` and sign in with that account.
4. **Shared settings.** Pull the team's `deploy/.env.uat` (sign-in passwords, worker token, secrets):

   ```powershell
   uv run python deploy/gcp.py env-pull --project pharmagentics --account <your Google account>
   ```

After that, every command in this guide works with `--account <your Google account>`.

## Use the app

1. Sign in as `uat-analyst`, choose a territory and a week, pick an engine, and generate.
   - **Scripted:** instant. The fixed order of checks runs with the manager off.
   - **Agent team:** the manager, Data Forensics and the Driver Investigator run on a teammate's machine (see below). It takes minutes and is experimental. You can type your own question.
2. **Triage review.** Code proposes the stories to investigate. On the agent engine, the manager's changes are shown and flagged. Keep, drop or reorder the stories, then approve.
3. **The brief.** Every underlined number is a claim: click it to see the query and record behind it. "How this brief was made" shows each stage and who did it: code, an agent or a person.
4. Approve or reject the brief. Only approved briefs reach `uat-director`.

## Host the agent team (anyone on the team)

The app never runs a model. When someone picks **Agent team**, the request waits in a queue until a teammate's machine takes it. Any number of teammates can host at once: each machine runs one request at a time, and the app shows who is online.

1. Install [Ollama](https://ollama.com/download) and pull the model: `ollama pull qwen3:4b-instruct-2507-q4_K_M`. A GPU with 6 GB or more is best; a CPU works, but slowly.
2. Load the data (setup step 1). Your data version must match the app's. It does as long as both come from the same `data/agent_visible/` release.
3. Start the worker and leave it running:

   ```powershell
   uv run python agents/brand-briefing/run_worker.py --app https://pharmagentics-app-18389319270.us-central1.run.app
   ```

   It shows in the app under your computer's name (`--name` changes it). Stop it with Ctrl+C.

Your machine only calls out to the app. Nothing on it becomes reachable from the internet, and Ollama stays on localhost. Don't run evals while you host: one GPU runs one model at a time.

## Run everything on your laptop

```powershell
uv run python deploy/make_env.py        # only if you did not env-pull; makes local secrets
docker compose up --build               # Keycloak on :8081, app on :8080
uv run python agents/brand-briefing/run_worker.py --app http://localhost:8080   # optional: local agent host
```

Open http://localhost:8080. Without Keycloak, `docker run --rm -p 8080:8080 -e PHARMAGENTICS_AUTH=dev pharmagentics:uat` gives you a page of stand-in accounts, one per role.

## Deploy, check and roll back

```powershell
uv run python deploy/gcp.py status   --project pharmagentics --account <you>   # URLs and live revisions
uv run python deploy/gcp.py app      --project pharmagentics --account <you>   # build and deploy the app
uv run python deploy/gcp.py rollback --project pharmagentics --account <you>   # previous app revision, no rebuild
uv run python deploy/gcp.py keycloak --project pharmagentics --account <you>   # only after a realm or password change
```

Once the GitHub repository variables are set, a merge to `main` deploys the app automatically, but only after CI passes (tests, golden set, image content check). Keycloak never deploys from CI.

**Add a UAT participant:** add a user with one realm role to `deploy/keycloak/realm-pharmagentics.json`, with `"value": "${UAT_PASSWORD_<NAME>}"`. Add `UAT_PASSWORD_<NAME>=...` to your `deploy/.env.uat`, then run `env-push` followed by `keycloak`. `keycloak` refuses to deploy if your `.env.uat` differs from the shared copy. Run `env-pull` first if someone else changed it.

## Rules

- **Ground truth never enters the repo, the image or the app.** The answer key and held-out parameters stay in the private store (`CLAUDE.md`, hard rules). Agent code never reads `eval/`.
- **Every number is a claim filled by code.** The app refuses an agent brief with a number that has no claim behind it.
- **Don't create cloud resources by hand.** Use `deploy/gcp.py`. Everything is sized for the free tiers, with a $1 budget alert. Your access covers deploys, rollbacks, logs and secrets, but not billing or granting access.
- Say "competitive intelligence", never "surveillance". "New patients" means NBRx only. No output names a rep.

## Forecast lane

The Forecast section in the app is a placeholder for Alvin and Sienna. To wire in the lane:
- Add routes in `src/pharmagentics/api/forecast.py`, following the Briefing routes in `app.py`.
- Replace `ForecastWorkspace` in `frontend/figma-make/src/App.tsx`.
- Set `lanes.forecast.available` to true in `src/pharmagentics/api/roles.json`.

The roles CA (analyst view) and BM (leadership view) already exist.

## When something is off

| You see | Do |
| :- | :- |
| "No host online" on Agent team | Nobody is running the worker; start it (Host the agent team) |
| An agent job fails with "did not pass the traceability check" | The agent stated a number with no claim; the app refused it as designed. Run it again or use Scripted |
| "Ran on data version X, not this app's Y" | Your local data differs from the app's; reload the data from the same release |
| `keycloak` says your `.env.uat` differs | `env-pull` (take the team's) or `env-push` (if your change should become the team's) |
| `401` from the worker | Your worker token is stale: `env-pull` |
