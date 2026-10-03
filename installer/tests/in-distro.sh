#!/bin/sh
# Run by .github/workflows/installer.yml inside a privileged container of
# each tested distribution: the installer, on a system that has never seen
# Docker, the way a fresh server would run it.
#
# There is no systemd in a container, so the first run installs Docker from
# Docker's repository and then stops ("installed but not running"). The
# Docker daemon is then started by hand, as Docker-in-Docker does it, and
# the second run installs DocuWaves -- from the image CI just built.
set -eu

say() { printf '\n==> %s\n' "$*"; }

say "Prerequisites a container image lacks and a server has"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq curl ca-certificates iproute2 procps >/dev/null
else
  dnf -y -q install iproute procps-ng findutils >/dev/null
fi

say "First run: Docker gets installed"
if sh /src/installer/install.sh --yes --no-domain >/tmp/first.log 2>&1; then
  cat /tmp/first.log
  echo "The first run should have stopped at a Docker that is not running." >&2
  exit 1
fi
cat /tmp/first.log
grep -q "Docker installed" /tmp/first.log
grep -q "not running" /tmp/first.log

say "Starting the Docker daemon by hand"
# cgroup v2: move this container's processes out of the root cgroup so the
# daemon may delegate controllers to its own containers (what moby's
# hack/dind does).
if [ -f /sys/fs/cgroup/cgroup.controllers ]; then
  mkdir -p /sys/fs/cgroup/init
  xargs -rn1 </sys/fs/cgroup/cgroup.procs >/sys/fs/cgroup/init/cgroup.procs 2>/dev/null || true
  sed -e 's/ / +/g' -e 's/^/+/' </sys/fs/cgroup/cgroup.controllers >/sys/fs/cgroup/cgroup.subtree_control
fi
dockerd --storage-driver=vfs >/tmp/dockerd.log 2>&1 &
i=0
until docker info >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    cat /tmp/dockerd.log
    exit 1
  fi
  sleep 1
done
docker load -q -i /image/docuwaves.tar

say "Second run: DocuWaves gets installed"
DOCUWAVES_SKIP_PULL=1 sh /src/installer/install.sh --yes --no-domain --image docuwaves:ci

say "Checking it"
curl -fsS http://localhost/health
echo
curl -fsS http://localhost/api/auth/status | grep -q '"setup_token_required":true'
docuwaves status
docuwaves backup
test "$(stat -c %a /opt/docuwaves/.env)" = 600
echo "OK"
