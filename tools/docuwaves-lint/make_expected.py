#!/usr/bin/env python3
"""Regenerate spec/conformance/*/expected.json from this linter.

Only for a deliberate change to the spec: review the diff of every
expected.json by hand before committing it.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docuwaves_lint import lint

CASES = Path(__file__).resolve().parents[2] / "spec" / "conformance"

for case in sorted(p for p in CASES.iterdir() if (p / "content").is_dir()):
    result = lint(case / "content")
    pairs = sorted({(d["path"], d["code"]) for d in result["diagnostics"]})
    result["diagnostics"] = [{"code": code, "path": path} for path, code in pairs]
    (case / "expected.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(case.name)
