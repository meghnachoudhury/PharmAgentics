"""Property-based UI exploration with Bombadil (Antithesis): it clicks, types and navigates through the app as every
dev role and checks tests/ui/bombadil.spec.ts after each step.

  uv run python tests/ui/run_bombadil.py [--time-limit 5m] [--image TAG]

Bombadil has no Windows build, so it runs in WSL Ubuntu with Google Chrome (once: `wsl -d Ubuntu -u root -- bash
tests/ui/setup_wsl.sh`). The app runs in Docker with dev sign-in and no model keys, published only on the WSL
network address, and a relay inside WSL serves it on 127.0.0.1: Chrome refuses Bombadil's instrumented scripts
and requests from private-network addresses, but not from loopback. Without --image the image is built from the
working tree. Exit code: 0 clean, 2 property violations, 1 other errors (Bombadil's codes).
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import urllib.request
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISTRO, APP, PORT = "Ubuntu", "pa-bombadil-app", 18090


def wsl(command: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(["wsl.exe", "-d", DISTRO, "-u", "root", "--cd", "/tmp", "--", "bash", "-c", command],
                       capture_output=True, check=False)
    out = r.stdout.decode("utf-8", "replace").replace("\0", "")
    if not capture:
        sys.stdout.write(out)
        sys.stderr.write(r.stderr.decode("utf-8", "replace").replace("\0", ""))
    if check and r.returncode != 0:
        sys.exit(f"WSL command failed ({r.returncode}): {command[:80]}")
    return subprocess.CompletedProcess(r.args, r.returncode, out, "")


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check, text=True, capture_output=True)


def seed(base: str) -> str:
    """Sign in as the analyst, generate one scripted brief and approve it, so every role has a brief to open."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.open(urllib.request.Request(f"{base}/auth/dev-login", data=b"username=dev-analyst", method="POST"))

    def call(path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(f"{base}{path}", data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
        with opener.open(req, timeout=120) as r:
            return json.load(r)

    week = call("/api/briefing/context")["latest_week"]
    brief = call("/api/briefing/query", {"week_start": week})
    call(f"/api/briefing/{brief['brief_id']}/review", {"decision": "approved"})
    return brief["brief_id"]


def to_wsl(path: Path) -> str:
    p = path.resolve().as_posix()
    return f"/mnt/{p[0].lower()}{p[2:]}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--time-limit", default="5m")
    ap.add_argument("--image", help="an existing app image; default: build pharmagentics:bombadil from the working tree")
    ap.add_argument("--seed", action="store_true", help="approve one scripted brief first, so brief screens are reachable")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if "bombadil" not in wsl("command -v bombadil google-chrome socat || true", capture=True).stdout:
        sys.exit("Run the one-time setup first: wsl -d Ubuntu -u root -- bash tests/ui/setup_wsl.sh")
    image = a.image or "pharmagentics:bombadil"
    if not a.image:
        subprocess.run(["docker", "build", "-q", "-t", image, str(ROOT)], check=True)
    gateway = wsl("ip route show default", capture=True).stdout.split()[2]
    out = ROOT / "local" / "bombadil" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)

    docker("rm", "-f", APP, check=False)
    docker("run", "-d", "--rm", "--name", APP, "-p", f"{gateway}:{PORT}:8080", "-e", "PHARMAGENTICS_AUTH=dev", image)
    try:
        wsl(f"pkill -f '[s]ocat TCP-LISTEN:{PORT}' || true", capture=True)
        wsl(f"setsid -f socat TCP-LISTEN:{PORT},fork,reuseaddr,bind=127.0.0.1 TCP:{gateway}:{PORT} </dev/null >/dev/null 2>&1",
            capture=True)
        for _ in range(45):
            if '"database_ready":true' in wsl(f"curl -s -m 3 http://127.0.0.1:{PORT}/api/health || true", capture=True).stdout:
                break
            time.sleep(2)
        else:
            sys.exit(f"The app did not answer; see `docker logs {APP}`.")
        if a.seed:
            print(f"Seeded an approved brief: {seed(f'http://{gateway}:{PORT}')}")
        run = wsl(f"bombadil browser test --headless --no-sandbox --time-limit {a.time_limit} "
                  f"--output-path {to_wsl(out)}/trace http://127.0.0.1:{PORT} {to_wsl(ROOT / 'tests/ui/bombadil.spec.ts')}",
                  check=False)
        wsl(f"bombadil trace --screenshots {to_wsl(out)}/screens {to_wsl(out)}/trace > {to_wsl(out)}/trace.txt 2>&1 || true",
            capture=True)
        (out / "app.log").write_text(docker("logs", APP, check=False).stdout + docker("logs", APP, check=False).stderr,
                                     encoding="utf-8")
    finally:
        wsl(f"pkill -f '[s]ocat TCP-LISTEN:{PORT}' || true", check=False, capture=True)
        docker("rm", "-f", APP, check=False)
    print(f"\nTrace, screenshots and app log: {out}\nBombadil exit code: {run.returncode} (0 clean, 2 violations, 1 error)")
    return run.returncode


if __name__ == "__main__":
    sys.exit(main())
