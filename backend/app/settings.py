import os
from dataclasses import dataclass


@dataclass
class Settings:
    # SQLite is the zero-config default (a single file under /data) --
    # setting DATABASE_URL switches every store over to Postgres instead.
    # Same "blank = default, filled in = opt in" contract CachePanel uses
    # for the same setting.
    database_url: str = os.environ.get("DATABASE_URL", "")
    sqlite_path: str = os.environ.get("SQLITE_PATH", "/data/docuwaves.db")

    # Panel SSO login via a generic OIDC provider -- same env var names as
    # CachePanel's own OIDC feature, deliberately, so the two SyntaxLab
    # tools configure SSO the same way. Blank = feature off.
    oidc_issuer_url: str = os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
    oidc_client_id: str = os.environ.get("OIDC_CLIENT_ID", "")
    oidc_client_secret: str = os.environ.get("OIDC_CLIENT_SECRET", "")
    oidc_provider_name: str = os.environ.get("OIDC_PROVIDER_NAME", "authentik")

    # Content repo -- the Markdown+YAML files under this clone are the
    # single source of truth for all content (see services/content_files.py
    # for the on-disk convention); the database above is only ever a
    # rebuildable search/browse index over it. Blank CONTENT_REPO_URL =
    # feature entirely off, same "blank = off" contract as OIDC above --
    # the admin UI shows a clear "not connected" state instead of a crash.
    content_repo_url: str = os.environ.get("CONTENT_REPO_URL", "")
    content_repo_branch: str = os.environ.get("CONTENT_REPO_BRANCH", "main")
    # Exactly one of these two is expected, matching the URL's own scheme
    # (https:// -> token, git@/ssh:// -> key) -- see
    # git_content_repo.py's _authenticated_url()/_env().
    content_repo_token: str = os.environ.get("CONTENT_REPO_TOKEN", "")
    content_repo_ssh_key: str = os.environ.get("CONTENT_REPO_SSH_KEY", "")
    # Local working clone, under the same /data volume every other file
    # this app writes already lives on -- survives container restarts, only
    # cloned fresh once per install rather than on every startup.
    content_repo_path: str = os.environ.get("CONTENT_REPO_PATH", "/data/content-repo")
    content_repo_sync_interval_seconds: int = int(os.environ.get("CONTENT_REPO_SYNC_INTERVAL_SECONDS", "300"))


settings = Settings()
