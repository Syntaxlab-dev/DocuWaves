# Conformance cases

Each directory is one case:

- `content/` is a content tree, as section 2 of the spec describes it.
- `expected.json` is what a conforming reader gets from it.
- `README.md` says what the case is about.

## `expected.json`

```json
{
  "model": {
    "languages": ["en", "de"],
    "projects": [
      {
        "slug": "guide",
        "name": "Guide",
        "order": 0,
        "private": false,
        "review_required": false,
        "versions": [],
        "categories": [
          {"version": "", "slug": "start", "name": "Start", "order": 0, "parent": ""}
        ],
        "pages": [
          {"version": "", "category": "start", "slug": "intro", "language": "en",
           "title": "Intro", "order": 0, "published": true}
        ],
        "redirects": {"old": "intro"}
      }
    ]
  },
  "diagnostics": [
    {"code": "duplicate-language", "path": "guide/start/intro.md"}
  ]
}
```

- `languages`: the configured languages after section 4, default first.
- `projects`: every project, by slug. `name` is the text in the default
  language. `private` is `visibility: private`, `review_required` is
  `review: required`, both compared without case.
- `versions`: `[]` for a project without `_versions.yml`, otherwise
  `current` followed by the remaining frozen ids, in file order.
- `categories`: by version as listed, then slug. `version` is `""` in a
  project without versions. `parent` is `""` for a top-level category,
  including one whose parent was dropped.
- `pages`: the pages a reader keeps, by slug and then language. `language`
  is `""` when no languages are configured. A page with an empty title has
  its slug as title.
- `redirects`: the entries after trimming and dropping empty sides, by key.
- `diagnostics`: the set of `(code, path)` pairs, by path. Paths are
  relative to `content/`. The order, the count of repeats and any detail
  text are not part of the result.

A reader MAY take more from the files than the model lists (descriptions,
icons, page bodies). The cases only pin down what is listed here.

## Adding a case

Add a directory with `content/` and `README.md`, then run
`python tools/docuwaves-lint/make_expected.py` and read the new
`expected.json` line by line against the spec before you commit it. If the
spec and the file disagree, fix the linter or the spec, never only the file.
