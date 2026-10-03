"""Maintenance commands run inside the container, for the `docuwaves` command
on the host (installer/docuwaves) -- or by hand:

    docker compose exec docuwaves python -m app.cli reset-password <username>
    docker compose exec docuwaves python -m app.cli users
    docker compose exec docuwaves python -m app.cli snapshot-db /data/snapshot.db

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-password", help="set an account's password, read from standard input")
    reset.add_argument("username")
    commands.add_parser("users", help="list the accounts and their roles")
    snapshot = commands.add_parser("snapshot-db", help="copy the SQLite index consistently")
    snapshot.add_argument("target")
    args = parser.parse_args(argv)

    if args.command == "reset-password":
        password = sys.stdin.readline().rstrip("\r\n")
        return reset_password(args.username, password)
    if args.command == "users":
        return list_users()
    return snapshot_db(args.target)


if __name__ == "__main__":
    sys.exit(main())
