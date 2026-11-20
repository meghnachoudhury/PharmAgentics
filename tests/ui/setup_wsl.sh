#!/usr/bin/env bash
# One-time setup inside WSL Ubuntu (run as root): Bombadil, Google Chrome and socat.
#   wsl -d Ubuntu -u root -- bash tests/ui/setup_wsl.sh
set -euo pipefail
VERSION=0.8.0
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates socat >/dev/null
if ! bombadil --version 2>/dev/null | grep -q "$VERSION"; then
  curl -sSL -o /usr/local/bin/bombadil "https://github.com/antithesishq/bombadil/releases/download/v$VERSION/bombadil-x86_64-linux"
  chmod +x /usr/local/bin/bombadil
fi
if ! command -v google-chrome >/dev/null; then
  curl -sSL -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  apt-get install -y -qq /tmp/chrome.deb >/dev/null
fi
bombadil --version
google-chrome --version
