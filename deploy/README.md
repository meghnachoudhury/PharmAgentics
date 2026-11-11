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

`setup` creates, in `us-central1`: the project (if new) and its billing link; an Artifact Registry repository that keeps the two newest images per name; a Cloud Storage bucket for approvals and UAT events; three secrets (session secret, OIDC client secret, rendered realm), each with one active version; three service accounts (app runtime, Keycloak runtime, GitHub deployer); Workload Identity Federation for GitHub Actions on `main` only; and a $1 budget with alerts at 1%, 50% and 100%. It prints four `gh variable set` lines: set them to turn on automatic deploys.

**Automatic deploys.** After the `DuckDB data foundation` checks pass on a push to `main` (tests, golden set, API, image build and content check), [`deploy-uat.yml`](../.github/workflows/deploy-uat.yml) builds the app image, checks again that it holds no `eval/`, `SoT/`, `.env` or ground-truth file, pushes it and deploys it. Only the image changes. Keycloak is never deployed from CI.

**Rollback.** `uv run python deploy/gcp.py rollback --project <id>` puts all traffic on the previous revision (no rebuild). `--service keycloak` does the same for Keycloak.

**Adding a UAT participant.** Add a user to the realm file with `"value": "${UAT_PASSWORD_<NAME>}"` and one realm role, add `UAT_PASSWORD_<NAME>=...` to `deploy/.env.uat`, then run `deploy/gcp.py keycloak`. The deploy refuses a placeholder with no value. Never commit a password.

## Cost

Everything is sized for the free tiers (core-007 SC-003: under $1 a month). Both services scale to zero and are capped (Keycloak 1 instance, app 2), so idle time costs nothing. A cold start takes about 16 s for Keycloak and 2 s for the app.

| Resource | Use | Free tier |
| :- | :- | :- |
| Cloud Run | Keycloak 1 vCPU / 1 GiB, app 1 vCPU / 512 MiB, billed per request | 180,000 vCPU-s and 360,000 GiB-s a month |
| Artifact Registry | 2 images per name (about 1 GB in all) | 0.5 GB; the rest is about $0.05 a month |
| Secret Manager | 3 active versions | 6 versions, 10,000 accesses |
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
