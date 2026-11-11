"""Google Cloud deployment for UAT (core-007 US4, US5). Free-tier resources only.

Every gcloud call passes --project, so the global gcloud config is never changed.

  uv run python deploy/gcp.py setup    --project ID --billing ACCOUNT_ID   # once
  uv run python deploy/gcp.py keycloak --project ID                        # realm or Keycloak change
  uv run python deploy/gcp.py app      --project ID                        # manual app deploy (CI does this on main)
  uv run python deploy/gcp.py status   --project ID
  uv run python deploy/gcp.py rollback --project ID [--service app|keycloak]

What it creates (us-central1): an Artifact Registry repo that keeps 2 images per name; a
Cloud Storage bucket for approvals and UAT events; three secrets (session secret, OIDC client
secret, rendered realm); three service accounts (app runtime, Keycloak runtime, GitHub
deployer); Workload Identity Federation for GitHub Actions on main; two Cloud Run services
scaled to zero; a $1 budget alert. Secrets come from deploy/.env.uat (deploy/make_env.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENV_FILE = HERE / ".env.uat"
REALM = HERE / "keycloak" / "realm-pharmagentics.json"
REPO = "pharmagentics"
APP, KC = "pharmagentics-app", "pharmagentics-keycloak"
SA = {"app": "pa-app", "kc": "pa-keycloak", "deployer": "pa-deployer"}
SECRETS = {"session": "pa-session-secret", "client": "pa-oidc-client-secret", "realm": "pa-keycloak-realm"}
APIS = ["run.googleapis.com", "artifactregistry.googleapis.com", "secretmanager.googleapis.com",
        "iam.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com",
        "cloudresourcemanager.googleapis.com", "billingbudgets.googleapis.com", "storage.googleapis.com"]
GCLOUD = shutil.which("gcloud") or "gcloud"


class Ctx:
    def __init__(self, project: str, region: str):
        self.project, self.region = project, region

    def gc(self, *args: str, input: str | None = None, check: bool = True, quiet_fail: bool = False) -> str:
        cmd = [GCLOUD, *args, f"--project={self.project}", "--quiet"]
        if not quiet_fail:
            print("  $ gcloud " + " ".join(a if len(a) < 90 else a[:87] + "..." for a in args))
        r = subprocess.run(cmd, input=input, capture_output=True, text=True)
        if check and r.returncode != 0:
            sys.exit(f"gcloud failed ({r.returncode}): {' '.join(args[:4])}\n{r.stderr.strip()}")
        return r.stdout.strip() if r.returncode == 0 else ""

    def ok(self, *args: str) -> bool:
        return subprocess.run([GCLOUD, *args, f"--project={self.project}", "--quiet"], capture_output=True).returncode == 0

    @property
    def number(self) -> str:
        return self.gc("projects", "describe", self.project, "--format=value(projectNumber)", quiet_fail=True)

    def url(self, service: str) -> str:
        return f"https://{service}-{self.number}.{self.region}.run.app"  # Cloud Run's deterministic URL

    def sa(self, key: str) -> str:
        return f"{SA[key]}@{self.project}.iam.gserviceaccount.com"

    @property
    def registry(self) -> str:
        return f"{self.region}-docker.pkg.dev/{self.project}/{REPO}"

    @property
    def bucket(self) -> str:
        return f"{self.project}-uat-state"


def read_env() -> dict[str, str]:
    if not ENV_FILE.is_file():
        sys.exit(f"{ENV_FILE} is missing. Run: uv run python deploy/make_env.py")
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def render_realm(env: dict[str, str], app_url: str) -> str:
    values = {**env, "PHARMAGENTICS_APP_URL": app_url}
    missing = sorted(set(re.findall(r"\$\{([A-Z0-9_]+)\}", REALM.read_text(encoding="utf-8"))) - set(values))
    if missing:
        sys.exit(f"No value in {ENV_FILE.name} for: {', '.join(missing)}")
    text = re.sub(r"\$\{([A-Z0-9_]+)\}", lambda m: values[m.group(1)], REALM.read_text(encoding="utf-8"))
    json.loads(text)
    return text


def put_secret(c: Ctx, name: str, value: str) -> None:
    """Add a version and destroy older ones, so at most one version per secret is active (free tier: 6)."""
    if not c.ok("secrets", "describe", name):
        c.gc("secrets", "create", name, "--replication-policy=automatic")
    c.gc("secrets", "versions", "add", name, "--data-file=-", input=value)
    versions = c.gc("secrets", "versions", "list", name, "--filter=state=enabled", "--format=value(name)").split()
    for v in sorted(versions, key=lambda x: int(x.rsplit("/", 1)[-1]))[:-1]:
        c.gc("secrets", "versions", "destroy", v.rsplit("/", 1)[-1], f"--secret={name}")


def docker(*args: str) -> None:
    print("  $ docker " + " ".join(args))
    if subprocess.run(["docker", *args]).returncode != 0:
        sys.exit("docker failed")


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip() or "manual"


# ---- commands -------------------------------------------------------------------------------

def setup(c: Ctx, billing: str | None, github_repo: str) -> None:
    if not c.ok("projects", "describe", c.project):
        print(f"Creating project {c.project}")
        subprocess.run([GCLOUD, "projects", "create", c.project, "--name=PharmAgentics UAT", "--quiet"], check=True)
    info = c.gc("billing", "projects", "describe", c.project, "--format=value(billingEnabled,billingAccountName)",
                quiet_fail=True).split()
    if billing:
        c.gc("billing", "projects", "link", c.project, f"--billing-account={billing}")
    elif info and info[0].lower() == "true":
        billing = info[1].rsplit("/", 1)[-1]
        print(f"  billing already linked: {billing}")
    else:
        sys.exit(f"{c.project} has no open billing account linked. Link one in the console or pass --billing.")
    c.gc("services", "enable", *APIS)
    pn = c.number

    if not c.ok("artifacts", "repositories", "describe", REPO, f"--location={c.region}"):
        c.gc("artifacts", "repositories", "create", REPO, "--repository-format=docker", f"--location={c.region}")
    policy = HERE / "gcp-cleanup-policy.json"
    c.gc("artifacts", "repositories", "set-cleanup-policies", REPO, f"--location={c.region}", f"--policy={policy}", "--no-dry-run")

    if not c.ok("storage", "buckets", "describe", f"gs://{c.bucket}"):
        c.gc("storage", "buckets", "create", f"gs://{c.bucket}", f"--location={c.region}",
             "--default-storage-class=STANDARD", "--uniform-bucket-level-access", "--public-access-prevention")

    for key, title in (("app", "PharmAgentics app runtime"), ("kc", "PharmAgentics Keycloak runtime"),
                       ("deployer", "GitHub Actions deployer (main only)")):
        if not c.ok("iam", "service-accounts", "describe", c.sa(key)):
            c.gc("iam", "service-accounts", "create", SA[key], f"--display-name={title}")

    env = read_env()
    put_secret(c, SECRETS["session"], env["PHARMAGENTICS_SESSION_SECRET"])
    put_secret(c, SECRETS["client"], env["PHARMAGENTICS_OIDC_CLIENT_SECRET"])
    put_secret(c, SECRETS["realm"], render_realm(env, c.url(APP)))
    for key, secret in (("app", "session"), ("app", "client"), ("kc", "realm")):
        c.gc("secrets", "add-iam-policy-binding", SECRETS[secret], f"--member=serviceAccount:{c.sa(key)}",
             "--role=roles/secretmanager.secretAccessor")
    c.gc("storage", "buckets", "add-iam-policy-binding", f"gs://{c.bucket}",
         f"--member=serviceAccount:{c.sa('app')}", "--role=roles/storage.objectUser")

    # GitHub Actions on main deploys the app: Workload Identity Federation, no stored key (FR-024).
    for role in ("roles/run.developer", "roles/artifactregistry.writer"):
        c.gc("projects", "add-iam-policy-binding", c.project, f"--member=serviceAccount:{c.sa('deployer')}",
             f"--role={role}", "--condition=None")
    c.gc("iam", "service-accounts", "add-iam-policy-binding", c.sa("app"),
         f"--member=serviceAccount:{c.sa('deployer')}", "--role=roles/iam.serviceAccountUser")
    if not c.ok("iam", "workload-identity-pools", "describe", "github", "--location=global"):
        c.gc("iam", "workload-identity-pools", "create", "github", "--location=global", "--display-name=GitHub Actions")
    if not c.ok("iam", "workload-identity-pools", "providers", "describe", "github-oidc",
                "--workload-identity-pool=github", "--location=global"):
        c.gc("iam", "workload-identity-pools", "providers", "create-oidc", "github-oidc", "--location=global",
             "--workload-identity-pool=github", "--issuer-uri=https://token.actions.githubusercontent.com",
             "--attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref",
             f"--attribute-condition=assertion.repository=='{github_repo}' && assertion.ref=='refs/heads/main'")
    c.gc("iam", "service-accounts", "add-iam-policy-binding", c.sa("deployer"), "--role=roles/iam.workloadIdentityUser",
         f"--member=principalSet://iam.googleapis.com/projects/{pn}/locations/global/workloadIdentityPools/github/attribute.repository/{github_repo}")

    budgets = subprocess.run([GCLOUD, "billing", "budgets", "list", f"--billing-account={billing}",
                              "--format=value(displayName)"], capture_output=True, text=True).stdout.split("\n")
    if f"{c.project} UAT" not in budgets:
        print("  $ gcloud billing budgets create ...")
        subprocess.run([GCLOUD, "billing", "budgets", "create", f"--billing-account={billing}",
                        f"--display-name={c.project} UAT", "--budget-amount=1USD", f"--filter-projects=projects/{c.project}",
                        "--threshold-rule=percent=0.01", "--threshold-rule=percent=0.5", "--threshold-rule=percent=1.0",
                        "--quiet"], check=True)

    print("\nSetup done. Next: deploy/gcp.py keycloak, then deploy/gcp.py app.")
    print("For automatic deploys from main, set these GitHub repository variables:")
    for k, v in github_vars(c).items():
        print(f"  gh variable set {k} --body '{v}'")


def github_vars(c: Ctx) -> dict[str, str]:
    return {"GCP_PROJECT": c.project, "GCP_REGION": c.region, "GCP_DEPLOYER_SA": c.sa("deployer"),
            "GCP_WIF_PROVIDER": f"projects/{c.number}/locations/global/workloadIdentityPools/github/providers/github-oidc"}


def keycloak(c: Ctx) -> None:
    image = f"{c.registry}/keycloak:{git_sha()}"
    c.gc("auth", "configure-docker", f"{c.region}-docker.pkg.dev", quiet_fail=True)
    docker("build", "-t", image, str(HERE / "keycloak"))
    docker("push", image)
    put_secret(c, SECRETS["realm"], render_realm(read_env(), c.url(APP)))
    c.gc("run", "deploy", KC, f"--image={image}", f"--region={c.region}", f"--service-account={c.sa('kc')}",
         "--allow-unauthenticated", "--port=8080", "--cpu=1", "--memory=1Gi", "--min-instances=0",
         "--max-instances=1",  # one instance: Keycloak keeps sessions in memory (no database)
         "--cpu-boost", "--timeout=300", "--concurrency=40",
         f"--set-env-vars=KC_HOSTNAME={c.url(KC)}",
         f"--set-secrets=/opt/keycloak/data/import/realm-pharmagentics.json={SECRETS['realm']}:latest")
    print(f"\nKeycloak: {c.url(KC)}  (realm pharmagentics; restart to reload accounts)")


def app(c: Ctx, image: str | None = None) -> None:
    if image is None:
        image = f"{c.registry}/app:{git_sha()}"
        c.gc("auth", "configure-docker", f"{c.region}-docker.pkg.dev", quiet_fail=True)
        docker("build", "--build-arg", f"PHARMAGENTICS_VERSION={git_sha()}", "-t", image, str(ROOT))
        content_check(image)
        docker("push", image)
    c.gc("run", "deploy", APP, f"--image={image}", f"--region={c.region}", f"--service-account={c.sa('app')}",
         "--allow-unauthenticated", "--port=8080", "--cpu=1", "--memory=512Mi", "--min-instances=0",
         "--max-instances=2", "--cpu-boost", "--timeout=120", "--concurrency=40",
         "--set-env-vars=" + ",".join([
             "PHARMAGENTICS_AUTH=oidc", f"PHARMAGENTICS_OIDC_ISSUER={c.url(KC)}/realms/pharmagentics",
             "PHARMAGENTICS_OIDC_CLIENT_ID=pharmagentics-app", f"PHARMAGENTICS_STATE_BUCKET={c.bucket}"]),
         f"--set-secrets=PHARMAGENTICS_SESSION_SECRET={SECRETS['session']}:latest,"
         f"PHARMAGENTICS_OIDC_CLIENT_SECRET={SECRETS['client']}:latest")
    print(f"\nApp: {c.url(APP)}")


def content_check(image: str) -> None:
    """FR-018: no eval package, no ground truth, no .env in the image."""
    script = ("test ! -e /app/eval && test ! -e /app/.env && test ! -e /app/SoT && "
              "! find / -xdev \\( -name 'answer_key*' -o -name '*counterfactual*' -o -name 'heldout_params*' "
              "-o -name '*true_before_feed_artifacts*' \\) 2>/dev/null | grep -q .")
    docker("run", "--rm", "--entrypoint", "sh", image, "-c", script)
    print("  content check passed: no eval/, SoT/, .env or ground-truth files")


def status(c: Ctx) -> None:
    for svc in (APP, KC):
        rev = c.gc("run", "services", "describe", svc, f"--region={c.region}",
                   "--format=value(status.latestReadyRevisionName)", check=False, quiet_fail=True)
        print(f"{svc}: {c.url(svc)}  revision {rev or '(not deployed)'}")
    for k, v in github_vars(c).items():
        print(f"  {k}={v}")


def rollback(c: Ctx, service: str) -> None:
    svc = APP if service == "app" else KC
    revs = c.gc("run", "revisions", "list", f"--service={svc}", f"--region={c.region}",
                "--sort-by=~metadata.creationTimestamp", "--format=value(metadata.name)").split()
    if len(revs) < 2:
        sys.exit("No earlier revision to roll back to.")
    c.gc("run", "services", "update-traffic", svc, f"--region={c.region}", f"--to-revisions={revs[1]}=100")
    print(f"{svc}: all traffic on {revs[1]} (was {revs[0]}). Undo with: update-traffic --to-latest")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["setup", "keycloak", "app", "status", "rollback", "github-vars"])
    p.add_argument("--project", required=True)
    p.add_argument("--account", help="gcloud account to use (e.g. mwc2150@columbia.edu); the active account is not changed")
    p.add_argument("--region", default="us-central1")
    p.add_argument("--billing", help="billing account ID (setup only)")
    p.add_argument("--github-repo", default="mwc2150/PharmAgentics")
    p.add_argument("--image", help="app: deploy this pushed image instead of building")
    p.add_argument("--service", choices=["app", "keycloak"], default="app")
    a = p.parse_args()
    if a.account:
        # Applies to every gcloud call and to Docker's gcloud credential helper, for this process only.
        os.environ["CLOUDSDK_CORE_ACCOUNT"] = a.account
    c = Ctx(a.project, a.region)
    if a.command == "setup":
        setup(c, a.billing, a.github_repo)
    elif a.command == "keycloak":
        keycloak(c)
    elif a.command == "app":
        app(c, a.image)
    elif a.command == "status":
        status(c)
    elif a.command == "rollback":
        rollback(c, a.service)
    else:
        for k, v in github_vars(c).items():
            print(f"{k}={v}")


if __name__ == "__main__":
    main()
