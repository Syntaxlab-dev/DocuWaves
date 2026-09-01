"""Image assets inside the content repo -- pure file I/O plus the safety
rules around it, no git and no database (same split as content_files.py,
which owns the Markdown/YAML side of the same clone).

Convention (see the README's "Content repo structure" section):

    content/<project-slug>/assets/<filename>

A page at content/<project>/<category>/<page>.md references one with a
NORMAL relative Markdown path -- `![Dashboard](../assets/dashboard.png)` --
deliberately, so GitHub/Gitea's own file preview of that same .md renders
the image too. A rewritten absolute URL in the source would only ever work
inside DocuWaves itself.

Resolution rule: a page's relative path is resolved against that page's own
directory in the clone, and the result must stay inside that page's own
PROJECT directory. `../assets/x.png` from a category directory lands in the
project's assets/ folder (fine); `../../other-project/x.png`, an absolute
path, or a symlink pointing out of the clone must never resolve (see
resolve_asset() -- it compares fully resolved paths, never string prefixes,
so a symlink or a `..` segment can't sneak past it).

Uploads are validated on real file content, never on the extension or the
client's declared content-type alone: an "image/png" upload whose bytes are
a PHP script would otherwise sit in a public repo waiting for someone to
misconfigure a webserver over it. SVG is the special case -- it's XML that
can carry script, so it gets parsed and screened rather than sniffed for a
magic number.
"""

from pathlib import Path
from xml.etree import ElementTree

from slugify import slugify

from app.services.content_files import content_root
from app.settings import settings

_ASSETS_DIRNAME = "assets"

# Fixed lookup table -- the Content-Type served to a visitor is decided here
# and nowhere else. mimetypes.guess_type() reads the system's mime.types,
# which differs per base image and would make what gets served depend on the
# container's OS packages rather than on this file.
CONTENT_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
}

MAX_ASSET_BYTES = 10 * 1024 * 1024


def assets_dir(project_slug: str) -> Path:
    return content_root() / project_slug / _ASSETS_DIRNAME


def _rel(path: Path) -> str:
    return str(path.relative_to(Path(settings.content_repo_path)))


def _project_dir(project_slug: str) -> Path | None:
    """The resolved project directory, or None if `project_slug` doesn't
    name a real directory sitting DIRECTLY inside content/ -- that parent
    check is what stops a slug of `..` (or a symlinked project directory)
    from turning the whole clone, .git included, into the resolution root
    below."""
    root = content_root().resolve()
    candidate = (root / project_slug).resolve()
    if candidate.parent != root or not candidate.is_dir():
        return None
    return candidate


def resolve_asset(project_slug: str, relative_path: str) -> Path | None:
    """Maps a project-relative asset path to a real file, or None if it
    doesn't exist, isn't an allowed image type, or escapes the project
    directory. None is deliberately the single answer for all three: the
    public endpoint turns it into a 404 either way, so a probe can't tell
    "wrong extension" from "outside the project" from "not there"."""
    project_dir = _project_dir(project_slug)
    if project_dir is None:
        return None

    # Path("/a") / "/etc/passwd" == Path("/etc/passwd"), and resolve()
    # follows every symlink on the way -- so both the absolute-path and the
    # symlink-out-of-the-repo cases end up outside project_dir here and get
    # rejected by the same containment check as a plain `../..`.
    candidate = (project_dir / relative_path).resolve()
    if not candidate.is_relative_to(project_dir):
        return None
    if candidate.suffix.lower() not in CONTENT_TYPES:
        return None
    if not candidate.is_file():
        return None
    return candidate


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES[path.suffix.lower()]


def markdown_path(filename: str) -> str:
    """What the author pastes into a page. A page sits one directory deeper
    than assets/ (content/<project>/<category>/<page>.md), so the way out of
    the category and back into assets/ is always exactly one `..`."""
    return f"../{_ASSETS_DIRNAME}/{filename}"


def public_url(project_slug: str, filename: str) -> str:
    """The same file as the public serving endpoint addresses it -- used for
    the admin uploader's preview, where markdown_path() alone wouldn't
    resolve (the editor isn't sitting in a category directory)."""
    return f"/api/public/assets/{project_slug}/{_ASSETS_DIRNAME}/{filename}"


def list_assets(project_slug: str) -> list[dict]:
    directory = assets_dir(project_slug)
    if not directory.is_dir():
        return []
    return sorted(
        (
            {"filename": p.name, "size": p.stat().st_size}
            for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in CONTENT_TYPES
        ),
        key=lambda a: a["filename"],
    )


def unique_filename(project_slug: str, original_name: str) -> str:
    """Slugified stem + the real extension, suffixed -2, -3, ... until it's
    free. Never overwrites: two authors uploading their own "screenshot.png"
    would otherwise silently replace each other's image on pages neither of
    them is editing."""
    source = Path(original_name)
    stem = slugify(source.stem) or "image"
    extension = source.suffix.lower()
    directory = assets_dir(project_slug)
    candidate = f"{stem}{extension}"
    n = 2
    while (directory / candidate).exists():
        candidate = f"{stem}-{n}{extension}"
        n += 1
    return candidate


def write_asset(project_slug: str, filename: str, data: bytes) -> str:
    """Returns the written path relative to the content repo ROOT (not to
    content/), the form git_content_repo.commit_and_push() stages."""
    path = assets_dir(project_slug) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _rel(path)


def delete_asset(project_slug: str, filename: str) -> list[str]:
    """Empty list = the file wasn't there, which callers treat as a no-op
    rather than an error (same contract as content_files.delete_page)."""
    directory = assets_dir(project_slug)
    path = directory / filename
    # Defence in depth behind the router's own separator check: a name whose
    # parent isn't exactly this project's assets/ folder is treated the same
    # as a name that simply isn't there.
    if path.parent != directory or not path.is_file():
        return []
    rel = _rel(path)
    path.unlink()
    return [rel]


# ---- Upload validation ----


def _looks_like_avif(data: bytes) -> bool:
    # AVIF is ISOBMFF: [4-byte box size]["ftyp"][major brand]. The brand is
    # "avif" for a still and "avis" for a sequence, but encoders that share
    # HEIF's container machinery (libheif, macOS) legitimately stamp the
    # generic "mif1"/"msf1" brands instead and list "avif" only among the
    # compatible brands -- accept those rather than rejecting files every
    # major encoder produces.
    return len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis", b"mif1", b"msf1")


def _svg_rejection_reason(data: bytes) -> str | None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "That .svg file isn't valid UTF-8 text."

    # Screened before parsing, not after: entity declarations are the
    # "billion laughs" expansion vector, and ElementTree would already have
    # expanded them by the time we could look at the tree. Real-world SVGs
    # from Inkscape/Illustrator declare a DOCTYPE but never their own
    # entities, so this costs nothing legitimate.
    if "<!ENTITY" in text.upper():
        return "That .svg file declares XML entities, which isn't allowed."

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        return f"That .svg file isn't valid XML: {exc}"

    for element in root.iter():
        # Tags come out namespace-qualified ("{http://www.w3.org/2000/svg}script"),
        # so match on the local name after the closing brace.
        local_name = str(element.tag).rsplit("}", 1)[-1].lower()
        if local_name == "script":
            return "That .svg file contains a <script> element."
        for attribute, value in element.attrib.items():
            if attribute.rsplit("}", 1)[-1].lower().startswith("on"):
                return f"That .svg file contains an event handler attribute ({attribute})."
            if "javascript:" in value.lower().replace(" ", ""):
                return "That .svg file contains a javascript: URL."
    return None


def rejection_reason(filename: str, data: bytes) -> str | None:
    """None = accepted. Checks the extension AND the bytes behind it -- the
    client's declared content-type is never consulted at all, since it's the
    one part of an upload the uploader fully controls and nothing verifies."""
    extension = Path(filename).suffix.lower()
    if extension not in CONTENT_TYPES:
        allowed = ", ".join(sorted(CONTENT_TYPES))
        return f"Unsupported image type '{extension or filename}'. Allowed: {allowed}."
    if not data:
        return "The uploaded file is empty."
    if len(data) > MAX_ASSET_BYTES:
        return f"That image is {len(data) // 1024} KB; the limit is {MAX_ASSET_BYTES // (1024 * 1024)} MB."

    if extension == ".svg":
        return _svg_rejection_reason(data)

    magic_ok = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".gif": data.startswith(b"GIF87a") or data.startswith(b"GIF89a"),
        ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        ".avif": _looks_like_avif(data),
    }[extension]
    if not magic_ok:
        return f"That file's contents aren't a real {extension.lstrip('.').upper()} image."
    return None
