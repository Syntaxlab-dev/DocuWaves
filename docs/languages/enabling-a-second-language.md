---
order: 0
published: true
title: Enabling a second language
---

Multiple languages are optional and off until you switch them on. **A content repository with no `languages:` in `_site.yml` behaves as though this feature did not exist** — one language, no URL prefix, no switcher, no per-language fields anywhere in the admin area, and every file stays where it is.

## The switch

List the languages in `content/_site.yml`, in order. **The first one is the default.**

```yaml
languages: [de, en]
```

That is the whole thing. Codes are two lowercase letters (ISO 639-1); anything else in the list is dropped and logged. Twelve is the maximum — more than that is a configuration mistake rather than a use case, and each one multiplies the editor's tab strip and the header's switcher.

Restart is not required; the file is re-read when it changes.

## It is edited in the file, not in the form

The admin area's **Branding** panel shows the configured languages but will not let you change them. That is deliberate: `languages:` decides how every page file in the repository is named and how every URL is shaped, so a branding save must never be able to drop or change it. A stale browser tab posting a form from before the key existed would otherwise silently un-translate the whole instance.

Change it in the file, or by pull request.

## What happens to the files you already have

Nothing. They are not moved and not rewritten.

A page file with no language code — plain `installation.md` — means **the default language**. So on the day you add `languages: [de, en]`, every existing file is simply read as German, in place. A page can keep that name forever; only files the editor creates from then on spell the code out.

## What turns on

- **A language prefix in every reading URL**, and a switcher in the header.
- **A tab per language in the page editor.** Opening the tab for a language a page does not have yet gives you an empty editor; saving it creates the translation under the same slug.
- **Per-language values for names.** `name` and `description` in `_project.yml`, `name` in `_category.yml`, and `name`, `tagline` and `footer_text` in `_site.yml` each accept either a plain string as before, or a mapping:

  ```yaml
  name:
    de: Erste Schritte
    en: Getting Started
  ```

  Both forms are valid in the same repository at the same time. Translate the two names that matter and leave the rest as plain strings. A language missing from a mapping falls back to the default language's value.

  DocuWaves writes the plain-string form back whenever a mapping would say only one thing, so enabling `languages:` and then saving a project without translating it does not rewrite `name: My Project` into a one-key mapping nobody asked for.

## One entry is still a single-language site

`languages: [de]` does not turn on the switcher or the URL prefix — those need more than one language. What it does do is make `de` a **recognised** code, so `installation.de.md` is read as a German page called `installation` rather than as a page called `installation.de`.

That is occasionally useful on its own, and it is also why a single-language instance never mistakes a filename for a translation: with nothing configured, no suffix is a language code at all.

## Turning it off again

Remove the key. Files keep their names, and a `<slug>.<lang>.md` whose code is no longer configured is read as a page whose slug includes the code — which is almost certainly not what you want. If you mean to go back to one language, rename the files you are keeping and delete the rest, in the content repository, before removing the key.

Next: [Translations, slugs and fallback](/p/docuwaves/pages/translations-slugs-and-fallback).
