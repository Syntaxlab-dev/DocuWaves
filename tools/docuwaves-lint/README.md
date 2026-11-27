# docuwaves-lint

Checks a content tree against the [DocuWaves content
format](../../spec/content-format.md), without running DocuWaves. It needs
Python 3.10 or newer and PyYAML, nothing else.

```sh
pip install pyyaml
python tools/docuwaves-lint/docuwaves_lint.py path/to/repo/content
```

It prints one line per diagnostic and exits with 1 when there is an error,
so it fits into a pre-commit hook or a CI job of a docs repository:

```
guide/start/intro.md: warning: duplicate-language (intro.en.md is used)
kb/beta/setup.md: error: duplicate-page (already in category 'alpha')
1 error(s), 1 warning(s)
```

`--json` prints what it read (the model described in
[spec/conformance/README.md](../../spec/conformance/README.md)) along with
the diagnostics.

It shares no code with the DocuWaves backend on purpose: it is a second
reader of the spec, and both are held to the cases in
[spec/conformance/](../../spec/conformance/). Its own tests:

```sh
python -m pytest tools/docuwaves-lint
```
