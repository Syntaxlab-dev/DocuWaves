"""Maintenance commands run inside the container, for the `docuwaves` command
on the host (installer/docuwaves) -- or by hand:

    docker compose exec docuwaves python -m app.cli reset-password <username>
    docker compose exec docuwaves python -m app.cli users
    docker compose exec docuwaves python -m app.cli snapshot-db /data/snapshot.db
    docker run --rm -v "$PWD/docs:/docs:ro" -v "$PWD/out:/out" ghcr.io/syntaxlab-dev/docuwaves \
        python -m app.cli preview-site /docs /out/site.zip

preview-site builds a docs folder into a static website the way DocuWaves
would show it, without an instance: for a pull request's CI (see
docs/bringing-docs-in/previews-for-pull-requests.md).

reset-password reads the new password from standard input, never from the
command line: an argument would sit in the shell history and in `ps` for
everyone on the host to read.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

from app.services import db, session_registry_store, users_store
from app.settings import settings

MIN_PASSWORD_LENGTH = 8


def reset_password(username: str, password: str) -> int:
    user = users_store.get_user(username)
    if user is None:
        names = ", ".join(u["username"] for u in users_store.list_users()) or "(none)"
        print(f"No account called {username!r}. Accounts: {names}", file=sys.stderr)
        return 1
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"The password needs at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1
    users_store.set_password(user["username"], password)
    # Whoever knew the old password may still be signed in with it.
    signed_out = session_registry_store.revoke_for_user(user["username"])
    print(f"Password set for {user['username']}; {signed_out} session(s) signed out.")
    return 0


def list_users() -> int:
    for user in users_store.list_users():
        print(f"{user['username']}\t{user['role']}")
    return 0


def snapshot_db(target: str) -> int:
    """A consistent copy of the SQLite index while the app keeps running --
    copying the file itself mid-write (or without its -wal file) can give a
    database that does not open. Postgres is backed up with pg_dump instead."""
    if db.is_postgres():
        print("This instance uses PostgreSQL (DATABASE_URL); back it up with pg_dump.", file=sys.stderr)
        return 2
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(settings.sqlite_path, timeout=30)
    try:
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    return 0


def preview_site(docs_dir: str, target: str, name: str, summary: str = "") -> int:
    """The docs folder as DocuWaves would publish it, built as a static
    website ZIP (services/static_export.py) -- in a throwaway instance in a
    temporary directory: its own content repository and index, no network,
    no webhooks, no e-mail, nothing kept. The same import as a real sync
    (services/docs_sync.py), so what the preview shows and warns about is
    what the sync will do."""
    import json
    import tempfile

    from app.services import (
        content_sync,
        content_versions,
        docs_sync,
        git_content_repo,
        importer,
        projects_store,
        session_secret,
        static_export,
    )

    source = Path(docs_dir)
    if not source.is_dir():
        print(f"{docs_dir} is not a folder.", file=sys.stderr)
        return 1
    archive = _zip_folder(source)

    with tempfile.TemporaryDirectory(prefix="docuwaves-preview-") as tmp:
        settings.content_repo_path = str(Path(tmp) / "content-repo")
        settings.content_repo_url = ""
        settings.database_url = ""
        settings.sqlite_path = str(Path(tmp) / "index.db")
        settings.webhook_urls = ()
        settings.smtp_host = ""
        session_secret._SECRET_PATH = Path(tmp) / ".session_secret"
        content_versions._cache = {}
        db.init_schema()
        git_content_repo.ensure_clone()
        content_sync.full_sync()
        projects_store.create_project(name, "preview", "", "", "", "preview")
        try:
            result = docs_sync.sync(archive, "preview", "preview")
        except (docs_sync.SyncError, importer.ImportError_) as exc:
            print(f"The docs could not be read: {exc}", file=sys.stderr)
            return 1
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        built = static_export.build(target)

    warnings = result.get("warnings", [])
    print(f"{built['pages']} pages built into {target}.")
    for warning in warnings:
        print(f"warning: {warning['source']}: {warning['message']}")
    if summary:
        Path(summary).write_text(
            json.dumps({"pages": built["pages"], "warnings": warnings}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


def _zip_folder(source: Path) -> bytes:
    import io
    import zipfile

    from app.services import importer

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as packed:
        for file in sorted(source.rglob("*")):
            relative = file.relative_to(source).as_posix()
            if file.is_file() and not file.is_symlink() and importer.wanted_path(relative):
                packed.write(file, relative)
    return buffer.getvalue()


def demo_seed(docs_dir: str, name: str) -> int:
    """Fills an EMPTY demo instance (services/demo.py, deploy/demo/): the
    demo account from DEMO_USERNAME / DEMO_PASSWORD as admin, and the docs
    folder as a project to play with. Does nothing to an instance that
    already has accounts or projects, so it is safe to run on every start."""
    from app.services import content_sync, docs_sync, git_content_repo, projects_store

    if not settings.demo_mode or not settings.demo_password:
        print("demo-seed needs DEMO_MODE=1 and DEMO_PASSWORD.", file=sys.stderr)
        return 1
    db.init_schema()
    git_content_repo.ensure_clone()
    content_sync.full_sync()
    if not users_store.list_users():
        users_store.create_first_admin(settings.demo_username, settings.demo_password)
        print(f"Created the demo account {settings.demo_username}.")
    if projects_store.list_projects():
        print("The instance already has projects; nothing imported.")
        return 0
    source = Path(docs_dir)
    if not source.is_dir():
        print(f"{docs_dir} is not a folder.", file=sys.stderr)
        return 1
    slug = "docs"
    projects_store.create_project(name, slug, "📘", "", "", settings.demo_username)
    result = docs_sync.sync(_zip_folder(source), slug, settings.demo_username, ref="demo")
    print(f"Imported {name}: {len(result['added'])} pages.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-password", help="set an account's password, read from standard input")
    reset.add_argument("username")
    commands.add_parser("users", help="list the accounts and their roles")
    snapshot = commands.add_parser("snapshot-db", help="copy the SQLite index consistently")
    snapshot.add_argument("target")
    preview = commands.add_parser("preview-site", help="build a docs folder into a static website ZIP, no instance needed")
    preview.add_argument("docs_dir")
    preview.add_argument("target", help="the ZIP to write")
    preview.add_argument("--name", default="Documentation", help="the project's name on the site")
    preview.add_argument("--summary", default="", help="also write pages and warnings as JSON to this file")
    seed = commands.add_parser("demo-seed", help="fill an empty demo instance (DEMO_MODE) with its account and docs")
    seed.add_argument("docs_dir")
    seed.add_argument("--name", default="DocuWaves")
    args = parser.parse_args(argv)

    if args.command == "reset-password":
        password = sys.stdin.readline().rstrip("\r\n")
        return reset_password(args.username, password)
    if args.command == "users":
        return list_users()
    if args.command == "demo-seed":
        return demo_seed(args.docs_dir, args.name)
    if args.command == "preview-site":
        return preview_site(args.docs_dir, args.target, args.name, args.summary)
    return snapshot_db(args.target)


if __name__ == "__main__":
    sys.exit(main())
