#!/usr/bin/env bash
# Starts a throwaway DocuWaves for the end-to-end tests (playwright.config.ts).
#
# Everything lives in e2e/.run/, wiped on every start: an empty content
# repository (DocuWaves creates it), a fresh SQLite index and session secret.
# The frontend is whatever `npm run build` last wrote to dist/, served by the
# backend through backend/static, exactly as in the container.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
run="$here/.run"
rm -rf "$run"
mkdir -p "$run"
cd "$here/../../backend"
export SQLITE_PATH="$run/index.db"
export CONTENT_REPO_PATH="$run/content-repo"
export SESSION_SECRET_PATH="$run/session_secret"
export SESSION_COOKIE_SECURE=false
export UPDATE_CHECK=off
exec "${E2E_PYTHON:-python3}" -m uvicorn app.main:app --host 127.0.0.1 --port "${E2E_PORT:-8790}"
