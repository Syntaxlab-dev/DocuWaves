"""Import straight from a Git repository URL: the documentation folder of a
project on GitHub, GitLab, Codeberg or a Forgejo of your own, without
downloading and re-uploading a ZIP.

It is the ZIP import (services/importer.py) with a different first step:
the repository is cloned (one commit deep, no submodules, no LFS) into a
temporary directory, the files the importer reads at all are packed into a
ZIP in memory, and from there everything is the same code -- the same
detection of MkDocs, Docusaurus, GitBook and the rest, the same preview,
the same limits, every page a draft, one commit.

THE URL IS UNTRUSTED INPUT, even from an administrator: it makes this
server open a connection. Only `https://` is accepted (no `file://`, no
`ssh`, no `git://`, and git's own protocol allow-list says the same), and
an address that resolves to the server itself or to a link-local address --
where cloud metadata services answer -- is refused. Private network
addresses are allowed on purpose: a Forgejo on the same LAN is the most
ordinary place for a self-hosted team's repository to be.

A token for a private repository can be passed with the request. It is
used for this one clone and never stored.
"""
import io
import ipaddress
import os
import posixpath
import socket
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from app.services import importer

CLONE_TIMEOUT_SECONDS = 120


class GitImportError(importer.ImportError_):
    pass


def _check_url(url: str) -> str:
    url = (url or "").strip()
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise GitImportError("Enter the repository's https:// address, e.g. https://github.com/org/project.git.")
    if parts.username or parts.password:
        raise GitImportError("Put the token in its own field, not in the address.")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise GitImportError(f"The host {parts.hostname} could not be found.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
            raise GitImportError(f"{parts.hostname} points at an address this server does not clone from.")
    return url


def _with_token(url: str, token: str) -> str:
    if not token:
        return url
    parts = urlsplit(url)
    netloc = f"x-access-token:{quote(token, safe='')}@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _clean_subdir(path: str) -> str:
    path = (path or "").strip().strip("/")
    if not path:
        return ""
    normalised = posixpath.normpath(path)
    if normalised.startswith("..") or normalised.startswith("/"):
        raise GitImportError("The folder has to be inside the repository.")
    return normalised


def archive(url: str, *, branch: str = "", subdir: str = "", token: str = "") -> bytes:
    """The repository (or one folder of it) as the ZIP the importer reads."""
    url = _check_url(url)
    subdir = _clean_subdir(subdir)
    branch = (branch or "").strip()
    if branch.startswith("-"):
        raise GitImportError("That is not a branch name.")
    with tempfile.TemporaryDirectory(prefix="docuwaves-git-import-") as tmp:
        target = Path(tmp) / "repo"
        command = ["git", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
                   "clone", "--depth", "1", "--no-tags", "--single-branch"]
        if branch:
            command += ["--branch", branch]
        command += ["--", _with_token(url, token), str(target)]
        env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_LFS_SKIP_SMUDGE": "1",
            "GIT_ALLOW_PROTOCOL": "https",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        try:
            result = subprocess.run(
                command, env=env, capture_output=True, text=True, timeout=CLONE_TIMEOUT_SECONDS, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise GitImportError(
                f"Cloning took longer than {CLONE_TIMEOUT_SECONDS} seconds. Import a ZIP of the docs folder instead."
            ) from exc
        if result.returncode != 0:
            message = (result.stderr or "").replace(token, "***") if token else (result.stderr or "")
            last = [line for line in message.splitlines() if line.strip()][-1:] or ["unknown error"]
            raise GitImportError(f"The repository could not be cloned: {last[0].strip()}")

        root = target / subdir if subdir else target
        if not root.is_dir():
            raise GitImportError(f"There is no folder '{subdir}' in the repository.")
        buffer = io.BytesIO()
        total = 0
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as packed:
            for file in sorted(root.rglob("*")):
                relative = file.relative_to(root).as_posix()
                if relative.startswith(".git/") or file.is_symlink() or not file.is_file():
                    continue
                if not importer.wanted_path(relative):
                    continue
                size = file.stat().st_size
                total += size
                if total > importer.MAX_UNPACKED_BYTES:
                    raise GitImportError("The documentation in this repository is larger than the import takes.")
                packed.write(file, relative)
        return buffer.getvalue()
