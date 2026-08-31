import os
from dataclasses import dataclass


@dataclass
class Settings:
    # SQLite is the zero-config default (a single file under /data) --
    # setting DATABASE_URL switches every store over to Postgres instead.
    # Same "blank = default, filled in = opt in" contract CachePanel uses
    # for the same setting.
    database_url: str = os.environ.get("DATABASE_URL", "")
    sqlite_path: str = os.environ.get("SQLITE_PATH", "/data/claritydocs.db")

    # Panel SSO login via a generic OIDC provider -- same env var names as
    # CachePanel's own OIDC feature, deliberately, so the two SyntaxLab
    # tools configure SSO the same way. Blank = feature off.
    oidc_issuer_url: str = os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
    oidc_client_id: str = os.environ.get("OIDC_CLIENT_ID", "")
    oidc_client_secret: str = os.environ.get("OIDC_CLIENT_SECRET", "")
    oidc_provider_name: str = os.environ.get("OIDC_PROVIDER_NAME", "authentik")


settings = Settings()
