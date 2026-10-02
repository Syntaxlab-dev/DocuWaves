import os
import re
from dataclasses import dataclass


def _base_url(raw: str) -> str:
    """PUBLIC_BASE_URL, normalized -- scheme and host, no trailing slash, and
    "" for anything that isn't an absolute http(s) URL (an operator who put a
    bare hostname there gets the auto-detected address rather than a canonical
    tag pointing at `docs.example.com/p/x`, which no crawler can fetch)."""
    value = raw.strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return ""


def _list(raw: str) -> list[str]:
    """Comma- or whitespace-separated values, blanks dropped."""
    return [part for part in re.split(r"[\s,]+", raw.strip()) if part]


def _cookie_secure(explicit: str, public_base_url: str) -> bool:
    """SESSION_COOKIE_SECURE when it is set, otherwise whether the public
    address is https -- see the setting below."""
    if explicit.strip():
        return explicit.strip().lower() in ("1", "true", "yes", "on")
    return _base_url(public_base_url).startswith("https://")


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

    # Content repo -- the Markdown+YAML files under CONTENT_REPO_PATH are the
    # single source of truth for all content (see services/content_files.py
    # for the on-disk convention); the database above is only ever a
    # rebuildable search/browse index over it.
    #
    # Blank CONTENT_REPO_URL does NOT mean "feature off" (unlike OIDC above):
    # the repository is always there, initialised locally inside the data
    # volume, and every write commits into it with a full history. This
    # setting adds a REMOTE to that repository -- somewhere to push, and
    # somewhere a community can send pull requests from. It can be filled in
    # later without losing anything: the local history is pushed to a new
    # empty remote on the next start (see git_content_repo._reconcile_remote).
    content_repo_url: str = os.environ.get("CONTENT_REPO_URL", "")
    content_repo_branch: str = os.environ.get("CONTENT_REPO_BRANCH", "main")
    # Exactly one of these two is expected, matching the URL's own scheme
    # (https:// -> token, git@/ssh:// -> key) -- see
    # git_content_repo.py's _authenticated_url()/_env().
    content_repo_token: str = os.environ.get("CONTENT_REPO_TOKEN", "")
    content_repo_ssh_key: str = os.environ.get("CONTENT_REPO_SSH_KEY", "")
    # The repository itself, under the same /data volume every other file
    # this app writes already lives on -- survives container restarts, and
    # is created (cloned, or initialised) once per install rather than on
    # every startup. On a local-only instance this directory IS the content:
    # back up the volume and you have backed up the docs.
    content_repo_path: str = os.environ.get("CONTENT_REPO_PATH", "/data/content-repo")
    content_repo_sync_interval_seconds: int = int(os.environ.get("CONTENT_REPO_SYNC_INTERVAL_SECONDS", "300"))

    # The address readers actually use, e.g. https://docs.example.com. Only
    # needed to OVERRIDE what the app works out for itself: every absolute
    # URL it publishes (canonical tags, Open Graph, sitemap.xml, robots.txt)
    # is otherwise built from X-Forwarded-Proto/X-Forwarded-Host and the Host
    # header, which is right for every ordinary reverse proxy -- see
    # services/seo.py's public_base_url(). Set it when the proxy doesn't
    # forward those, or when the site is reachable at several addresses and
    # exactly one of them is the canonical one. Blank = auto-detect, the same
    # "blank = default" contract as everything above.
    public_base_url: str = _base_url(os.environ.get("PUBLIC_BASE_URL", ""))

    # The documentation chat (services/doc_chat.py). Off unless ALL THREE are
    # set -- an instance that leaves them blank never makes an outbound
    # request, which is the default and is the point: self-hosted
    # documentation should not have to mean a cloud account.
    #
    # The endpoint is OpenAI-compatible, i.e. POST {base}/chat/completions --
    # which a local Ollama (http://host:11434/v1), a llama.cpp server, OpenAI
    # and most hosted providers all speak.
    #
    # The key is here rather than in the admin UI because it is a CREDENTIAL,
    # and every setting a person edits in that UI is written to _site.yml --
    # a file in a repository built to be cloned and read in pull requests.
    # The same reasoning keeps API tokens out of the content repo. Once the
    # key has to be an env var the other two belong beside it, rather than
    # split across two places an operator has to remember.
    chat_api_base: str = os.environ.get("CHAT_API_BASE", "").strip().rstrip("/")
    chat_model: str = os.environ.get("CHAT_MODEL", "").strip()
    chat_api_key: str = os.environ.get("CHAT_API_KEY", "").strip()
    # How many questions may wait on the model at once. Each one holds a
    # worker thread for up to the chat timeout; without a ceiling a burst of
    # slow answers takes every thread, and the whole instance -- health
    # check included -- stops answering until they come back.
    chat_max_concurrent: int = max(1, int(os.environ.get("CHAT_MAX_CONCURRENT", "4")))

    # A one-time code the first-run setup asks for (routers/auth.py). The
    # installer generates one and prints it, so that between `docker compose
    # up` and the admin's first visit nobody else who finds the address can
    # claim the instance. Blank = no code, the setup screen as it always was.
    # Meaningless once an admin account exists; it can be removed then.
    setup_token: str = os.environ.get("SETUP_TOKEN", "").strip()

    # The gaps radar (services/search_gaps.py): searches that found nothing,
    # tallied for the admin's "Insights". On unless switched off.
    search_gaps_enabled: bool = os.environ.get("SEARCH_GAPS", "on").strip().lower() not in ("off", "0", "false", "no")

    # Which header carries the reader's real address, when there is more
    # than one proxy in front of DocuWaves (e.g. CF-Connecting-IP behind
    # Cloudflare). Blank = the rightmost X-Forwarded-For entry, which is
    # right behind a single ordinary reverse proxy. See
    # services/client_address.py for why it is never the leftmost one.
    client_ip_header: str = os.environ.get("CLIENT_IP_HEADER", "").strip().lower()

    # Send the session cookie over HTTPS only. Blank = on when PUBLIC_BASE_URL
    # is an https:// address, off otherwise (plain HTTP on a LAN, local
    # development). Set it to true behind any HTTPS reverse proxy that does
    # not set PUBLIC_BASE_URL, so the cookie is never sent over plain HTTP --
    # not even on the one request before the proxy redirects to https.
    # Webhooks (services/webhooks.py): where to announce documentation
    # changes -- Discord and Slack webhook URLs are recognised and get their
    # own message format, anything else receives JSON. Env vars, not the
    # admin UI, because a webhook URL is itself a credential. Blank = off.
    webhook_urls: tuple[str, ...] = tuple(
        url for url in _list(os.environ.get("WEBHOOK_URLS", "")) if url.startswith(("https://", "http://"))
    )
    # Which changes are announced: published, updated, unpublished. Default
    # "published" alone -- a channel told about every typo fix stops being read.
    webhook_events: frozenset[str] = frozenset(_list(os.environ.get("WEBHOOK_EVENTS", "published").lower()))
    # Signs JSON deliveries (X-DocuWaves-Signature: sha256=<hmac of the body>).
    webhook_secret: str = os.environ.get("WEBHOOK_SECRET", "")

    session_cookie_secure: bool = _cookie_secure(
        os.environ.get("SESSION_COOKIE_SECURE", ""), os.environ.get("PUBLIC_BASE_URL", "")
    )


settings = Settings()
