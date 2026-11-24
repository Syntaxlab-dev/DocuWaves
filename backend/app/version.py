"""Which DocuWaves this is.

The image is built with DOCUWAVES_VERSION and DOCUWAVES_REVISION as build
arguments (.github/workflows/docker-publish.yml): the release number for a
tagged build ("1.0.0"), "latest" for a build of main, and the commit it was
built from. A checkout run by hand has neither and says "dev" -- which is the
truth: it is whatever is in that working tree.

Bug reports ask for this (CONTRIBUTING.md), so it is shown under
Diagnostics, returned by /health and written to the log at startup.
"""

import os

VERSION = os.environ.get("DOCUWAVES_VERSION", "").strip() or "dev"
REVISION = os.environ.get("DOCUWAVES_REVISION", "").strip()


def describe() -> str:
    """"1.0.0 (0f651bf)", "latest (a3ea774)" or "dev"."""
    return f"{VERSION} ({REVISION[:7]})" if REVISION else VERSION
