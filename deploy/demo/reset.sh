#!/bin/sh
# Throws the demo's data away and starts it fresh: the demo account and the
# seed docs, nothing a visitor wrote. Run from this folder (the timer does).
set -eu
cd "$(dirname "$0")"
docker compose pull --quiet
docker compose down --volumes
docker compose up -d
# Wait until the app answers, then fill it.
for _ in $(seq 1 60); do
  if docker compose exec -T docuwaves python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" 2>/dev/null; then
    break
  fi
  sleep 2
done
docker compose exec -T docuwaves python -m app.cli demo-seed /seed --name "${DEMO_NAME:-DocuWaves}"
