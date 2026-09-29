"""Snippets and variables: filled in for readers, left alone where they mean
something else, and frozen along with the version they belong to."""
import pytest
from fastapi import HTTPException

from app.routers import admin_content
from app.services import content_versions, site_languages, snippets
from app.settings import settings


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "content_repo_path", str(tmp_path))
    monkeypatch.setattr(site_languages, "default_language", lambda: "de")
    content = tmp_path / "content"
    project = content / "demo"
    (project / "_snippets").mkdir(parents=True)
    (content / "_snippets").mkdir(parents=True)
    (project / "_project.yml").write_text("name: Demo\n", encoding="utf-8")

    def write(path: str, text: str):
        target = content / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    return write


def resolve(markdown: str, version: str = "", language: str = "", **kw) -> str:
    return snippets.resolve(markdown, "demo", version, language, **kw)


class TestVariables:
    def test_project_variables_and_the_built_in_project_name(self, repo):
        repo("demo/_variables.yml", "product: DocuWaves\nport: 8091\n")
        assert resolve("{{product}} ({{ project }}) listens on {{port}}.") == "DocuWaves (Demo) listens on 8091."

    def test_the_project_overrides_the_site(self, repo):
        repo("_variables.yml", "support: site@example.com\nproduct: Site\n")
        repo("demo/_variables.yml", "product: DocuWaves\n")
        assert resolve("{{product}} / {{support}}") == "DocuWaves / site@example.com"

    def test_a_value_per_language(self, repo):
        repo("demo/_variables.yml", "greeting:\n  de: Hallo\n  en: Hello\n")
        assert resolve("{{greeting}}", language="en") == "Hello"
        assert resolve("{{greeting}}", language="de") == "Hallo"

    def test_unknown_names_and_other_templating_are_left_alone(self, repo):
        repo("demo/_variables.yml", "version: 1.0\n")
        text = "run: echo ${{ version }} and {{ secrets.TOKEN }} and {{unknown}}"
        assert resolve(text) == text

    def test_a_backslash_writes_the_braces(self, repo):
        repo("demo/_variables.yml", "product: DocuWaves\n")
        assert resolve("Write \\{{product}} to get {{product}}.") == "Write {{product}} to get DocuWaves."

    def test_broken_yaml_costs_the_variables_not_the_page(self, repo):
        repo("demo/_variables.yml", "product: [unclosed\n")
        assert resolve("Hi {{product}}") == "Hi {{product}}"


class TestSnippets:
    def test_a_snippet_is_included_with_its_variables(self, repo):
        repo("demo/_variables.yml", "product: DocuWaves\n")
        repo("demo/_snippets/prereq.md", "---\ntitle: ignored\n---\nYou need {{product}}.\n")
        assert resolve("Intro\n\n<!-- snippet: prereq -->\n\nMore") == "Intro\n\nYou need DocuWaves.\n\nMore"

    def test_project_before_site_and_language_before_plain(self, repo):
        repo("_snippets/footer.md", "site footer")
        repo("_snippets/support.md", "site support")
        repo("demo/_snippets/support.md", "project support")
        repo("demo/_snippets/support.en.md", "project support (en)")
        assert resolve("<!-- snippet: footer -->") == "site footer"
        assert resolve("<!-- snippet: support -->", language="de") == "project support"
        assert resolve("<!-- snippet: support -->", language="en") == "project support (en)"

    def test_inside_a_code_block_it_is_code(self, repo):
        repo("demo/_snippets/x.md", "EXPANDED")
        text = "```markdown\n<!-- snippet: x -->\n```"
        assert resolve(text) == text

    def test_snippets_nest_but_a_loop_is_cut_off(self, repo):
        repo("demo/_snippets/a.md", "A\n<!-- snippet: b -->")
        repo("demo/_snippets/b.md", "B\n<!-- snippet: a -->")
        assert resolve("<!-- snippet: a -->") == "A\nB"

    def test_a_missing_snippet_is_dropped_for_readers_and_flagged_in_the_preview(self, repo):
        assert resolve("x\n<!-- snippet: nope -->\ny") == "x\ny"
        assert "nicht gefunden" in resolve("<!-- snippet: nope -->", mark_missing=True)

    def test_a_name_can_not_leave_the_snippets_directory(self, repo):
        repo("secret.md", "SECRET")
        assert snippets.snippet_path("demo", "", "../../secret") is None
        assert snippets.snippet_path("demo", "", "support", language="../../secret") is None


class TestVersions:
    @pytest.fixture
    def versioned(self, repo):
        repo("demo/_versions.yml", "current_label: '3.x'\ndefault: current\nversions:\n  - id: v2.0\n    label: '2.0'\n")
        repo("demo/current/_variables.yml", "download: https://example.com/3\n")
        repo("demo/v2.0/_variables.yml", "download: https://example.com/2\n")
        return repo

    def test_version_is_built_in_and_each_version_keeps_its_own_values(self, versioned):
        assert resolve("{{version}} {{download}}", version="v2.0") == "2.0 https://example.com/2"
        assert resolve("{{version}} {{download}}", version="current") == "3.x https://example.com/3"

    def test_an_unversioned_project_has_no_version_variable(self, repo):
        assert resolve("{{version}}") == "{{version}}"


def test_freezing_takes_the_snippets_and_variables_along(repo, tmp_path):
    repo("demo/_variables.yml", "product: X\n")
    repo("demo/_snippets/a.md", "A")
    repo("demo/guide/_category.yml", "name: Guide\n")
    moved = {p.name for p in content_versions._content_entries("demo")}
    assert {"_snippets", "_variables.yml", "guide"} <= moved
    assert "_project.yml" not in moved


def test_the_preview_route_accepts_only_versions_and_languages_that_exist(repo, monkeypatch):
    monkeypatch.setattr(admin_content.projects_store, "get_project_by_slug", lambda slug: {"slug": slug})
    monkeypatch.setattr(admin_content.site_languages, "languages", lambda: ["de"])
    repo("demo/_snippets/a.md", "A")
    ok = admin_content.admin_resolve_markdown(admin_content.ResolveIn(project_slug="demo", markdown="<!-- snippet: a -->"))
    assert ok == {"markdown": "A"}
    for bad in ({"version": "../.."}, {"language": "../x"}):
        with pytest.raises(HTTPException) as refused:
            admin_content.admin_resolve_markdown(admin_content.ResolveIn(project_slug="demo", markdown="", **bad))
        assert refused.value.status_code == 400
