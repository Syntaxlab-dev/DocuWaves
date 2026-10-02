---
order: 4
published: true
title: Callouts and code blocks
---

Two small things that make instructions easier to follow: a coloured box for
what must not be missed, and a code block that says which file it belongs in.

## Callouts

GitHub's own syntax — so the files read exactly the same on GitHub, in a
pull request or in any editor that previews Markdown:

```markdown
> [!WARNING]
> Back up the data volume before upgrading.
```

> [!WARNING]
> Back up the data volume before upgrading.

There are five kinds, each with its own colour and a label in the reader's
language:

| Kind | Use it for |
|---|---|
| `NOTE` | Background worth knowing, but skippable |
| `TIP` | A shortcut or a better way |
| `IMPORTANT` | Something the reader needs to succeed |
| `WARNING` | Something that can go wrong if ignored |
| `CAUTION` | Something that destroys data or cannot be undone |

Everything a quote can hold works inside a callout: lists, code, links,
several paragraphs. Anywhere that does not know callouts it degrades to an
ordinary quote starting with `[!WARNING]` — still readable.

Use them sparingly. A page with a callout under every paragraph has taught
its readers to skip callouts.

## Code blocks with a file name

Add `title="…"` after the language:

````markdown
```python title="app/main.py"
def hello():
    return "world"
```
````

```python title="app/main.py"
def hello():
    return "world"
```

The file name is shown above the block, next to the language. A block
without one looks exactly as before, and every block has a **copy** button
either way.

The file name is not decoration: "add this to your config" is the sentence
that sends readers hunting for *which* config.
