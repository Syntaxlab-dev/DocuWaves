"""The tools an AI assistant sees behind the MCP endpoint (routers/mcp.py):
what each one does, what it takes, and the code that answers it.

The split from the router is the JSON-RPC envelope: everything about
`initialize`/`tools/list`/`tools/call` -- ids, error codes, the content
wrapper -- lives up there, and everything about DocuWaves' own content lives
down here, where it can call the same stores the admin UI calls without
knowing it is being reached over JSON-RPC.

THREE RULES SHAPE EVERY TOOL BELOW.

1. The descriptions are the interface. A model picking a tool has nothing
   but `tools/list` to go on -- no README, no source, no colleague to ask.
   So each description says what the tool does, what each parameter means,
   and where the walls are (frozen versions are read-only, search only sees
   published pages, a slug is derived from the title and not chosen). A
   vague description here doesn't make the feature slightly worse, it makes
   the model guess.

2. Errors are instructions, not verdicts. "Category not found" tells a model
   nothing it can act on; "no category 'setup' in project 'cachepanel'
   (version current); available: getting-started (Getting Started),
   reference (Reference)" tells it exactly what to call next. Every failure
   below raises ToolError with that shape, and the router turns it into an
   MCP tool error the model reads.

3. Writes take no shortcuts. They go through the same *_store.py functions
   the admin editor uses, which means they get the same slug generation, the
   same "frozen versions are read-only" refusal, the same language
   validation, and the same commit-and-push -- and they get them by
   construction rather than by remembering to. The only thing a write
   through a token does differently is its git AUTHOR (see
   api_tokens_store.author_name), so `git log` shows which token wrote what.

There is deliberately NO DELETE TOOL. Creating and editing are recoverable
-- every one is a commit, and `git revert` puts a page back exactly as it
was. Deleting a page or a category is a bigger, quieter action: it is the
one operation whose damage isn't visible in the docs afterwards (nothing
looks broken, something is simply gone), and the value of handing it to an
autonomous agent is close to zero, because an assistant that is wrong about
a page being obsolete is wrong in a way nobody notices for weeks. Deletion
stays in the admin UI, where a human confirms it.
"""

from app.services import (
    api_tokens_store,
    categories_store,
    content_files,
    content_versions,
    git_content_repo,
    pages_store,
    projects_store,
    site_languages,
)


class ToolError(Exception):
    """A tool could not do what was asked, for a reason the caller can act
    on. The message is written for a model to read and retry with, so it
    names the thing that was wrong AND what is actually available."""


# ---- Shared lookups: every one of these fails with a list of what exists --


def _project(slug: str) -> dict:
    if not slug:
        raise ToolError("The 'project' parameter is required. Call list_projects to see the available project slugs.")
    project = projects_store.get_project_by_slug(slug)
    if project is not None:
        return project
    available = [p["slug"] for p in projects_store.list_projects()]
    raise ToolError(
        f"No project with slug '{slug}'. "
        + (f"Available project slugs: {', '.join(available)}." if available else "This instance has no projects yet.")
    )


def _version(project: dict, requested: str | None) -> str:
    """The documentation version to read. Blank means the one being edited
    -- the project directory itself while the project has no versions,
    `current` once it has (see content_versions.py)."""
    slug = project["slug"]
    if not requested:
        return content_versions.writable_version(slug)
    known = content_versions.version_ids(slug)
    if requested in known:
        return requested
    if not known:
        raise ToolError(
            f"Project '{slug}' has no documentation versions at all, so it takes no 'version' parameter -- "
            f"its pages live directly in the project. Omit 'version'."
        )
    raise ToolError(f"Project '{slug}' has no version '{requested}'. Available versions: {', '.join(known)}.")


def _writable_version(project: dict, requested: str | None) -> str:
    """The version a WRITE targets. Same resolution as a read, and then the
    frozen check -- which is the point of accepting `version` on a write at
    all rather than silently forcing the writable one. An assistant that
    just read a page at v2.0 and wants to correct it there has to be TOLD
    that it can't, because the alternative (quietly writing the fix into
    `current`) leaves it believing it fixed a released version's docs when
    it changed a different one."""
    version = _version(project, requested)
    # Raises FrozenVersionError with the message every other write path in
    # this app produces for the same mistake -- caught by the router.
    content_versions.ensure_writable(project["slug"], version)
    return version


def _language(requested: str | None) -> str:
    """The content language a page is read or written in. Blank means the
    site's default, which is every page on a single-language instance."""
    if not requested:
        return site_languages.default_language()
    configured = site_languages.languages()
    if requested in configured:
        return requested
    if not configured:
        raise ToolError(
            f"This instance is single-language, so it takes no 'language' parameter (got '{requested}'). "
            f"Omit it."
        )
    raise ToolError(
        f"'{requested}' is not one of this site's configured languages. Configured: {', '.join(configured)} "
        f"(the first is the default)."
    )


def _describe_categories(categories: list[dict]) -> str:
    return ", ".join(f"{c['slug']} ({c['name']})" for c in categories) or "none"


def _category(project: dict, version: str, reference: str) -> dict:
    """A category by its SLUG, or -- as a convenience for a model that only
    saw the human-readable name -- by an exact, case-insensitive name match.
    Both, because `tools/list` tells the model to pass a slug but a name is
    the plausible mistake, and answering a plausible mistake correctly is
    cheaper than a round trip."""
    if not reference:
        raise ToolError("The 'category' parameter is required. Call list_pages to see this project's categories.")
    categories = categories_store.list_categories(project["id"], "", version)
    for category in categories:
        if category["slug"] == reference:
            return category
    lowered = reference.strip().lower()
    matches = [c for c in categories if c["name"].strip().lower() == lowered]
    if len(matches) == 1:
        return matches[0]
    raise ToolError(
        f"No category '{reference}' in project '{project['slug']}' (version "
        f"'{version or 'the project itself'}'); available: {_describe_categories(categories)}. "
        f"Use the slug. To add one, call create_category."
    )


def _require_content_repo() -> None:
    """Every write here is a git commit, so the repository has to open first.
    It practically always does -- an instance with no CONTENT_REPO_URL has a
    local one rather than none at all -- but an unwritable volume or an
    unreachable remote is still a real answer, and the assistant's own
    retry-or-tell-the-operator decision depends on hearing it."""
    try:
        git_content_repo.ensure_clone()
    except git_content_repo.GitContentError as exc:
        raise ToolError(
            f"This DocuWaves instance's content repository could not be opened, so nothing can be written "
            f"-- every write is a git commit. Reading still works. Tell the operator: {exc}"
        ) from exc


def _page_entry(page: dict) -> dict:
    return {
        "slug": page["slug"],
        "title": page["title"],
        "language": page["language"],
        "version": page["version"],
        "published": page["published"],
    }


# ---- Read tools ----


def list_projects(_arguments: dict, _token: dict) -> dict:
    """Every project, with the slug that identifies it everywhere else."""
    projects = projects_store.list_projects()
    entries = []
    for project in projects:
        document = content_versions.read_versions(project["slug"])
        entries.append(
            {
                "slug": project["slug"],
                "name": project["name"],
                "description": project["description"],
                # The version dimension, spelled out per project rather than
                # left for the model to discover by getting it wrong: which
                # version reads by default, which one writes land in, and
                # which ones are frozen.
                "versioned": document is not None,
                "writable_version": content_versions.writable_version(project["slug"]),
                "default_version": content_versions.default_version(project["slug"]),
                "frozen_versions": [v["id"] for v in document["versions"]] if document else [],
            }
        )
    return {
        "projects": entries,
        "languages": site_languages.languages(),
        "default_language": site_languages.default_language(),
    }


def list_pages(arguments: dict, _token: dict) -> dict:
    """A project's categories and the pages in them, one entry per page PER
    LANGUAGE -- because which languages a page does and does not exist in is
    exactly the thing a caller is here to find out."""
    project = _project(arguments.get("project", ""))
    version = _version(project, arguments.get("version"))
    categories = categories_store.list_categories(project["id"], "", version)
    return {
        "project": project["slug"],
        "version": version,
        "frozen": content_versions.is_frozen(project["slug"], version),
        "categories": [
            {
                "slug": category["slug"],
                "name": category["name"],
                "icon": category["icon"],
                "pages": [_page_entry(p) for p in pages_store.list_all_pages(category["id"])],
            }
            for category in categories
        ],
    }


def read_page(arguments: dict, _token: dict) -> dict:
    """One page's Markdown, exactly as it sits in the content repo (the
    frontmatter is split off into the fields beside it)."""
    project = _project(arguments.get("project", ""))
    version = _version(project, arguments.get("version"))
    language = _language(arguments.get("language"))
    slug = (arguments.get("page") or "").strip()
    if not slug:
        raise ToolError("The 'page' parameter is required -- a page slug, as list_pages reports it.")

    # resolve_page, not get_page_by_slug: a page that exists only in the
    # site's default language is still a page this caller asked for, and
    # answering "no such page" because the English translation hasn't been
    # written would be a dead end where the public site itself shows the
    # German one with a notice. `fallback` says which happened.
    page = pages_store.resolve_page(project["id"], slug, language, published_only=False, version=version)
    if page is None:
        raise ToolError(
            f"No page '{slug}' in project '{project['slug']}' (version '{version or 'the project itself'}'). "
            f"Call list_pages to see the pages that exist there."
        )
    category = categories_store.get_category(page["category_id"])
    return {
        "project": project["slug"],
        "category": {"slug": category["slug"], "name": category["name"]} if category else None,
        "page": _page_entry(page),
        "requested_language": language,
        # True = this page has no version in the language asked for, and the
        # one below is another language's text. Worth acting on: writing an
        # "update" against it would overwrite the wrong translation.
        "fallback": bool(page.get("fallback")),
        "available_languages": pages_store.page_languages(project["id"], slug, version),
        "updated_at": page["updated_at"],
        "markdown": page["markdown_content"],
    }


def search(arguments: dict, _token: dict) -> dict:
    """Full-text search over PUBLISHED pages -- the same index and the same
    ranking the public search box uses."""
    query = (arguments.get("query") or "").strip()
    if not query:
        raise ToolError("The 'query' parameter is required and can't be empty.")
    limit = arguments.get("limit")
    if limit is None:
        limit = 20
    if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= 50):
        raise ToolError("'limit' must be a whole number between 1 and 50.")

    language = _language(arguments.get("language"))
    project_id = None
    version = None
    if arguments.get("project"):
        project = _project(arguments["project"])
        project_id = project["id"]
        # Scoping to a project also scopes to ONE of its versions, or the
        # same page would come back once per frozen release.
        version = _version(project, arguments.get("version"))
    results = pages_store.search(query, limit=limit, language=language, project_id=project_id, version=version)
    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "project": r["project_slug"],
                "page": r["page_slug"],
                "title": r["title"],
                "category": r["category_slug"],
                "language": r["language"],
                "version": r["version"],
                "snippet": r["snippet"],
            }
            for r in results
        ],
    }


# ---- Write tools ----
#
# Each one is `"write": True` in TOOLS below, which is what the router
# checks a token's scope against before it ever gets here.


def create_page(arguments: dict, token: dict) -> dict:
    project = _project(arguments.get("project", ""))
    version = _writable_version(project, arguments.get("version"))
    _require_content_repo()
    category = _category(project, version, arguments.get("category", ""))
    language = _language(arguments.get("language"))
    title = (arguments.get("title") or "").strip()
    if not title:
        raise ToolError("The 'title' parameter is required -- it is what the page is called, and where its slug comes from.")
    markdown = arguments.get("markdown")
    if markdown is None:
        markdown = ""
    if not isinstance(markdown, str):
        raise ToolError("'markdown' must be a string (the page body, without YAML frontmatter).")

    # The same slug the admin editor would mint for this title, including
    # the -2/-3 suffix when one is taken (see content_files.unique_slug).
    slug = content_files.unique_slug(title, pages_store.slug_taken, project["id"], version)
    author = api_tokens_store.author_name(token["name"])
    page = pages_store.create_page(project["id"], category["id"], title, slug, markdown, author, language)
    if page is None:
        raise ToolError(
            "The page file was written and committed but could not be read back as a page -- something about "
            "the write disagrees with the way the index reads the content repo. Check the server log."
        )
    published = _publish_flag(arguments)
    if published:
        pages_store.set_published(page["id"], True, author)
    return {
        "created": True,
        "project": project["slug"],
        "category": category["slug"],
        "page": _page_entry({**page, "published": bool(published)}),
        "commit_author": author,
    }


def update_page(arguments: dict, token: dict) -> dict:
    project = _project(arguments.get("project", ""))
    version = _writable_version(project, arguments.get("version"))
    _require_content_repo()
    language = _language(arguments.get("language"))
    slug = (arguments.get("page") or "").strip()
    if not slug:
        raise ToolError("The 'page' parameter is required -- the slug of the page to update, as list_pages reports it.")
    markdown = arguments.get("markdown")
    if not isinstance(markdown, str):
        raise ToolError(
            "'markdown' is required and must be a string: the page's FULL new body. This tool replaces the "
            "body, it does not append to it -- call read_page first if you mean to edit rather than replace."
        )

    # Exactly this language's row, never a fallback: writing is the one
    # place where "close enough" would overwrite a different translation
    # than the one asked for.
    page = pages_store.get_page_by_slug(project["id"], slug, language, version)
    if page is None:
        existing = pages_store.page_languages(project["id"], slug, version)
        if existing:
            raise ToolError(
                f"Page '{slug}' exists in project '{project['slug']}' but has no version in language "
                f"'{language}' yet -- it exists in: {', '.join(existing)}. This tool only updates a "
                f"translation that already exists; creating one is a content-repo edit."
            )
        raise ToolError(
            f"No page '{slug}' in project '{project['slug']}' (version '{version or 'the project itself'}'). "
            f"Call list_pages to see what is there, or create_page to add it."
        )

    title = arguments.get("title")
    title = page["title"] if title is None else str(title).strip()
    if not title:
        raise ToolError("'title' can't be empty. Omit it entirely to keep the page's current title.")

    # Only the DEFAULT language's title steers the slug -- the same rule the
    # admin editor follows, and for the same reason: a page's translations
    # share one slug, so renaming the English title must not move the URL
    # the German page was bookmarked at.
    renamable = page["language"] == site_languages.default_language()
    new_slug = (
        page["slug"]
        if title == page["title"] or not renamable
        else content_files.unique_slug(
            title, pages_store.slug_taken, project["id"], version, exclude_id=page["id"]
        )
    )

    author = api_tokens_store.author_name(token["name"])
    updated = pages_store.update_page(page["id"], title, new_slug, markdown, page["category_id"], author)
    if updated is None:
        raise ToolError("The page could not be updated -- it may have been removed in the content repo meanwhile.")

    published = arguments.get("published")
    if published is not None:
        if not isinstance(published, bool):
            raise ToolError("'published' must be true or false.")
        # Only when it actually changes: set_published is its own commit,
        # and re-stating the current state would put an empty one in the
        # history on every single update.
        #
        # Addressed by the row as it reads back AFTER the update, not by the
        # id this function started with: a title change that moves the slug
        # moves the file, and the reindex that follows gives the page a new
        # id (see content_sync.py -- rows are matched by slug, not by id).
        if published != updated["published"]:
            pages_store.set_published(updated["id"], published, author)
            updated = {**updated, "published": published}

    return {
        "updated": True,
        "project": project["slug"],
        "page": _page_entry(updated),
        # Spelled out because it may not be the slug that was passed in: a
        # renamed page has a new URL, and a caller holding the old one would
        # otherwise keep addressing a page that no longer answers.
        "renamed": updated["slug"] != slug,
        "commit_author": author,
    }


def create_project(arguments: dict, token: dict) -> dict:
    """The top level, and the one an empty instance cannot do without.

    Left out of the first version of this interface by oversight rather than
    by decision. Withholding a DELETE tool is deliberate -- deleting is the
    one operation the git history does not make painless to undo. But
    creating a project is exactly as recoverable as creating a page: it is a
    single commit adding one _project.yml, revertable like any other. The
    asymmetry only showed up in practice, when an assistant was handed a
    write token, pointed at a fresh instance, and could not begin: every
    other tool resolves a project first, so with none present all seven were
    unreachable.
    """
    _require_content_repo()
    name = (arguments.get("name") or "").strip()
    if not name:
        raise ToolError("The 'name' parameter is required -- what the project is called, and where its slug comes from.")

    existing = projects_store.list_projects()
    slug = content_files.unique_slug(name, projects_store.slug_taken)
    author = api_tokens_store.author_name(token["name"])
    project = projects_store.create_project(
        name,
        slug,
        str(arguments.get("icon") or "").strip(),
        str(arguments.get("color") or "").strip(),
        str(arguments.get("description") or "").strip(),
        author,
    )
    if project is None:
        raise ToolError("The project could not be created -- check the server log.")
    return {
        "created": True,
        "project": {
            "slug": project["slug"],
            "name": project["name"],
            "icon": project["icon"],
            "description": project["description"],
        },
        # Named because a project is where every other tool starts, and an
        # assistant that has just created the first one has nothing else to
        # go on yet.
        "next": "Add a category with create_category, then pages with create_page."
        if not existing else "Use this slug as the 'project' argument to the other tools.",
        "commit_author": author,
    }


def create_category(arguments: dict, token: dict) -> dict:
    project = _project(arguments.get("project", ""))
    _require_content_repo()
    name = (arguments.get("name") or "").strip()
    if not name:
        raise ToolError("The 'name' parameter is required -- what the category is called, and where its slug comes from.")
    icon = str(arguments.get("icon") or "").strip()
    order = arguments.get("order")
    if order is not None and (not isinstance(order, int) or isinstance(order, bool)):
        raise ToolError("'order' must be a whole number (lower sorts first), or omitted to add the category last.")

    # Always the writable version -- there is no way to add a section to a
    # frozen release's docs, here or in the admin UI, so this tool takes no
    # 'version' parameter at all rather than one whose only other value is
    # refused.
    version = content_versions.writable_version(project["slug"])
    slug = content_files.unique_slug(name, categories_store.slug_taken, project["id"], version)
    author = api_tokens_store.author_name(token["name"])
    category = categories_store.create_category(project["id"], name, slug, icon, author, None, order)
    if category is None:
        raise ToolError("The category could not be created -- check the server log.")
    return {
        "created": True,
        "project": project["slug"],
        "category": {
            "slug": category["slug"],
            "name": category["name"],
            "icon": category["icon"],
            "version": category["version"],
            "order": category["sort_order"],
        },
        "commit_author": author,
    }


def _publish_flag(arguments: dict) -> bool:
    published = arguments.get("published")
    if published is None:
        return False
    if not isinstance(published, bool):
        raise ToolError("'published' must be true or false.")
    return published


# ---- The catalogue `tools/list` answers with ----
#
# `inputSchema` is JSON Schema, which is what an MCP client hands the model
# as the tool's signature. Every property carries its own description for
# the same reason the tool does: the model reads these and nothing else.

_PROJECT_PROPERTY = {
    "type": "string",
    "description": "The project's slug, exactly as list_projects reports it (e.g. 'cachepanel').",
}

_VERSION_PROPERTY = {
    "type": "string",
    "description": "Documentation version id, e.g. 'v2.0'. Omit for the version being edited ('current', or the "
    "project itself when it has no versions at all). Most projects have none -- list_projects says which do.",
}

_LANGUAGE_PROPERTY = {
    "type": "string",
    "description": "Two-letter content language code, e.g. 'en'. Omit for the site's default language. Only "
    "codes list_projects reports under 'languages' are accepted; a single-language instance takes none.",
}

TOOLS: list[dict] = [
    {
        "name": "list_projects",
        "write": False,
        "description": (
            "List every documentation project in this DocuWaves instance, with the slug that identifies it in "
            "every other tool. Start here: nothing else can be addressed without a project slug. The answer also "
            "reports this instance's configured content languages and, per project, its documentation versions -- "
            "'writable_version' is where writes go, 'frozen_versions' are read-only snapshots of past releases."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": list_projects,
    },
    {
        "name": "list_pages",
        "write": False,
        "description": (
            "List one project's categories and the pages inside them. This is the map of a project: use it to find "
            "the page slug that read_page and update_page take. Pages are listed ONE ENTRY PER LANGUAGE, so a page "
            "written in two languages appears twice under one slug -- which is how you see which translations "
            "exist. Unpublished drafts are included and marked 'published': false; the public site does not show "
            "them, but they are pages you can read and edit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"project": _PROJECT_PROPERTY, "version": _VERSION_PROPERTY},
            "required": ["project"],
            "additionalProperties": False,
        },
        "handler": list_pages,
    },
    {
        "name": "read_page",
        "write": False,
        "description": (
            "Read one page's full Markdown source, exactly as it is stored in the content repo (the YAML "
            "frontmatter is returned as separate fields, not as part of the body). Always call this before "
            "update_page: that tool REPLACES the body rather than appending to it. If the page has no version in "
            "the language asked for, another language's text is returned rather than an error, with "
            "'fallback': true -- do not update against a fallback, it is a different translation's file."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROPERTY,
                "page": {
                    "type": "string",
                    "description": "The page's slug, as list_pages reports it (e.g. 'installation'). Not its title.",
                },
                "language": _LANGUAGE_PROPERTY,
                "version": _VERSION_PROPERTY,
            },
            "required": ["project", "page"],
            "additionalProperties": False,
        },
        "handler": read_page,
    },
    {
        "name": "search",
        "write": False,
        "description": (
            "Full-text search across the documentation -- the same index the site's own search box uses. Covers "
            "PUBLISHED pages only, in one language and one documentation version per project; to find an "
            "unpublished draft, use list_pages instead. Each hit names the project and page slug, so a result can "
            "be handed straight to read_page. Use this to find where something is documented; use list_pages when "
            "you already know the project and want its structure."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The words to search for. Terms are OR'd and ranked by relevance; this is a "
                    "word search, not a regular expression or a glob.",
                },
                "project": {
                    "type": "string",
                    "description": "Optional project slug to search inside one project only. Omit to search every "
                    "project (each in its own default documentation version).",
                },
                "language": _LANGUAGE_PROPERTY,
                "version": _VERSION_PROPERTY,
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of hits, 1-50. Defaults to 20.",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "handler": search,
    },
    {
        "name": "create_page",
        "write": True,
        "description": (
            "Create a new documentation page in a category, and commit it to the content repo. REQUIRES a token "
            "with 'write' scope. The page's slug (its URL) is derived from the title the same way the admin "
            "editor derives it -- you cannot choose it, and a title colliding with an existing page gets a '-2' "
            "suffix; the answer reports the slug that was actually used. The page is created as an unpublished "
            "draft unless 'published' is true. Frozen documentation versions are read-only: naming one in "
            "'version' is refused, it is not silently redirected to the version being edited."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROPERTY,
                "category": {
                    "type": "string",
                    "description": "The slug of the category to create the page in, as list_pages reports it. The "
                    "category must already exist -- call create_category first if it doesn't.",
                },
                "title": {
                    "type": "string",
                    "description": "The page's title. Also what its slug is derived from.",
                },
                "markdown": {
                    "type": "string",
                    "description": "The page body as GitHub-flavored Markdown. Do NOT include YAML frontmatter: "
                    "title, order and published state are stored separately and written for you. Images are "
                    "referenced relative to the page, as '![alt](../assets/name.png)'.",
                },
                "language": _LANGUAGE_PROPERTY,
                "published": {
                    "type": "boolean",
                    "description": "true to publish the page to the public site immediately. Defaults to false "
                    "(a draft, visible only through this API and the admin UI).",
                },
                "version": _VERSION_PROPERTY,
            },
            "required": ["project", "category", "title", "markdown"],
            "additionalProperties": False,
        },
        "handler": create_page,
    },
    {
        "name": "update_page",
        "write": True,
        "description": (
            "Replace an existing page's Markdown body, and commit the change. REQUIRES a token with 'write' "
            "scope. This REPLACES the whole body -- read_page first and send back the full text with your edit "
            "applied, or you will delete everything you did not resend. Optionally also changes the title and the "
            "published state. Changing the title of a page in the site's DEFAULT language changes its slug and "
            "therefore its public URL (the answer reports 'renamed': true and the new slug); changing a "
            "translation's title never does. Frozen documentation versions are read-only and refuse this call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROPERTY,
                "page": {
                    "type": "string",
                    "description": "The slug of the page to update, as list_pages reports it.",
                },
                "markdown": {
                    "type": "string",
                    "description": "The page's complete new body, GitHub-flavored Markdown, without YAML "
                    "frontmatter. Replaces the existing body entirely.",
                },
                "title": {
                    "type": "string",
                    "description": "Optional new title. Omit to keep the current one.",
                },
                "published": {
                    "type": "boolean",
                    "description": "Optional: true publishes the page, false turns it back into a draft. Omit to "
                    "leave the published state alone.",
                },
                "language": _LANGUAGE_PROPERTY,
                "version": _VERSION_PROPERTY,
            },
            "required": ["project", "page", "markdown"],
            "additionalProperties": False,
        },
        "handler": update_page,
    },
    {
        "name": "create_project",
        "write": True,
        "description": (
            "Create a new project, and commit it. REQUIRES a token with 'write' scope. A project is the top "
            "level: it holds categories, which hold pages, and every other tool here takes a project slug as "
            "its first argument -- so on an instance with no projects yet, this is where to start. Create one "
            "per piece of software or product being documented, not per topic; topics are categories. The slug "
            "is derived from the name and becomes part of every URL underneath it, so it is worth getting the "
            "name right the first time."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The project's name, e.g. 'CachePanel'. Also what its slug is derived from.",
                },
                "icon": {
                    "type": "string",
                    "description": "Optional single emoji shown on the project's tile, e.g. '📦'.",
                },
                "color": {
                    "type": "string",
                    "description": "Optional accent colour as a hex value, e.g. '#00d4d5'.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional one-line description shown on the home page tile.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "handler": create_project,
    },
    {
        "name": "create_category",
        "write": True,
        "description": (
            "Create a new category in a project, and commit it. REQUIRES a token with 'write' scope. A category "
            "is the grouping level between a project and its pages -- it is shown as a tile on the project's page "
            "and as a section in the sidebar, so create one only when a page genuinely does not belong in any "
            "existing category. Its slug is derived from the name, like a page's is from its title. Always "
            "created in the version being edited: a frozen release never gains a new section, so this tool takes "
            "no 'version' parameter."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT_PROPERTY,
                "name": {
                    "type": "string",
                    "description": "The category's name, e.g. 'Getting Started'. Also what its slug is derived from.",
                },
                "icon": {
                    "type": "string",
                    "description": "Optional single emoji shown on the category's tile, e.g. '📘'.",
                },
                "order": {
                    "type": "integer",
                    "description": "Optional sort position among the project's categories -- lower sorts first. "
                    "Omit to add the category after the existing ones.",
                },
            },
            "required": ["project", "name"],
            "additionalProperties": False,
        },
        "handler": create_category,
    },
]

_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def public_catalogue() -> list[dict]:
    """TOOLS as `tools/list` answers it -- without the two keys that are
    ours and not the protocol's (`handler`, `write`)."""
    return [{k: v for k, v in tool.items() if k not in ("handler", "write")} for tool in TOOLS]


def get(name: str) -> dict | None:
    return _BY_NAME.get(name)


def tool_names() -> list[str]:
    return [tool["name"] for tool in TOOLS]


def read_only_names() -> list[str]:
    return [tool["name"] for tool in TOOLS if not tool["write"]]
