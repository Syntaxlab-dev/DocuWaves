---
order: 4
published: true
title: Tabs
---

The same step for several systems, languages or setups — one visible at a
time, instead of three near-identical sections in a row.

````markdown
<!-- tabs -->
#### macOS
```bash
brew install docuwaves
```
#### Linux
```bash
apt install docuwaves
```
<!-- /tabs -->
````

<!-- tabs -->
#### macOS
```bash
brew install docuwaves
```
#### Linux
```bash
apt install docuwaves
```
<!-- /tabs -->

## How it is read

- The first heading after `<!-- tabs -->` names the first tab.
- Every following heading **of the same level** starts the next tab.
- Everything else — deeper headings, code, callouts, lists — belongs to the
  tab it is in.
- `<!-- /tabs -->` ends the group.

On GitHub the two comments are invisible, and the page reads as one heading
per system with its steps underneath — which is how you would have written
it without tabs. Nothing about the file is DocuWaves-only.

A group that does not start with a heading, or is never closed, is shown as
ordinary text, so a typo never swallows half a page.

## What readers get

- **Their choice is remembered**, by name, in their browser, for every tab
  group on every page: pick "Linux" once and every group with a Linux tab
  shows it.
- **Printed pages show all tabs**, one after another, each under its name —
  paper has nothing to click.
- Headings inside a tab group stay out of **On this page**: they would link
  to something the reader may not be looking at.
