"""docuwaves-lint against every case in spec/conformance/ (spec section 10)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docuwaves_lint import LEVELS, lint, main

CASES = Path(__file__).resolve().parents[2] / "spec" / "conformance"
CASE_DIRS = sorted(p for p in CASES.iterdir() if (p / "content").is_dir())


def test_there_are_cases():
    assert len(CASE_DIRS) >= 9


@pytest.mark.parametrize("case", CASE_DIRS, ids=lambda p: p.name)
def test_case(case):
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    result = lint(case / "content")
    assert result["model"] == expected["model"]
    got = {(d["code"], d["path"]) for d in result["diagnostics"]}
    assert got == {(d["code"], d["path"]) for d in expected["diagnostics"]}


@pytest.mark.parametrize("case", CASE_DIRS, ids=lambda p: p.name)
def test_every_case_has_a_readme(case):
    assert (case / "README.md").is_file()


def test_every_code_is_in_the_spec():
    spec = (CASES.parent / "content-format.md").read_text(encoding="utf-8")
    for code in LEVELS:
        assert f"`{code}`" in spec, code


def test_every_code_is_exercised():
    seen = set()
    for case in CASE_DIRS:
        seen |= {d["code"] for d in json.loads((case / "expected.json").read_text())["diagnostics"]}
    assert seen == set(LEVELS)


def test_exit_code(capsys):
    assert main([str(CASES / "01-minimal" / "content")]) == 0
    assert main([str(CASES / "04-category-parents" / "content")]) == 1
    assert main([str(CASES / "08-redirects" / "content")]) == 0  # warnings only
    capsys.readouterr()


def test_the_projects_own_docs_are_clean(tmp_path):
    """docs/ is served as one project; read that way it gives no diagnostics."""
    import shutil

    project = tmp_path / "content" / "docuwaves"
    shutil.copytree(CASES.parents[1] / "docs", project)
    (project / "_project.yml").write_text("name: DocuWaves\n", encoding="utf-8")
    result = lint(tmp_path / "content")
    assert result["diagnostics"] == []
    assert len(result["model"]["projects"][0]["pages"]) > 20
