---
order: 1
published: true
title: Tile cover images
---

The home page lists projects as tiles, and a project page lists its categories as tiles. Either can carry a real image instead of an icon on a plain box.

It is optional, off until you set one, and a tile without one looks exactly as it always did.

## Setting one

In the admin area, project and category rows each have an **Edit** button, and the form has a cover field with an upload button, a small preview, and a way to clear it.

Uploading commits the file into the project's `assets/` folder immediately, exactly like the editor's **Insert image** does. Clearing only drops the reference and removes the `image:` key from the YAML — the file stays in `assets/`, where a page may well still be using it.

## The field

`image:` in `_project.yml` or `_category.yml`, holding a **normal relative path from the file it appears in** — for the same reason a page's images are relative: the same string resolves when someone browses the repository on GitHub.

```yaml
# content/my-project/_project.yml            (sits IN the project directory)
image: assets/cover.png

# content/my-project/getting-started/_category.yml   (one directory deeper)
image: ../assets/getting-started.png
```

The file goes in the project's ordinary `assets/` folder, so a cover and a screenshot on a page are the same kind of thing in the same place, and either can be reused as the other.

Everything on [Images](/p/docuwaves/pages/images) applies unchanged, because it is the same code: the allowed types, the 10 MB limit, the contents checked against the extension, the restrictive `Content-Security-Policy` on an SVG, and the rule that a path may never leave the project directory.

## A cover that does not resolve is simply no cover

A typo, a deleted file, a path pointing at a `.txt`, a path climbing out of the project, a value that is not even a string — each yields no URL at all, and the tile falls back to the icon and title it has without one.

Nothing 404s, nothing shows a broken image, and the site does not care. It is the same rule `logo:` in `_site.yml` already follows.

The type check is load-bearing rather than fussy, incidentally. `icon:` and `color:` next to it are only ever printed, but this value is handed to the filesystem resolver — so an `image: 42` would reach `project_dir / 42` and raise, taking the public site down over one wrong line in a file anyone can send a pull request for.

## Covers and documentation versions

**A category's cover belongs to its [documentation version](/p/docuwaves/pages/after-the-freeze).** `assets/` lives inside the version directory, so `v2.0`'s category resolves `../assets/x.png` inside `v2.0/` and keeps showing what it showed at the freeze, however the current version's images change afterwards. A path that climbs out into another version resolves to nothing rather than crossing over — otherwise a frozen release's tile would change every time the current version's images did.

**A project's cover is version-independent**, because `_project.yml` is: it describes the project, not one release of it, and the home page tile is not inside a version either.

That has one consequence worth knowing. A project's *first* freeze moves `assets/` down into `current/` without rewriting `_project.yml`, so an `image: assets/cover.png` set before that freeze stops resolving afterwards. The tile falls back cleanly, and re-picking the cover in the project form stores the now-correct `current/assets/cover.png`.
