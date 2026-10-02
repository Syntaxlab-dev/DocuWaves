#!/bin/sh
# DocuWaves installer.
#
#   curl -fsSL https://get.docuwaves.app | sudo sh
#   curl -fsSL https://get.docuwaves.app | sudo sh -s -- --domain docs.example.com
#
# Sets up one DocuWaves instance on this server, in /opt/docuwaves:
# Docker (if it is missing, after asking), the DocuWaves container, Caddy in
# front of it for HTTPS, a daily backup, and the `docuwaves` command that
# runs it all afterwards. Re-running it on a server that already has an
# installation changes nothing -- that is what `docuwaves update` is for.
#
# Plain POSIX sh, so it runs as `| sh` on any distribution; read it before
# you run it -- it is meant to be read.
#
# Options (all optional; without them it asks):
#   --domain NAME        serve on NAME with an HTTPS certificate from Let's Encrypt
#   --no-domain          plain HTTP on port 80 for now (`docuwaves domain` later)
#   --no-proxy           no Caddy: DocuWaves on 127.0.0.1:8091, for your own proxy
#   --listen ADDR:PORT   with --no-proxy, where to listen instead (e.g. 0.0.0.0:8091)
#   --repo-url URL       a Git remote for the content (https:// or git@...)
#   --repo-ssh-key FILE  the private key for a git@/ssh:// remote
#                        (for https://, the token is asked for, or read from
#                        the DOCUWAVES_REPO_TOKEN environment variable)
#   --channel NAME       stable (default), latest, or a version like 1.2
#   --dir PATH           install somewhere other than /opt/docuwaves
#   --no-backup-timer    no daily backup
#   --yes                ask nothing; take the defaults for anything not given
#   --image REF          a different image altogether (for testing)
set -eu

DIR=/opt/docuwaves
CHANNEL=stable
IMAGE=""
DOMAIN=""
DOMAIN_SET=0
PROXY=1
LISTEN=127.0.0.1:8091
REPO_URL=""
REPO_KEY_FILE=""
REPO_TOKEN="${DOCUWAVES_REPO_TOKEN:-}"
BACKUP_TIMER=1
YES=0
REGISTRY_IMAGE=ghcr.io/syntaxlab-dev/docuwaves
CLI_IN_IMAGE=/usr/share/docuwaves/docuwaves

if [ -t 1 ]; then
  BOLD=$(printf '\033[1m') DIM=$(printf '\033[2m') RED=$(printf '\033[31m')
  GREEN=$(printf '\033[32m') YELLOW=$(printf '\033[33m') RESET=$(printf '\033[0m')
else
  BOLD="" DIM="" RED="" GREEN="" YELLOW="" RESET=""
fi

say() { printf '%s\n' "$*"; }
step() { printf '\n%s==>%s %s\n' "$BOLD" "$RESET" "$*"; }
ok() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s!%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
die() {
  printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2
  exit 1
}

# Questions go to the terminal, not to stdin: under `curl ... | sh`, stdin is
# this script.
can_ask() { [ "$YES" = 0 ] && [ -r /dev/tty ] && [ -w /dev/tty ]; }

ask() { # ask VAR "Question" "default"
  printf '%s%s%s %s[%s]%s ' "$BOLD" "$2" "$RESET" "$DIM" "$3" "$RESET" >/dev/tty
  IFS= read -r _answer </dev/tty || _answer=""
  [ -n "$_answer" ] || _answer=$3
  eval "$1=\$_answer"
}

ask_secret() { # ask_secret VAR "Question"
  printf '%s%s%s ' "$BOLD" "$2" "$RESET" >/dev/tty
  stty -echo </dev/tty 2>/dev/null || true
  IFS= read -r _answer </dev/tty || _answer=""
  stty echo </dev/tty 2>/dev/null || true
  printf '\n' >/dev/tty
  eval "$1=\$_answer"
}

confirm() { # confirm "Question" -> 0 for yes
  [ "$YES" = 1 ] && return 0
  can_ask || return 1
  printf '%s%s%s %s[Y/n]%s ' "$BOLD" "$1" "$RESET" "$DIM" "$RESET" >/dev/tty
  IFS= read -r _answer </dev/tty || _answer=""
  case $_answer in [nN]*) return 1 ;; *) return 0 ;; esac
}

need_value() { [ -n "${2:-}" ] || die "$1 needs a value."; }

while [ $# -gt 0 ]; do
  case $1 in
    --domain) need_value "$1" "${2:-}"; DOMAIN=$2; DOMAIN_SET=1; shift ;;
    --no-domain) DOMAIN=""; DOMAIN_SET=1 ;;
    --no-proxy) PROXY=0 ;;
    --listen) need_value "$1" "${2:-}"; LISTEN=$2; shift ;;
    --repo-url) need_value "$1" "${2:-}"; REPO_URL=$2; shift ;;
    --repo-ssh-key) need_value "$1" "${2:-}"; REPO_KEY_FILE=$2; shift ;;
    --channel) need_value "$1" "${2:-}"; CHANNEL=$2; shift ;;
    --dir) need_value "$1" "${2:-}"; DIR=$2; shift ;;
    --image) need_value "$1" "${2:-}"; IMAGE=$2; shift ;;
    --no-backup-timer) BACKUP_TIMER=0 ;;
    --yes | -y) YES=1 ;;
    -h | --help) sed -n '2,/^set -eu/p' "$0" 2>/dev/null | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
  shift
done

case $CHANNEL in
  stable | latest) ;;
  *) printf '%s' "$CHANNEL" | grep -Eq '^[0-9]+\.[0-9]+(\.[0-9]+)?$' ||
    die "--channel is stable, latest, or a version like 1.2 or 1.2.3." ;;
esac
[ -n "$IMAGE" ] || IMAGE="$REGISTRY_IMAGE:$CHANNEL"

say "${BOLD}DocuWaves installer${RESET}"

# ---- this server ----

step "Checking this server"
[ "$(id -u)" = 0 ] || die "Run the installer as root: curl -fsSL https://get.docuwaves.app | sudo sh"

case $(uname -m) in
  x86_64 | amd64) ARCH=amd64 ;;
  aarch64 | arm64) ARCH=arm64 ;;
  *) die "DocuWaves images exist for amd64 and arm64; this server is $(uname -m)." ;;
esac

OS_ID=unknown OS_LIKE="" OS_VERSION="" OS_NAME="this system"
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID=${ID:-unknown} OS_LIKE=${ID_LIKE:-} OS_VERSION=${VERSION_ID:-} OS_NAME=${PRETTY_NAME:-$OS_ID}
fi
FAMILY=other
case "$OS_ID" in
  debian | ubuntu) FAMILY=debian ;;
  rocky | almalinux | rhel | centos) FAMILY=rhel ;;
  fedora) FAMILY=fedora ;;
esac
TESTED=0
case "$OS_ID:$OS_VERSION" in
  debian:12* | debian:13* | ubuntu:22.04 | ubuntu:24.04 | rocky:9* | almalinux:9*) TESTED=1 ;;
esac
if [ "$TESTED" = 1 ]; then
  ok "$OS_NAME, $ARCH"
else
  warn "$OS_NAME ($ARCH) is not one of the tested systems (Debian 12/13, Ubuntu 22.04/24.04, Rocky/Alma 9). It will most likely work if Docker does."
fi

if [ -e "$DIR/compose.yml" ]; then
  die "DocuWaves is already installed in $DIR. To update it: docuwaves update   (To start over: docuwaves uninstall --purge)"
fi

# ---- Docker ----

install_docker() {
  case $FAMILY in
    debian)
      apt-get update -qq
      apt-get install -y -qq ca-certificates curl >/dev/null
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL "https://download.docker.com/linux/$OS_ID/gpg" -o /etc/apt/keyrings/docker.asc
      chmod a+r /etc/apt/keyrings/docker.asc
      printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
        "$(dpkg --print-architecture)" "$OS_ID" "${VERSION_CODENAME:-}" >/etc/apt/sources.list.d/docker.list
      apt-get update -qq
      apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
      ;;
    rhel | fedora)
      repo=rhel
      [ "$FAMILY" = fedora ] && repo=fedora
      dnf -y -q install dnf-plugins-core >/dev/null
      # dnf 4 and dnf 5 spell adding a repository differently.
      dnf config-manager --add-repo "https://download.docker.com/linux/$repo/docker-ce.repo" >/dev/null 2>&1 ||
        dnf config-manager addrepo --from-repofile="https://download.docker.com/linux/$repo/docker-ce.repo" >/dev/null
      dnf -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
      ;;
    *)
      die "Install Docker with the Compose plugin for $OS_NAME (https://docs.docker.com/engine/install/), then run this again."
      ;;
  esac
  systemctl enable --now docker >/dev/null 2>&1 || true
}

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '(version unknown)'), $(docker compose version --short 2>/dev/null | sed 's/^/Compose /')"
else
  if command -v docker >/dev/null 2>&1; then
    say "Docker is installed, but without the Compose plugin (\`docker compose\`)."
  else
    say "Docker is not installed."
  fi
  [ "$FAMILY" != other ] || die "Install Docker with the Compose plugin (https://docs.docker.com/engine/install/), then run this again."
  confirm "Install Docker from Docker's official repository now?" ||
    die "DocuWaves needs Docker. Install it (https://docs.docker.com/engine/install/) and run this again."
  install_docker
  docker compose version >/dev/null 2>&1 || die "Docker was installed, but \`docker compose\` does not work. Check: docker compose version"
  ok "Docker installed"
fi
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start it (systemctl start docker) and run this again."

port_in_use() {
  command -v ss >/dev/null 2>&1 || return 1
  [ -n "$(ss -Hltn "sport = :$1" 2>/dev/null)" ]
}

if [ "$PROXY" = 1 ]; then
  busy=""
  for port in 80 443; do port_in_use "$port" && busy="$busy $port"; done
  if [ -n "$busy" ]; then
    die "Port(s)$busy are already taken -- another web server runs here. Either stop it, or install behind it with --no-proxy (DocuWaves then listens on 127.0.0.1:8091 for that server to forward to)."
  fi
else
  port_in_use "${LISTEN##*:}" && die "Port ${LISTEN##*:} is already taken; pick another with --listen 127.0.0.1:PORT."
fi

# ---- questions ----

if [ "$PROXY" = 1 ] && [ "$DOMAIN_SET" = 0 ] && can_ask; then
  step "Where should the documentation be reachable?"
  say "With a domain, DocuWaves gets an HTTPS certificate from Let's Encrypt automatically."
  say "The domain must already point at this server, and ports 80 and 443 must be open."
  say "Leave it empty to start on plain HTTP and add a domain later (docuwaves domain <name>)."
  ask DOMAIN "Domain (e.g. docs.example.com):" ""
fi
DOMAIN=$(printf '%s' "$DOMAIN" | sed 's#^https\{0,1\}://##; s#/.*$##')
if [ -n "$DOMAIN" ]; then
  printf '%s' "$DOMAIN" | grep -Eq '^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' || die "$DOMAIN does not look like a domain name."
  resolved=$(getent ahosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ' || true)
  if [ -z "$resolved" ]; then
    warn "$DOMAIN does not resolve yet. The certificate is fetched once it points at this server -- nothing else to do then."
  else
    say "${DIM}$DOMAIN points at: $resolved${RESET}"
  fi
fi

if [ -z "$REPO_URL" ] && can_ask; then
  step "Where should the content be pushed? (optional)"
  say "DocuWaves keeps your documentation in a Git repository on this server. A remote"
  say "(GitHub, GitLab, Forgejo, ...) gives it a second copy. Empty = local only; you can add one later."
  ask REPO_URL "Git remote URL:" ""
fi
if [ -n "$REPO_URL" ]; then
  case $REPO_URL in
    https://*)
      if [ -z "$REPO_TOKEN" ] && can_ask; then
        say "A token with write access to that one repository (on GitHub: a fine-grained token with Contents: Read and write)."
        ask_secret REPO_TOKEN "Token (hidden):"
      fi
      [ -n "$REPO_TOKEN" ] || die "An https:// remote needs a token: set DOCUWAVES_REPO_TOKEN, or run interactively."
      ;;
    git@* | ssh://*)
      if [ -z "$REPO_KEY_FILE" ] && can_ask; then
        say "The PRIVATE key of a deploy key with write access, as a file on this server."
        ask REPO_KEY_FILE "Path to the private key file:" ""
      fi
      [ -n "$REPO_KEY_FILE" ] && [ -r "$REPO_KEY_FILE" ] || die "A git@/ssh:// remote needs --repo-ssh-key FILE (a readable private key)."
      grep -q 'PRIVATE KEY' "$REPO_KEY_FILE" || die "$REPO_KEY_FILE does not look like a private key."
      ;;
    *) die "The remote URL must start with https://, git@ or ssh://." ;;
  esac
fi

# ---- the image ----

step "Getting DocuWaves ($IMAGE)"
if docker image inspect "$IMAGE" >/dev/null 2>&1 && [ "${DOCUWAVES_SKIP_PULL:-0}" = 1 ]; then
  ok "Using the local image"
else
  docker pull -q "$IMAGE" >/dev/null || die "Could not download $IMAGE. Is the server online? Does the channel exist?"
  ok "Downloaded"
fi

# ---- files ----

step "Writing $DIR"
umask 077
mkdir -p "$DIR/data" "$DIR/backups"
chmod 755 "$DIR"

# 16 random bytes, hex: long enough that guessing is pointless, short
# enough to type.
SETUP_TOKEN=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')

if [ "$PROXY" = 1 ]; then
  SITE=${DOMAIN:-:80}
  BASE_URL=""
  [ -n "$DOMAIN" ] && BASE_URL="https://$DOMAIN"
else
  SITE=""
  BASE_URL=""
fi

{
  say "# DocuWaves settings, written by the installer on $(date -u +%Y-%m-%d)."
  say "# Every setting: https://docs.docuwaves.app/p/docuwaves/pages/environment-variables"
  say "# After a change: docker compose -f $DIR/compose.yml up -d   (a restart is not enough)"
  say ""
  say "# The image updates follow -- change it with: docuwaves channel"
  say "DOCUWAVES_IMAGE=$IMAGE"
  if [ "$PROXY" = 1 ]; then
    say "# What Caddy serves: a domain (with HTTPS), or :80 -- change it with: docuwaves domain"
    say "DOCUWAVES_SITE=$SITE"
  else
    say "# Where DocuWaves listens, for your own reverse proxy to forward to."
    say "DOCUWAVES_LISTEN=$LISTEN"
  fi
  say "PUBLIC_BASE_URL=$BASE_URL"
  say ""
  say "# The code the first-run setup asks for. Not needed once the first account exists."
  say "SETUP_TOKEN=$SETUP_TOKEN"
  if [ -n "$REPO_URL" ]; then
    say ""
    say "CONTENT_REPO_URL=$REPO_URL"
    if [ -n "$REPO_TOKEN" ]; then
      say "CONTENT_REPO_TOKEN=$REPO_TOKEN"
    else
      printf 'CONTENT_REPO_SSH_KEY="'
      tr -d '\r' <"$REPO_KEY_FILE"
      say '"'
    fi
  fi
} >"$DIR/.env"
chmod 600 "$DIR/.env"
umask 022

if [ "$PROXY" = 1 ]; then
  cat >"$DIR/compose.yml" <<'EOF'
# DocuWaves, as the installer set it up. Settings are in .env next to this
# file; the `docuwaves` command manages both.
name: docuwaves

services:
  docuwaves:
    image: ${DOCUWAVES_IMAGE}
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/data
    # No ports: only Caddy, on the network Compose makes for the two of
    # them, talks to it.

  caddy:
    image: caddy:2
    restart: unless-stopped
    depends_on:
      - docuwaves
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    environment:
      DOCUWAVES_SITE: ${DOCUWAVES_SITE}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./caddy/data:/data
      - ./caddy/config:/config
EOF
  cat >"$DIR/Caddyfile" <<'EOF'
# HTTPS for DocuWaves. DOCUWAVES_SITE (in .env) is either a domain -- Caddy
# then fetches and renews its Let's Encrypt certificate by itself and sends
# plain HTTP over to HTTPS -- or :80, for plain HTTP on any address.
{$DOCUWAVES_SITE} {
	encode zstd gzip
	reverse_proxy docuwaves:8000
}
EOF
else
  cat >"$DIR/compose.yml" <<'EOF'
# DocuWaves, as the installer set it up (without a proxy of its own -- put
# yours in front of DOCUWAVES_LISTEN). Settings are in .env next to this
# file; the `docuwaves` command manages both.
name: docuwaves

services:
  docuwaves:
    image: ${DOCUWAVES_IMAGE}
    restart: unless-stopped
    env_file: .env
    ports:
      - "${DOCUWAVES_LISTEN}:8000"
    volumes:
      - ./data:/data
EOF
fi
ok "compose.yml, .env$( [ "$PROXY" = 1 ] && printf ', Caddyfile')"

# ---- the docuwaves command ----

tmp=$(mktemp)
if docker run --rm --entrypoint cat "$IMAGE" "$CLI_IN_IMAGE" >"$tmp" 2>/dev/null && [ -s "$tmp" ]; then
  install -m 755 "$tmp" /usr/local/bin/docuwaves
elif [ -f "$(dirname "$0")/docuwaves" ]; then
  # Run from a checkout of the repository, with an image from before the
  # command was part of it.
  install -m 755 "$(dirname "$0")/docuwaves" /usr/local/bin/docuwaves
else
  rm -f "$tmp"
  die "$IMAGE does not contain the docuwaves command; it is older than this installer. Use --channel latest."
fi
rm -f "$tmp"
if [ "$DIR" != /opt/docuwaves ]; then
  printf 'DOCUWAVES_DIR=%s\n' "$DIR" >/etc/default/docuwaves
fi
ok "/usr/local/bin/docuwaves"

# ---- daily backup ----

if [ "$BACKUP_TIMER" = 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  cat >/etc/systemd/system/docuwaves-backup.service <<'EOF'
[Unit]
Description=DocuWaves backup
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/docuwaves backup --quiet
EOF
  cat >/etc/systemd/system/docuwaves-backup.timer <<'EOF'
[Unit]
Description=Daily DocuWaves backup

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now docuwaves-backup.timer >/dev/null 2>&1
  ok "Daily backup at 03:30 (7 kept, in $DIR/backups)"
fi

# ---- start ----

step "Starting"
docker compose --project-directory "$DIR" -f "$DIR/compose.yml" up -d --quiet-pull 2>&1 | grep -v -e '^ *$' -e 'Pulling' -e 'Pulled' || true
if docuwaves wait 180; then
  ok "DocuWaves is running"
else
  die "DocuWaves did not come up healthy. See: docuwaves logs"
fi

if [ "$PROXY" = 1 ]; then
  if [ -n "$DOMAIN" ]; then
    URL="https://$DOMAIN"
  else
    URL="http://$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
else
  URL="http://$LISTEN"
fi

# A firewall that keeps the ports closed looks exactly like a broken install.
if [ "$PROXY" = 1 ]; then
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    warn "ufw is active. If the site does not open: ufw allow 80/tcp && ufw allow 443/tcp"
  elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    warn "firewalld is active. If the site does not open: firewall-cmd --permanent --add-service=http --add-service=https && firewall-cmd --reload"
  fi
fi

cat <<EOF

${GREEN}${BOLD}DocuWaves is installed.${RESET}

  Open         ${BOLD}$URL/admin${RESET}
  Setup code   ${BOLD}$SETUP_TOKEN${RESET}
               ${DIM}(the first-run screen asks for it; it is also in $DIR/.env)${RESET}

  Files        $DIR
  Manage       docuwaves status | update | backup | logs | help
  Docs         https://docs.docuwaves.app/p/docuwaves/pages/installing-with-the-installer
EOF
if [ -n "$DOMAIN" ]; then
  say ""
  say "${DIM}The HTTPS certificate is fetched on the first visit; that can take a few seconds.${RESET}"
elif [ "$PROXY" = 1 ]; then
  say ""
  say "${YELLOW}Plain HTTP for now.${RESET} Passwords travel unencrypted until you add a domain: docuwaves domain docs.example.com"
fi
