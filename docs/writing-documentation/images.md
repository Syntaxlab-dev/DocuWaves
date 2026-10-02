---
order: 6
published: true
title: Images
---

Images live in the content repository next to the Markdown that uses them, in the project's own `assets/` folder, and are referenced with a **normal relative Markdown path**:

```markdown
![The dashboard](../assets/dashboard.png)
```

One `..`, always, because a page sits one directory deeper than `assets/`:

```
content/my-project/assets/dashboard.png
content/my-project/getting-started/installation.md      <- the page
```

## Why relative and not a rewritten URL

Because the exact same `.md` file then renders its images correctly in GitHub's, Gitea's or Forgejo's own file preview, and in any local Markdown editor — not only inside DocuWaves. A rewritten absolute URL would work in one place and nowhere else, which defeats the point of keeping the content portable.

DocuWaves resolves the relative path at render time against the page's own directory and serves the file from `/api/public/assets/…`.

## Three ways to add one

- **Insert image** in the editor opens a panel: upload a file, or pick one of the project's existing images to reuse it on another page without uploading it twice.
- **Paste.** A screenshot on the clipboard, pasted into the editor with Ctrl+V, is uploaded and its `![](../assets/…)` appears at the cursor. Take the screenshot, put the cursor where the image belongs, paste.
- **Drag and drop.** Drop image files onto the editor — several at once if you like. They upload in the order you dropped them and their snippets go in in that order, each on its own line. Dragging text around inside the editor is unaffected; only a drag actually carrying files lights up the drop target.

All three do the same thing underneath: write the file into `assets/`, commit it, push it, and insert the Markdown. Adding an image by pull request works just as well — drop the file in `assets/` and reference it the same way.

A pasted image has no filename of its own (browsers hand it over as `image.png`, if anything), so it is named after the moment it was pasted:

```
pasted-2026-09-02-143205.png
```

That reads as a date, sorts chronologically in `assets/`, and keeps two screenshots taken minutes apart apart — unlike `image.png`, `image-2.png`, `image-3.png`. Dropped and uploaded files keep their own names, slugified, with a `-2` suffix if the name is taken. Nothing is ever silently overwritten.

## The rules

Enforced on upload **and** when serving, so a file committed by hand is held to the same standard as one uploaded:

- **Allowed types:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.avif`, `.svg`. Anything else is refused on upload and answers 404 when requested.
- **10 MB per image.** A refusal names the actual size: *"That image is 11264 KB; the limit is 10 MB."*
- **The bytes are checked, not the filename.** An upload's real magic number has to match its extension. The content type the browser declares is ignored entirely.
- **SVG is screened as XML.** It must parse, and it must contain no `<script>` element, no `on…=` event attribute, no `javascript:` URL, and no entity declarations. SVGs are additionally served with a restrictive `Content-Security-Policy`, so even one committed straight into the repository by hand cannot run script.
- **A path may not leave the page's project.** `../assets/x.png` and `./screenshots/x.png` are fine. `../../other-project/x.png`, an absolute path, or a symlink pointing out of the repository all resolve to nothing. Paths are compared after full resolution, so a `..` segment or a symlink cannot slip past.

## Images are not drafts

Only pages have a published state. An image sitting in `assets/` is publicly readable as soon as it is in the repository, whether or not any published page references it.

So do not put anything in there that is not meant to be seen. The content repository itself is the boundary, not the publish toggle.

## Deleting

The image panel has a delete button. It removes the file in a commit; pages still referencing it will show a broken image, which is why the confirmation says so. As with everything else here, the commit that removed it leaves it in the history.

A [frozen documentation version](/p/docuwaves/pages/after-the-freeze) has no upload at all — there is nothing to upload into, and the API refuses it as well.

## Video and audio come the same way

The uploader takes `.mp4`, `.webm`, `.ogg`, `.mp3`, `.m4a` and `.wav` as
well, and the image syntax renders them as a player. The same 10 MB limit
applies and is deliberately not raised — see [Formulas, video and
audio](/p/docuwaves/pages/formulas-video-and-audio) for why, and for the one
thing media files cannot be: a tile cover, which has to be a picture.
