# DocuWaves

A self-hosted documentation CMS. Content is Markdown+YAML files in a Git
repository you control — but it's edited through a real browser UI: the admin
editor writes the file and commits on save, so nobody has to touch `git`
directly if they don't want to.

**It needs no Git hosting account to run.** Start it with no configuration at
all and it creates its own repository inside its data volume; every page you
write is a real commit with real history. Point it at a remote later — on
GitHub, GitLab, your own Forgejo — and the history you already have is pushed
there, which is when a community can start contributing the normal way (fork,
edit a `.md` file, open a pull request). See "Setup" and "Adding a Git remote
later".

- **Multiple projects in one instance** — one DocuWaves deployment can
  host the docs for every app/tool you maintain, each with its own set of
  categories and pages, so visitors land on one shared homepage and click
  through to exactly the project they're looking for.
- **Categories as tiles** — a project's docs are grouped into categories,
  shown as clickable tiles rather than one long sidebar to scroll through.
  A project tile and a category tile can each carry a cover image, so the
  way into the docs looks like something (see "Tile cover images"); one
  that doesn't have one looks exactly as it always did.
- **Markdown, with a live preview** — pages are written in Markdown (GFM:
  tables, checklists, fenced code blocks with syntax highlighting) and
  edited in a split editor/preview pane. **Paste a screenshot straight in**
  (or drag image files onto it) and it is uploaded, committed and referenced
  at the cursor (see "Images"), and **unsaved text survives a closed tab** —
  it is kept in the browser and offered back when you return (see "Unsaved
  work").
- **Diagrams as text** — a ` ```mermaid ` block is drawn as a real diagram
  (see "Diagrams"): an architecture sketch, a request flow or a state
  machine stays in the `.md` file, diffs line by line in git, and needs no
  binary asset anyone has to keep in sync with the prose around it.
- **Content lives in Git, not a database** — every project/category/page is
  a plain file (see "Content repo structure" below) and every save is a
  commit. That is true with no remote configured: history, diffs, page
  restore and "who changed this" all come from the repository being *there*,
  not from it being hosted anywhere. Connect a remote and a community member
  can contribute via a normal pull request; DocuWaves picks up merged changes
  automatically (a background sync job, or a "Sync now" button in the admin
  UI).
- **Branded per instance** — name, tagline, logo, favicon, accent colour and
  footer come from a `_site.yml` in the content repo (see "Site branding"),
  so two deployments look like two different products without either of them
  needing its own build.
- **A project with nothing published stays off the public site** -- there is
  no separate switch for it: a project whose pages are all drafts has
  nothing a reader could open, so it appears only in the admin area. That
  is also how you keep a private set of notes in the same instance.
- **Draft vs. published** — a page stays invisible to the public site
  until you explicitly publish it.
- **Multiple languages, optionally** — a page can exist in several
  languages (`installation.de.md` next to `installation.en.md`), with the
  language in the URL, a switcher in the header, and an honest notice on a
  page that isn't translated yet rather than a dead end (see
  "Multiple languages"). Off unless you ask for it: an instance that never
  sets `languages:` behaves exactly as it always has.
- **Documentation versions, optionally** — freeze the docs at a release and
  they stay frozen: `v2.0` becomes its own directory, readable at
  `/de/p/cachepanel/v2.0/pages/installation`, while you keep editing the
  current one (see "Documentation versions"). Off unless you ask for it: a
  project that never freezes one keeps its files exactly where they are and
  has no version in its URLs at all.
- **Full-text search** across every published page in every project — in the
  language and the version the reader is currently in.
- **Findable, and shareable** — every public URL is answered with its own
  `<title>`, description, Open Graph/Twitter card, canonical and structured
  data, written by the server before the response leaves it. Search engines
  and link-preview crawlers (Discord, Slack, WhatsApp, Signal, Mastodon) run
  no JavaScript, so pasting a link to your installation guide shows *that
  page*, not the app shell. Plus `/sitemap.xml` and `/robots.txt` (see
  "Search engines and link previews").
- **Single admin account** — password login, or single sign-on via any
  standard OIDC provider (Authentik, Keycloak, Authelia, Zitadel, ...).
- **An AI assistant can read and write the docs** — generate an API token
  in the admin UI, hand it to Claude (or anything else that speaks MCP),
  and it can browse, search and — if the token says so — write the
  documentation, with every change arriving as a normal git commit named
  after the token (see "AI assistants: API tokens and the MCP endpoint").
- **SQLite by default** (a single file, zero configuration), with
  PostgreSQL as an optional upgrade for larger installs — either way, this
  is only ever a rebuildable search/browse *index* over the content repo's
  files, never the source of truth itself. Losing it isn't losing content;
  DocuWaves rebuilds it from the files on next startup or "Sync now".

## Setup

No account anywhere, no repository to create first, no token to mint:

1. Clone this repo and `cd` into it.
2. `docker compose up -d --build`
3. Open `http://<your-server>:8091` — the first thing you'll see is the
   setup screen. Pick a username and password; this becomes the one admin
   account.
4. In the admin area, add a project, add a category to it, add a page,
   write some Markdown, and hit "Published" to make it visible on the
   public site.

That's it. There is no step where you configure a Git remote, because there
doesn't have to be one: on first start DocuWaves initialises a Git repository
at `CONTENT_REPO_PATH` (`/data/content-repo`, inside the volume
`docker-compose.yml` already mounts) and every one of those actions is a real
commit in it, authored by whoever made it. `cp .env.example .env` if you want
to change anything at all — every setting in it is optional.

**What you get with no remote:** everything except a copy somewhere else.
Full page history, diffs, restoring an old version, attribution, the content
being plain Markdown files you can read and edit outside the app, and a
database that is only a rebuildable index over them.

**What you don't get:** anywhere for a community to send a pull request from,
and any copy of your documentation outside this server. **On a local-only
instance the data volume is the backup** — `./data` holds the repository and
nothing mirrors it. Back that directory up (or `git clone` it somewhere, or
add a remote as below) the way you would any other data you'd miss.

### Adding a Git remote later

Nothing is lost by starting local. When you want the docs on GitHub/GitLab/
Forgejo/Gitea/anything that speaks Git:

1. Create an **empty** repository there.
2. In `.env`, set `CONTENT_REPO_URL` to it, plus either `CONTENT_REPO_TOKEN`
   (for an `https://` remote — e.g. a GitHub fine-grained PAT scoped to that
   one repo, Contents: Read and write) or `CONTENT_REPO_SSH_KEY` (for a
   `git@`/`ssh://` one — a deploy key with write access). See `.env.example`
   for both forms.
3. `docker compose up -d` to restart it.

On that start, the history you already have is **pushed to the new remote in
full** — every commit, from the first page you wrote. It is not squashed into
an import and the local repository is not re-cloned over. From then on the
instance behaves exactly as one that was configured with a remote on day one:
saves push, merged pull requests are pulled back in on a timer, and the admin
area's "Sync now" fetches immediately.

Removing `CONTENT_REPO_URL` again is just as safe: the instance goes back to
local mode with all of its history, and the `origin` entry is dropped from
the repository's config (which also takes the stored push token with it).

**If the remote is not empty and its history is unrelated to yours** — a
different repo, or one somebody else already put content in — DocuWaves
**does nothing** and says so. It won't merge them (merging unrelated
histories invents a tree neither side wrote), won't force-push over the
remote, and won't re-clone over your local content. The instance keeps
running exactly as a local one, every save still commits, and the admin
area's status bar carries the reason and the two ways out: point
`CONTENT_REPO_URL` at an empty repository instead (your history is then
pushed to it on the next restart), or — if the remote's content is the one
you want to keep — delete `./data/content-repo` so it is cloned fresh, which
discards what is in it. Whichever you choose, you choose it; nothing here
decides it for you.

## Content repo structure

This is the on-disk convention DocuWaves reads and writes (and the shape a
community contributor's pull request should follow):

```
content/
  _site.yml               <- this instance's branding (optional)
  _site/                  <- the images it points at
    logo.png
  <project-slug>/
    _project.yml
    assets/
      <image-file>
    <category-slug>/
      _category.yml
      <page-slug>.md            <- the default language
      <page-slug>.<lang>.md     <- the same page in another language
      <another-page-slug>.md
    <another-category-slug>/
      _category.yml
      ...
  <another-project-slug>/
    ...
```

A project that has frozen a documentation version has **one extra directory
level** between itself and its categories — see "Documentation versions"
below. Every project starts without it and keeps working without it forever.

Names starting with an underscore directly inside `content/` are reserved
for DocuWaves itself and are never read as a project — `_site/` can't turn
into a phantom project tile on the homepage.

`_project.yml`:

```yaml
name: My Project
icon: 🚀
color: "#5b8def"
image: assets/cover.png     # optional cover for the homepage tile
description: A short one-line description shown on the homepage tile.
order: 0
```

`_category.yml`:

```yaml
name: Getting Started
icon: 📘
image: ../assets/getting-started.png    # optional cover for the tile
order: 0
```

`image` is optional in both, and everything else works exactly as it always
has without it — see "Tile cover images" below for the path rules and what
happens when one doesn't resolve.

A page's `.md` file — YAML frontmatter, then the Markdown body:

```markdown
---
title: Installation
order: 0
published: true
---

# Installation

Write your page content here, normal GitHub-flavored Markdown.
```

`order` (on projects, categories, and pages) controls display order —
lower first. `published: false` (or omitting the field) keeps a page out of
the public site entirely, even if it's merged to the content repo's default
branch; only DocuWaves' own "Publish" toggle (or hand-editing the file)
changes that.

Two optional keys, written together or not at all, hold a page's **review
note**:

```markdown
---
title: Installation
order: 0
published: true
reviewed_by: Alex Winter
reviewed_at: "2026-09-04"
---
```

It renders as one quiet line under the page ("Reviewed by Alex Winter on 4
September 2026") and is set from the editor. It is a **note, not a
signature**: it identifies nobody, proves nothing, and carries no legal or
regulatory weight. DocuWaves removes it automatically the next time the
page's body is edited, so a note that is present always refers to the words
currently on the page. Like `published`, it is per language.

Slugs (the folder/file names themselves) become part of each page's URL, so
keep them stable once published — renaming a project/category/page's name
in the admin editor changes its slug (and therefore moves the file) too.

### Multiple languages

Entirely optional, and off until you switch it on: **a content repo with no
`languages:` in `_site.yml` behaves exactly as it always has** — one
language, no URL prefix, no switcher, no per-language fields anywhere in
the admin UI, and every file stays where it is. Nothing below needs doing
to keep an existing install working.

To offer the docs in more than one language, list them in
`content/_site.yml`, in order — **the first one is the default**:

```yaml
languages: [de, en]
```

That's the whole switch. Three things follow from it:

**1. A page's language is in its filename.** `<page-slug>.<lang>.md`, with
a two-letter code:

```
content/cachepanel/erste-schritte/
  _category.yml
  installation.de.md
  installation.en.md
  erweitert.de.md        <- German only; the missing English is visible at a glance
```

The **slug is the same in all of them** (`installation`), because these are
one page in two languages, not two pages: a reader who switches language
stays on the page they were reading. A plain `<page-slug>.md` with no code
means the default language — so the existing files of a repo that only just
added `languages:` are simply read as German (in the example above), in
place. Nothing is moved or rewritten, and a page can keep that name
forever; the admin editor only spells the code out on files it creates
from now on.

A code is only recognized as a language when it's one you configured, so a
file named `release.v2.md` keeps the slug `release.v2` and doesn't become a
Venda translation of `release`.

**2. Names can be per language.** `name` and `description` in
`_project.yml`, `name` in `_category.yml`, and `name` / `tagline` /
`footer_text` in `_site.yml` each accept **either** a plain string (applies
to every language, exactly as before) **or** a mapping:

```yaml
name:
  de: Erste Schritte
  en: Getting Started
```

A language missing from the mapping falls back to the default language's
value. Both forms are valid at the same time in the same repo — translate
the two names that matter and leave the rest as plain strings.

**3. The language is in the URL**, as a path prefix:

```
/de/p/cachepanel/pages/installation
/en/p/cachepanel/pages/installation
```

An unprefixed URL (every link that was ever shared before you added a
second language) redirects to the default language, so nothing breaks.

**A missing translation is never a dead end.** If a page has no version in
the language being read, the default language's version is served —
`200`, not `404` — with an unobtrusive notice above it saying so ("This
page has not been translated yet — showing the German version"). In the
sidebar and in category listings, such a page is listed normally and marked
with a small muted language code after its title, so the language it opens
in isn't a surprise. **Search stays in one language:** searching in English
returns the English pages, plus the pages that exist *only* in the default
language — never a page and its own translation as two hits.

In the admin editor, a page gets one tab per configured language. A tab for
a language the page doesn't exist in yet opens an empty editor and saves as
`<slug>.<lang>.md` under that same slug — creating a translation, never a
new page. Only the **default language's** title steers the slug, so
renaming a translation can't move the page's URL out from under anyone.
Deleting a page deletes all of its translations; to remove just one, delete
that file in the content repo.

The reader's *interface* language (button labels) is a separate thing they
pick for themselves — but on a multi-language instance it follows whatever
content language they're reading in, for the languages the interface has
translations for.

### Documentation versions

Entirely optional, like languages, and off until you ask for it: **a project
with no `_versions.yml` has its categories and `assets/` directly under the
project directory and behaves exactly as it always has** — no `current/`, no
version in its URLs, no switcher. Nothing below needs doing to keep an
existing project working, and DocuWaves never creates the version level on
its own.

A version is a **frozen snapshot directory**, not a git branch:

```
content/
  cachepanel/
    _project.yml
    _versions.yml         <- which versions exist, which one readers get by default
    current/              <- the working version; this is what the editor writes
      assets/
      getting-started/
        _category.yml
        installation.de.md
    v2.0/                 <- frozen at release; byte-identical copy of current/ at that moment
      assets/
      getting-started/
        ...
```

**Why a copy and not a branch.** A released version of the docs has to keep
saying what it said on release day while the current one is edited every
week — and a branch says the opposite: it's a line of development you merge,
rebase and eventually delete, and reading an old one means checking it out,
which one working clone can only do for one version at a time. DocuWaves
serves every version at once out of a single checkout, and a contributor's
pull request has to be able to touch `v2.0` and `current` in the same diff.
So duplication is the point: `v2.0/` is bytes nothing will ever rewrite. The
cost is disk (Markdown files — next to nothing), and the payoff is that
"what did 2.0 say?" is answered by looking in a directory.

`_versions.yml`:

```yaml
current_label: Current      # what the working version is called in the switcher
default: current            # which version an unprefixed URL shows
versions:                   # frozen ones, newest first
  - id: v2.0
    label: "2.0"
    released: 2026-08-01
```

**The first freeze moves your content for you, in one commit.** In the admin
area, open a project, click **Versions**, give the version an id (`v2.0` —
it becomes the directory name and the URL segment) and a label (`2.0` — what
the switcher shows). The confirmation names exactly what is about to happen
before it happens. On a project's *first* freeze that includes the
migration: the project's categories and `assets/` move into `current/`, then
`current/` is copied to `v2.0/`, then `_versions.yml` is written — all as a
single commit, so the repo's history never has a state where the project is
in neither shape. You never move a file by hand.

**`assets/` moves with the version**, deliberately: a screenshot belongs to
the version it documents, so 2.0's install page keeps showing 2.0's install
screen. This does **not** rewrite any page: a page still sits exactly one
directory above `assets/` afterwards
(`<project>/<version>/<category>/<page>.md` next to
`<project>/<version>/assets/`), so every `![](../assets/x.png)` in the repo
keeps resolving — inside DocuWaves and in GitHub's own file preview alike.

**The version is in the URL, and the default one isn't:**

```
/de/p/cachepanel/pages/installation          <- the default version (current)
/de/p/cachepanel/v2.0/pages/installation     <- the frozen 2.0
```

Every link that was ever shared before the project was versioned still points
at exactly the same page. A version switcher sits next to the language
switcher; switching keeps the reader on the page they're on when the target
version has it, and lands on that version's home when it doesn't — never a
dead end. Reading a frozen version shows an unobtrusive line above the page
("You are reading the documentation for 2.0. The current version is
Current.") with a link across; it is not dismissible, because which version
you're reading is a permanent property of the page rather than a
notification. **Search covers only the version being read** — from inside
`v2.0` you search `v2.0`; from the home page you search each project's
default version, so one page never comes back once per release.

**Frozen versions are read-only in the admin UI.** You can select one and
read it, and every control that would change it is gone, with the reason
said out loud. Frozen means frozen: someone who genuinely must correct an old
page edits the file under `content/<project>/<version>/` in the content repo,
where it's reviewable like any other contribution. The API refuses such a
write with a `403` and the same explanation, so it can't be reached another
way either.

**Deleting a version** (the button next to it under **Versions**) removes
that directory and its `_versions.yml` entry in one commit; the confirmation
names the directory that will go. `current` can never be deleted — it isn't a
snapshot, it's the project's content. Deleting the last frozen version leaves
the project with just `current/`, which reads exactly like an unversioned
project rather than moving every file back up a level and breaking every link
a second time.

Version ids are checked, not guessed at: lowercase letters, digits, dots,
dashes and underscores, starting with a letter or digit (so `v2.0` keeps its
dot — this is deliberately not the slugifier the rest of the app uses, which
would turn it into `v2-0`). `current`, `assets`, `c` and `pages` are refused
because they'd collide with a fixed part of a URL or with the version's own
assets folder, an id starting with `_` or `.` is refused rather than
repaired, and so is one the project already has.

Versions and languages compose: a frozen version keeps whatever translations
existed at the moment it was frozen.

### Page history

Every page is a file in a Git repository and every save is a commit, so a
complete, attributed history of every page already exists. DocuWaves surfaces
it rather than keeping a second one of its own: there is no revisions table,
nothing to prune, and `git log` in the content repo is the same answer the app
gives.

In the editor, a page has a **History** tab beside Markdown and Preview. It
lists the commits that touched this page's file — short sha, author, date and
commit message, newest first — and selecting one shows what the page said then
plus a coloured diff of what that commit changed. The history **follows
renames**: renaming a page moves its file, and the entry that did it says
which name it came from, rather than the log appearing to start over.

It is the history of the **language currently open**. A page's translations
are separate files (`installation.de.md`, `installation.en.md`), so they have
separate histories; the panel names the file it is showing.

**Restore** writes an older version's title and Markdown back as a **new
commit on top**. Nothing is rewritten, reverted or deleted — the version being
replaced stays in the log, and undoing a restore is the same button again on
the commit above it. Three things deliberately stay as they are: the page's
position, whether it is published (that's a decision about what readers should
see now, not text from the past), and its address — the slug doesn't change,
so links keep working. A frozen documentation version refuses a restore like
any other write; its history stays fully readable.

Who changed what, why, and the diffs are **admin-only**. The content repo is
usually private and its commit messages and author names are its internal
record, so the public site shows one line and nothing else:

> Last updated: 4 March 2025

That date comes from Git, not from the database. The database is a rebuildable
index (see the top of this README) — its `updated_at` moves whenever the index
is rebuilt, which would tell a reader the page changed on a day nothing about
it did. A page with no committed file, or an instance with no content repo
configured, simply has no such line.

### Unsaved work

Text in the editor that has not been saved yet is kept in the browser, so
closing the tab, reloading, navigating away by accident, a crash, or a
session that expired halfway through a long page no longer costs the page.
It is written a moment after you stop typing (not on every keystroke), and
it is a **local scratch copy only**: nothing is uploaded, nothing is
committed, and no reader ever sees it. The content repo stays the only place
documentation is stored.

Reopening a page that has one **offers** it, with the time it was made, next
to an equally prominent way to throw it away — the editor still shows what
the content repo has until you say otherwise. Silently preferring the local
copy is exactly how a colleague's afternoon gets overwritten.

Which brings up the case worth stating plainly: **a draft is not
automatically the newer text.** Someone else may have edited the page since,
or you may have saved it from another browser. DocuWaves notices (it records
which server text the draft was written on top of) and says so, in those
words — "restoring replaces the newer text with your older draft" — instead
of offering a cheerful restore.

A draft is kept per project, page, language and documentation version — the
same four things that pick out one file in the content repo — so a page's
German and English tabs keep their own, and switching language tabs with
unsaved changes now keeps the text rather than discarding it. Saving clears
it, discarding clears it, and anything left over expires after 14 days.
Browsers that refuse storage entirely (a private window, a full quota, site
data blocked) simply get no drafts; the editor works exactly as it did
before this existed.

### Diagrams

A fenced code block tagged `mermaid` is rendered as a diagram instead of as
code:

````markdown
```mermaid
graph TD
  A[Browser] --> B[DocuWaves]
  B --> C[(Git repo)]
```
````

That is the whole of it — nothing to install, nothing to upload, no
`image:` to keep pointing at the right file. The diagram is
[Mermaid](https://mermaid.js.org) syntax, so flowcharts, sequence diagrams,
state machines, ER diagrams, Gantt charts, class diagrams and the rest all
work; Mermaid's own documentation is the reference for what you can write
inside the block.

**Why a diagram and not a screenshot of one.** It stays in the `.md` file, so
it diffs line by line in a pull request the way the prose does, it can't drift
out of date while the picture in `assets/` stays as it was, and it needs no
binary in the repo. It also renders on GitHub, Gitea and Forgejo, which draw
` ```mermaid ` blocks in their own file previews — the same file, readable in
both places, which is the same reason images are written as relative paths.

**It renders in the editor's Preview tab too**, exactly as it will on the
published page — same component, no separate preview mode to fall out of
step with the real thing.

**When the syntax is wrong**, which is most of the time while you are still
typing one, the page does not break. That block shows the Mermaid source as
a plain code block, and underneath it:

> This diagram could not be drawn -- check the Mermaid syntax.
> `Parse error on line 2: ... Expecting 'SQE', 'DOUBLECIRCLEEND', ...`

— Mermaid's own message, which names the line. Everything else on the page
(other diagrams included) renders normally: one broken diagram is one broken
diagram, never a blank page.

**The copy button stays** on a diagram block, and copies the Mermaid *source*
rather than the drawing. Copying the source is what someone actually wants
from a diagram in someone else's docs — to paste it into their own page and
change three lines — and there is no way to reach it otherwise, since the
rendered diagram has replaced the code block it came from.

**Light and dark** are both handled: the diagram is drawn in whichever
palette the reader is on and is redrawn when they flip the switch, without a
reload. A wide diagram keeps its natural size and scrolls inside its own
frame, like a wide table or a long line of code — it never widens the page.

**On page weight.** Mermaid is a large library, so it is loaded only when a
page actually contains a diagram: it sits in separate bundle chunks that a
reader on a page without one never downloads (the shared bundle grows by
about 4 kB for the code that decides this). It is bundled with the app and
never fetched from a CDN — a DocuWaves on a LAN with no route to the
internet draws its diagrams exactly like one with.

### Images

Images live in the content repo alongside the Markdown that uses them, in
the project's own `assets/` folder (inside the version directory, once the
project has versions — see above), and are referenced with a **normal
relative Markdown path**:

```markdown
![Dashboard](../assets/dashboard.png)
```

One `..` because a page sits one directory deeper (`<category-slug>/`) than
`assets/` — which stays true in a versioned project, where both moved down a
level together. Relative rather than a rewritten absolute URL on purpose: the
exact same `.md` file then renders its images correctly in GitHub's (or
Gitea's/Forgejo's) own file preview, and in anyone's local Markdown editor,
not just inside DocuWaves.

The admin editor's **Insert image** button uploads a file into that folder,
commits and pushes it like any other content change, and pastes the snippet
at the cursor; the same panel lists the project's existing images so one can
be re-used on another page without uploading it twice. Adding an image by
pull request works just as well — drop the file in `assets/` and reference
it the same way.

**Or just paste it.** A screenshot on the clipboard, pasted into the Markdown
editor (Ctrl+V), is uploaded into the same `assets/` folder, committed and
pushed like any other image, and its `![](../assets/…)` appears at the cursor
— take the screenshot, put the cursor where it belongs, paste, done.
**Dragging image files onto the editor** does exactly the same, several at
once if you like: they upload in the order you dropped them and their
snippets go in in that order, each on its own line. Dragging text around
inside the editor is untouched — only a drag actually carrying files lights
up the drop target.

A pasted image has no filename of its own (browsers hand it over as
"image.png", if anything), so DocuWaves names it after the moment it was
pasted: `pasted-2026-09-02-143205.png`. That reads as a date, sorts
chronologically in `assets/`, and keeps two screenshots taken minutes apart
apart — unlike `image.png`, `image-2.png`, `image-3.png`. Dropped files keep
their own names. Both go through exactly the rules below, and a refusal is
shown in the server's own words ("That image is 11264 KB; the limit is 10
MB.") rather than as a generic failure. A frozen documentation version offers
neither: there is nothing to upload into, and the API refuses it as well.

Rules DocuWaves enforces, on upload *and* when serving:

- **Allowed types:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.avif`,
  `.svg`. Anything else is refused on upload and 404s when requested.
- **Max 10 MB** per image.
- **The bytes are checked, not the filename** — an upload's real magic
  number has to match its extension, and an `.svg` has to parse as XML with
  no `<script>` element, no `on…=` event attribute and no `javascript:` URL
  in it. The content-type the browser declares is ignored entirely. SVGs are
  additionally served with a restrictive `Content-Security-Policy`, so even
  one committed straight into the repo by hand can't run script.
- **A relative path is resolved against the page's own directory and may
  never leave the page's project directory.** `../assets/x.png` and
  `./screenshots/x.png` are fine; `../../other-project/x.png`, an absolute
  path, or a symlink pointing out of the repo resolve to nothing (404).

Images aren't subject to the draft/published distinction — only pages are.
An image sitting in `assets/` is publicly readable as soon as it's in the
repo, whether or not any published page references it. Don't put anything in
there that isn't meant to be seen; the content repo itself is the boundary.

### Tile cover images

The homepage lists projects as tiles and a project page lists its categories
as tiles. Either can carry a real image instead of being an icon on a grey
box — optional, off until you set one, and a tile without one looks exactly
as it always did.

It's the `image:` field in `_project.yml` / `_category.yml`, and it holds a
**normal relative path from the file it appears in**, for exactly the reason
a page's image does — the same string resolves when someone browses the repo
on GitHub:

```yaml
# content/my-project/_project.yml     (sits IN the project directory)
image: assets/cover.png

# content/my-project/getting-started/_category.yml   (one directory deeper)
image: ../assets/getting-started.png
```

The file itself goes in the project's ordinary `assets/` folder, so a cover
and a screenshot on a page are the same kind of thing in the same place, and
either can be re-used as the other. Everything under "Images" above applies
to it unchanged, because it is the same code: the allowed types, the 10 MB
limit, the content-checked upload, the restrictive `Content-Security-Policy`
on an SVG, and the rule that a path may never leave the project directory.

**A cover that doesn't resolve is simply no cover.** A typo, a deleted file,
a path pointing at a `.txt`, a path climbing out of the project, a value
that isn't even a string — each one yields no URL at all, and the tile falls
back to the icon and title it has without one. Nothing 404s, nothing shows a
broken image, and the site does not care. Same rule the `logo:` in
`_site.yml` already follows.

**A category's cover belongs to its documentation version.** `assets/` lives
inside the version directory, so `v2.0`'s category resolves `../assets/x.png`
inside `v2.0/` and keeps showing what it showed at the freeze, however the
current version's images change afterwards. A path that climbs out into
another version resolves to nothing rather than crossing over.

A **project's** cover is version-independent, because `_project.yml` is: it
describes the project, not one release of it, and the homepage tile isn't
inside a version either. One consequence worth knowing: a project's *first*
freeze moves `assets/` down into `current/` without rewriting `_project.yml`
(which stays where it is), so an `image: assets/cover.png` set before that
freeze stops resolving afterwards — the tile falls back cleanly, and
re-picking the cover in the admin form stores the now-correct
`current/assets/cover.png`.

In the admin area, the project and category rows each have an **edit**
button; the form has a cover field with an upload button, a small preview
and a way to clear it. Uploading commits the file into the project's
`assets/` immediately, exactly like the editor's "Insert image" does;
clearing only drops the reference and removes the `image:` key from the YAML
— the file stays in `assets/`, where a page may well still be using it.

### Site branding

Every DocuWaves instance carries its own name, logo, colour and footer, and
that identity lives in the content repo too — `content/_site.yml`, with its
images in `content/_site/`. It's in the repo rather than in the database on
purpose: the database is only ever a rebuildable index (see above), so
branding kept there would disappear the moment it's reindexed or the volume
is lost. In the repo it's versioned, reviewable in a pull request, and comes
back with the same `git clone` that restores every page.

The practical consequence: **branding is per instance, automatically.** One
deployment pointed at a company's docs repo and another pointed at a tool's
own docs repo look completely different, without either needing its own
build, image or environment variable.

`_site.yml` — every field is optional, and so is the file itself:

```yaml
languages: [de, en]                   # optional; omit for a single-language site
name: SyntaxLab Docs                  # header, and the browser tab title
tagline: Documentation for every…     # one line under the name on the home page
logo: logo.png                        # a file in _site/; omit for text only
logo_dark: logo-white.png             # optional, used in dark mode
favicon: favicon.png                  # optional
accent: "#00d4d5"                     # accent colour, #rgb or #rrggbb
footer_text: © 2026 SyntaxLab         # optional
footer_links:                         # optional
  - label: Imprint
    url: https://example.com/imprint
```

What each field does:

| Field | Default when absent |
|---|---|
| `languages` | Single-language: no URL prefix, no switcher, no per-language fields (see "Multiple languages") |
| `name` | `DocuWaves`. Shown in the header and used for the tab title — a page reads `<page title> · <name>`, the home page just `<name>` |
| `tagline` | The generic "choose a project" line on the home page |
| `logo` / `logo_dark` | No image; the name renders as text. `logo_dark` falls back to `logo`, so one file works for both modes |
| `favicon` | The shipped DocuWaves icon |
| `accent` | The built-in accent (which is deliberately a different value in light and dark mode) |
| `footer_text` / `footer_links` | No footer at all |

Edit it in the admin area under **Branding** — name, tagline, a colour
picker, footer text, footer link rows and upload buttons for the three
images, with a live preview of the header. Saving writes `_site.yml`,
commits and pushes it like any other content change. Hand-editing the file
in the repo (or in a pull request) works just as well. `name`, `tagline`
and `footer_text` get one input per language once `languages:` names more
than one; `languages` itself is shown there but only editable in the file,
since it decides how every page file in the repo is named.

The images in `_site/` follow exactly the same rules as a project's images
(allowed types, 10 MB, content checked against the extension, SVGs screened
and served with a restrictive CSP, no path escaping the folder) — it's the
same code path, with `_site` in the place of a project slug.

Nothing in this file can take the site down. A missing file, an empty one,
broken YAML, a field holding the wrong type, a key DocuWaves doesn't know,
a colour that isn't a colour, a `javascript:` footer link, a logo naming a
file that isn't there — each one falls back to its default (and the bad
value is logged), rather than erroring the public site over a typo.

## Search engines and link previews

The reader-facing site is a single-page app, which used to mean the server
answered every URL with the same shell: one title for the whole site, no
description anywhere. Search engines saw one page, and pasting a link into
Discord or Slack produced a card that said only the site's name — those
crawlers run no JavaScript at all, so whatever React would have filled in
never existed for them.

So the shell is no longer the same for every URL. When DocuWaves answers a
public documentation URL it writes that page's metadata into the `<head>`
first: `<title>`, a description taken from the page's own first paragraph of
prose, Open Graph and Twitter card tags, `<link rel="canonical">`,
`hreflang` alternates on a multilingual instance, and JSON-LD (`TechArticle`
plus a breadcrumb trail). Nothing about the app changes — the SPA still
renders and still updates the tab title as you click around; this is simply
the correct first answer, which is the only answer a crawler ever gets.

Three things it deliberately does **not** do:

- **A draft is still invisible.** Every lookup goes through the same
  published-only path the public API uses, so an unpublished page produces
  the site's default metadata and nothing else — no title, no snippet of its
  text, and no entry in the sitemap.
- **It doesn't claim what it doesn't know.** The structured data carries a
  `dateModified` (the content repo's own log, the same date the page's "last
  updated" line shows, and a date without a time) and no author and no
  publication date, because neither of those is a thing this app actually
  knows.
- **It costs nothing where there is nothing to say.** `/admin` is served
  exactly as before and performs no lookup at all; the home page and unknown
  URLs read only the already-cached `_site.yml`. Only a real reading URL
  touches the database, and it runs the same handful of queries the page's
  own API call is about to run anyway.

### Old versions don't compete with the current one

A frozen version's page is a near-duplicate of the current one: same title,
same topic, mostly the same words. Left alone, they compete, and the winner
is decided by age and inbound links — which is exactly how somebody
searching for your install guide ends up reading the one for a release from
two years ago.

- A page in a frozen version whose **current version has the same page**
  points its canonical there. One address, and every signal the old URL
  earned is credited to the page a reader actually wants.
- A page in a frozen version with **no equivalent** in the current one — a
  section that no longer exists — has nothing to point at, so it is marked
  `noindex, follow` instead: out of the index, still crawled, its links
  still followed.
- Never both. A canonical pointing elsewhere *and* a `noindex` is the one
  combination that misfires, because the `noindex` can be taken to apply to
  the page the canonical names, which would drop the current page from
  search.

Either way the old docs stay completely readable, linkable and switchable-to
in the version switcher. They are just not what a search result should be.
The same rule applies one level up: a frozen version's category and project
pages point at the current version's, or are `noindex` when that version
doesn't have them.

### `/sitemap.xml` and `/robots.txt`

`GET /sitemap.xml` lists every published page, in every configured content
language, for each project's **default version only** (every other version
was just told not to compete, so listing it would be inviting exactly what
the canonical prevents) — plus the pages readers navigate through: the home
page, each project's landing page and each category that has something
published in it. Each entry carries a `lastmod` taken from the content
repo's git log: the same source, and the same date-without-a-time, as the
"last updated" line at the bottom of a page.

`GET /robots.txt` allows the documentation, keeps crawlers out of `/admin`
and `/api/`, and points at the sitemap at this instance's real public
address. The search page and the 404 page are deliberately *not* disallowed
there: they say `noindex` in their own head, and a crawler has to be allowed
to fetch a page to find that out.

Both work on an instance with no content at all — you get a valid document
with the home page in it.

### Getting the address right

Every absolute URL above (canonical, `og:url`, the sitemap, the `Sitemap:`
line in `robots.txt`) has to be the address *readers* use, not the one the
container sees. DocuWaves works it out from `X-Forwarded-Proto` and
`X-Forwarded-Host` (the image already runs uvicorn with `--proxy-headers`),
falling back to the request's own scheme and `Host` — which is right for an
ordinary reverse proxy and right for a direct hit on a LAN.

Set **`PUBLIC_BASE_URL`** (e.g. `https://docs.example.com`) if your proxy
doesn't forward those headers, or if the site answers at several addresses
and exactly one of them is the canonical one. It overrides the lot.

If you're not sure it's right, ask it:

```
curl -s https://docs.example.com/robots.txt | tail -1
```

That last line is the same base URL every canonical tag on the site is built
from. If it says `http://` or names an internal host, set `PUBLIC_BASE_URL`.

## Optional: PostgreSQL

If you'd rather run a real database for the search/browse index (e.g. you
already run Postgres for other services and want everything backed up the
same way — remember this holds no content of its own, only what's already
safely in the content repo):

1. In `.env`, set `DATABASE_URL=postgresql://docuwaves:changeme@postgres:5432/docuwaves`
   (change the password to match `POSTGRES_PASSWORD` below).
2. `docker compose --profile postgres up -d --build`

Every future `docker compose` command that should also (re)start Postgres
needs the same `--profile postgres` flag.

## Optional: single sign-on (OIDC)

DocuWaves speaks standard OpenID Connect, so it works with Authentik,
Keycloak, Authelia, Zitadel, or anything else that implements the spec.

In your identity provider, create an OAuth2/OpenID application with:

- **Redirect URI:** `https://<your-docuwaves-domain>/api/auth/oidc/callback`
  (exact path, only the domain changes)
- A real **signing key** configured for the provider — without one, most
  providers' JWKS endpoint returns no signing keys at all, and DocuWaves
  will refuse to trust tokens it can't verify (fails with a clear error
  rather than silently accepting an unsigned token).

Then, in DocuWaves' `.env`:

```
OIDC_ISSUER_URL=https://your-idp.example.com/application/o/docuwaves/
OIDC_CLIENT_ID=<client id from your provider>
OIDC_CLIENT_SECRET=<client secret from your provider>
OIDC_PROVIDER_NAME=authentik
```

`OIDC_ISSUER_URL` is the base URL DocuWaves fetches
`{OIDC_ISSUER_URL}/.well-known/openid-configuration` from to find the
authorization/token/JWKS endpoints itself — you don't need to look those
up individually. `OIDC_PROVIDER_NAME` only controls the login button's
label ("Sign in with authentik"); it's optional.

Restart the container (`docker compose up -d --build`) and a login button
appears on the login page alongside the password form — the password path
stays available regardless, SSO is additive, not a replacement.

**First login on a brand-new instance:** if no admin account exists yet, the
first successful SSO login creates one automatically, using your SSO
username, and skips the setup screen entirely. On an already-configured
instance, the SSO username must exactly match the existing admin account's
username, or the login is rejected — SSO authenticates *who* you are, it
never grants access on its own.

## AI assistants: API tokens and the MCP endpoint

DocuWaves speaks **MCP** (Model Context Protocol), so an AI assistant can be
pointed at your documentation and actually work on it: "what does the
installation page say about Postgres?", "document the two new environment
variables", "fix every broken link in the CachePanel docs". It reads the
same pages the site serves, and — with a token that allows it — writes them
back as real commits in your content repo (local or remote, it makes no
difference here), reviewable and revertable like any other contribution.

This is not a replacement for the admin UI and not a second login. It is one
endpoint, reachable with one kind of credential, doing exactly the subset of
things a documentation assistant needs.

### 1. Create a token

Admin area → **API tokens** → name it, pick a scope, optionally give it an
expiry date, **Create token**.

The token value (`dwt_…`) is shown **exactly once**, right there, and is
never recoverable: only a SHA-256 hash of it is stored. Lose it and you make
a new one. The list afterwards shows the name, scope, expiry, when it was
created and when it was last used — never the value.

Tokens live in DocuWaves' **database**, not in the content repo. That is the
one place this project puts state anywhere other than the repo, and
deliberately: the content repo exists to be cloned, forked and read in pull
requests, so a credential committed there would be published by the very
thing that makes the repo useful. A schema rebuild never drops them (they
sit next to the admin account, not next to the rebuildable content index).

### 2. Give the assistant the URL and the header

```
https://<your-docuwaves-domain>/api/mcp
Authorization: Bearer dwt_your_token_here
```

It is a plain JSON-RPC 2.0 endpoint over `POST`, implementing `initialize`,
`ping`, `tools/list` and `tools/call`. A quick check from a shell:

```bash
curl -s https://<your-docuwaves-domain>/api/mcp \
  -H 'Authorization: Bearer dwt_your_token_here' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

An admin session is deliberately **not** accepted on `/api/mcp`, and an API
token is deliberately **not** accepted anywhere else — every answer the
endpoint gives depends on the caller's scope, and a browser session doesn't
have one. There is no anonymous access to it, ever.

Token requests are rate limited to **120 per minute per token**: far above
any pace a real assistant sets, and low enough that an agent stuck in a
retry loop stops within a second instead of hammering `git push`.

### 3. Read scope vs. write scope

| | `read` | `write` |
|---|---|---|
| `list_projects`, `list_pages`, `read_page`, `search` | yes | yes |
| `create_page`, `update_page`, `create_category` | **no** | yes |

`write` implies `read` — there is no write-only token, because every write
tool has to look the existing content up first.

A `read` token calling a write tool gets an explicit refusal naming the
scope it has, the scope it needs and the tools it can use — not a generic
failure it will retry forever.

Both scopes can see **unpublished drafts** (that is the point: an assistant
finishing a draft has to be able to read it). Only `search` is
published-only, because it is the same index the public search box uses.

### What the assistant can do

| Tool | Scope | What it does |
|---|---|---|
| `list_projects` | read | Every project, with its slug, languages and documentation versions |
| `list_pages` | read | One project's categories and pages — one entry per language, drafts included |
| `read_page` | read | One page's full Markdown, by project + page slug, optionally in a language and a version |
| `search` | read | Full-text search across published pages, optionally scoped to one project |
| `create_page` | write | A new page in a category, slug derived from the title exactly as the editor derives it |
| `update_page` | write | Replaces a page's Markdown; optionally its title and published state |
| `create_project` | write | Create a project -- the top level everything else hangs from |
| `create_category` | write | A new category in a project |

Writes obey every rule the admin UI obeys, because they go through the same
code: only configured languages, slugs generated the same way, and **the
writable version only** — a frozen documentation version refuses a write
with the same message the admin API gives, rather than quietly redirecting
the change into `current` and letting the assistant believe it corrected a
released version.

### What this costs

Nothing, on DocuWaves' side. The MCP endpoint is a tool server: it answers an
assistant's requests about your documentation and never calls a language model
itself, so it needs no AI provider account and adds nothing to any AI bill.

What the assistant costs is between you and whoever provides it. On a
subscription plan that usage sits inside the plan; through a pay-as-you-go API
the provider bills per request. That distinction is worth knowing before you
hand out a token -- "it's free" would be true for this endpoint and wrong for
the other half of the setup.

There is deliberately no delete tool

An assistant can create pages and rewrite them. It cannot delete a page, a
category or a project, and that is a decision rather than an omission.

Creating and editing are recoverable: each one is a commit, so `git revert`
puts a page back exactly as it was, and a wrong edit is visible — the page
reads wrong. Deleting is the one operation whose damage is invisible
afterwards: nothing looks broken, something is simply gone, and nobody
notices for weeks. Set against that, the benefit of handing deletion to an
autonomous agent is close to zero. Deleting stays in the admin UI, where a
human confirms it.

### Every write is a commit, attributed to the token

A change made through a token is committed with the **author**

```
Claude (API token: notes-bot) <claude-api-token-notes-bot@local>
```

...and the committer stays `DocuWaves`, which is the honest description:
this instance committed on the assistant's behalf. So:

```bash
git log --author='API token'            # everything any assistant ever wrote
git log --author='notes-bot'            # everything this one token wrote
git blame content/cachepanel/…/x.md     # which lines came from where
git revert <sha>                        # undo one of them
```

Attribution is in the author rather than in the commit message on purpose:
the message then stays the same sentence a human edit produces (so the
history reads uniformly and a diff isn't cluttered), while `--author`,
`git blame` and every git UI's author column answer "which of my tokens
wrote this?" without anyone opening a diff.

### The security warning, plainly

**A `write` token lets whoever holds it change your documentation.** Not
"has elevated permissions" — it means the holder can rewrite a published
page, publish a draft, and add pages, on every project in this instance. It
is scoped to documentation (it cannot delete anything, cannot touch
branding, cannot create another token, cannot reach the rest of the admin
API), but within that it is real write access to what your readers see.

- Hand a write token to an assistant you are actually supervising, and read
  the commits it produces.
- Give it an **expiry date** — a token for one documentation sprint should
  stop working when the sprint ends.
- Use a **read** token whenever reading is all that is needed. It is the
  default in the form for that reason.
- **Revoke** rather than leave it lying around: revoking takes effect on the
  very next request, and the list shows `last used` so a token nothing has
  touched in months is easy to spot.
- Remember that both scopes can read unpublished drafts. If a draft would be
  a problem to share, it is a problem to hand out any token for.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CONTENT_REPO_URL` | *(empty — local repo)* | Git remote to push the content repo to. Empty means the repository at `CONTENT_REPO_PATH` is local-only, which is a complete setup — see "Adding a Git remote later" |
| `CONTENT_REPO_TOKEN` | *(empty)* | Push token, for an `https://` content repo URL |
| `CONTENT_REPO_SSH_KEY` | *(empty)* | Private deploy key, for a `git@`/`ssh://` content repo URL |
| `CONTENT_REPO_BRANCH` | `main` | Branch to track (and the branch a local repository is initialised on) |
| `CONTENT_REPO_SYNC_INTERVAL_SECONDS` | `300` | How often the background job pulls + reindexes on its own (only runs with a remote configured) |
| `CONTENT_REPO_PATH` | `/data/content-repo` | Where the repository lives (inside the container). With no remote, this **is** your content — back the volume up |
| `DATABASE_URL` | *(empty — SQLite)* | Postgres connection string; switches the search-index backend |
| `SQLITE_PATH` | `/data/docuwaves.db` | Where the SQLite index file lives (only used without `DATABASE_URL`) |
| `OIDC_ISSUER_URL` | *(empty — SSO off)* | Your identity provider's base issuer URL |
| `OIDC_CLIENT_ID` | *(empty)* | OIDC client ID |
| `OIDC_CLIENT_SECRET` | *(empty)* | OIDC client secret |
| `OIDC_PROVIDER_NAME` | `authentik` | Label shown on the SSO login button |
| `PUBLIC_BASE_URL` | *(empty — auto-detected)* | The address readers use, e.g. `https://docs.example.com`. Only needed to override what the app works out from the proxy headers — see "Search engines and link previews" |

## Development

```
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev   # proxies /api to localhost:8000
```

## License

MIT — see [LICENSE](LICENSE).
