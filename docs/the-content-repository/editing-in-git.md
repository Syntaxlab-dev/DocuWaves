---
order: 1
published: true
title: Editing in Git
---

The browser editor is a convenience, not a gate. Every page is a file, so a text editor and `git` reach the same content with the same result.

## Working directly

```bash
git clone git@github.com:your-org/your-docs-content.git
cd your-docs-content
$EDITOR content/my-project/getting-started/installation.md
git commit -am "Fix the port number in the install guide"
git push
```

DocuWaves picks that up on its next sync — see [Syncing and conflicts](/p/docuwaves/pages/syncing-and-conflicts).

## What you can do there and not in the UI

A few things are deliberately only available as a file edit:

| Task | Why it is not a button |
|---|---|
| Correcting a page in a [frozen version](/p/docuwaves/pages/after-the-freeze) | Frozen means frozen. A correction to a released version should be reviewable like any other contribution, not a quiet in-place rewrite |
| Deleting **one** translation of a page | The Delete button removes a page and all of its translations, because they are one page. Two very similar buttons with very different consequences would be worse |
| Changing `languages:` in `_site.yml` | It decides how every page file in the repository is named and how every URL is shaped. The admin form shows it and does not let you edit it |
| Editing a version's `label` or `released` date | `_versions.yml` is written by the freeze and read back leniently; hand-edit it for anything else |

## Contributions from outside

This is the reason the content is in Git at all. Someone with no account on your instance can fork the content repository, edit a `.md` file, and open a pull request. When you merge it, DocuWaves indexes it — no import step, no copy-paste into an editor.

Tell contributors three things:

1. **Slugs are addresses.** A file's name is the page's URL. Renaming a published page breaks links to it.
2. **`published: false` really is invisible.** A merged draft is still a draft; it needs the flag flipped to appear.
3. **A page slug is unique per project, not per category.** Two categories in the same project cannot both hold `installation.md`. If that ever happens, the first one wins, the second is skipped, and the reason is listed under [Diagnostics](/p/docuwaves/pages/diagnostics) — which is the only place it shows, so a page that exists in the repository and is missing from the site is worth looking for there first.

## Rules that hold no matter who wrote the file

Everything DocuWaves enforces on upload it also enforces on the way out. A file committed by hand does not get an easier ride:

- an image with a disallowed extension answers 404, not "here you go";
- an SVG is served with a restrictive `Content-Security-Policy` whether it was uploaded or committed;
- a relative image path that climbs out of its project resolves to nothing;
- a `_versions.yml` entry whose id is not a usable directory name is ignored, and the reason is logged.

## Nothing in a YAML file can take the site down

`_site.yml`, `_project.yml`, `_category.yml` and `_versions.yml` are hand-editable files that arrive by pull request, so every one of them degrades rather than raises. A missing file, an empty file, broken YAML, a field holding the wrong type, a key DocuWaves does not know, a colour that is not a colour, a `javascript:` footer link, a logo naming a file that is not there — each falls back to its default and logs the reason.

The one thing that genuinely used to be fatal, a duplicate page slug, is now the "first one wins" rule above. One committed file must never be able to stop the application from starting.

## What to keep out of the repository

Anything secret. Images are public as soon as they are committed, drafts are readable by anyone with repository access, and the repository is the boundary — not the publish toggle. Credentials belong in `.env` and, for [API tokens](/p/docuwaves/pages/api-tokens-and-scopes), in the database, which is where DocuWaves puts them.
