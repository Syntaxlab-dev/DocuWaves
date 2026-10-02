---
order: 6
published: true
title: Snippets and variables
---

Write something once and use it on every page: a product name, a version
number, a port, a download link, a block of prerequisites.

## Variables

`{{name}}` anywhere in a page — code blocks included — is replaced by its
value. Values live in a `_variables.yml` next to the categories:

```yaml title="content/my-project/_variables.yml"
product: DocuWaves
port: 8091
download:
  de: https://example.com/de/download
  en: https://example.com/en/download
```

A value can differ per language, as `download` does above.

- `content/_variables.yml` holds values for **the whole site**; a project's
  own file wins over it.
- Two are built in: `{{project}}` (the project's name) and, in a versioned
  project, `{{version}}` — the label of the version being read, so a frozen
  2.0 keeps saying 2.0.
- A name that is not defined is left exactly as written.
- `${{ … }}` is never touched, so GitHub Actions, Helm or Jinja examples
  stay intact. To show the braces themselves, write `\{{name}}`.

## Snippets

A snippet is a Markdown file in `_snippets/` next to the categories (or
`content/_snippets/` for the whole site), included on a line of its own:

```markdown
<!-- snippet: prerequisites -->
```

That line is replaced by `_snippets/prerequisites.md` — or by
`prerequisites.de.md` first, when the reader reads German on a multilingual
site. Snippets can use variables and include other snippets. On GitHub the
comment is invisible.

An unknown snippet is left out for readers and shown as a warning in the
editor's preview, so a renamed file does not silently empty a page.

## Managing them in the admin area

**Snippets & variables**, next to **Versions** above a project, edits them
for the version you are looking at — or, with the switch at the top, for the
whole site. Every save is a commit, like any other edit. Variables are
checked before they are written (a value YAML would read as `true`, a name
with a space in it). A frozen version's snippets are shown but cannot be
edited, like the rest of it.

## Where they are filled in

For **readers**, everywhere they read: the page, preview links, search
result snippets, the page description, the chat, webhooks and the link
check. Variables and snippets are frozen with a version like the rest of its
content.

The files, the editor and the MCP read tool keep the source — `{{port}}`,
not `8091` — because that is what gets edited.

> [!NOTE]
> Search matches a page's **own** text. A word that only appears inside a
> snippet or a variable does not find the page.
