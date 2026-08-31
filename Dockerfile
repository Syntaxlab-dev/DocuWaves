FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# git: the content repo (Markdown+YAML files, the actual source of truth for
# everything under /admin) is a real clone managed by GitPython, which shells
# out to the system `git` binary -- it isn't vendored, so it has to be here.
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend-build /app/frontend/dist ./static

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

# --proxy-headers: trust X-Forwarded-Proto/X-Forwarded-For from upstream so
# request.base_url reflects the real public https:// URL a reverse proxy
# sees, not the plain-http one this container gets internally -- matters
# for the OIDC SSO redirect_uri (a strict provider-side match rejects a
# wrong scheme outright). Baked in from the start here, unlike CachePanel
# where this was found and fixed after the fact.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
