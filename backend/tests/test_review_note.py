"""The review note, as it lands in a page file and comes back out.

The rule this protects: a note is two halves that only mean something
together, it is written as a STRING date, and a page nobody has reviewed
carries no trace of the feature at all. That last one is not cosmetic --
every page in the content repo is a file somebody reads in a pull request,
and two blank keys on every one of them would be this feature's only visible
effect on an instance that never uses it.
"""
import frontmatter

from app.services import content_files


def read_raw(content, project: str, category: str, slug: str) -> dict:
    """The page file's frontmatter exactly as YAML parses it -- which is not
    the same thing as what read_page() hands back, and the difference is the
    point of two of the tests below."""
    path = content.content_dir(project) / category / f"{slug}.md"
    return frontmatter.loads(path.read_text(encoding="utf-8")).metadata


class TestWithoutANote:
    def test_the_keys_are_absent_entirely(self, content):
        content.project("demo").category("demo", "guide")
        content_files.write_page("demo", "guide", "install", "Install", "Body.", 0, True)
        metadata = read_raw(content, "demo", "guide", "install")
        assert "reviewed_by" not in metadata
        assert "reviewed_at" not in metadata

    def test_reads_back_as_two_empty_strings(self, content):
        content.project("demo").category("demo", "guide")
        content_files.write_page("demo", "guide", "install", "Install", "Body.", 0, True)
        page = content_files.read_page("demo", "guide", "install")
        assert page["reviewed_by"] == ""
        assert page["reviewed_at"] == ""


class TestWithANote:
    def test_round_trips(self, content):
        content.project("demo").category("demo", "guide")
        content_files.write_page(
            "demo", "guide", "install", "Install", "Body.", 0, True,
            reviewed_by="Alex Winter", reviewed_at="2026-09-04",
        )
        page = content_files.read_page("demo", "guide", "install")
        assert page["reviewed_by"] == "Alex Winter"
        assert page["reviewed_at"] == "2026-09-04"

    def test_the_date_stays_a_string(self, content):
        """Unquoted, YAML reads 2026-09-04 back as a datetime.date, and the
        page's frontmatter would round-trip through a different type than it
        was written with -- which reaches the database layer as one."""
        content.project("demo").category("demo", "guide")
        content_files.write_page(
            "demo", "guide", "install", "Install", "Body.", 0, True,
            reviewed_by="Alex Winter", reviewed_at="2026-09-04",
        )
        assert isinstance(read_raw(content, "demo", "guide", "install")["reviewed_at"], str)

    def test_a_hand_written_yaml_date_is_still_read_as_a_string(self, content):
        """Somebody editing the repo by hand will write `reviewed_at:
        2026-09-04` without quotes, and PyYAML hands that over as a date
        object. read_page has to normalize it rather than pass the object on."""
        content.project("demo").category("demo", "guide")
        path = content.content_dir("demo") / "guide" / "install.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntitle: Install\norder: 0\npublished: true\n"
            "reviewed_by: Alex Winter\nreviewed_at: 2026-09-04\n---\n\nBody.\n",
            encoding="utf-8",
        )
        page = content_files.read_page("demo", "guide", "install")
        assert page["reviewed_at"] == "2026-09-04"
        assert isinstance(page["reviewed_at"], str)


class TestHalfANote:
    def test_a_name_without_a_date_is_written_as_no_note(self, content):
        """"Reviewed by Alex" with no date says nothing about whether the
        check is from this week or from three years ago, so it is not a note
        this app is willing to make."""
        content.project("demo").category("demo", "guide")
        content_files.write_page(
            "demo", "guide", "install", "Install", "Body.", 0, True, reviewed_by="Alex Winter",
        )
        metadata = read_raw(content, "demo", "guide", "install")
        assert "reviewed_by" not in metadata and "reviewed_at" not in metadata

    def test_a_date_without_a_name_is_written_as_no_note(self, content):
        content.project("demo").category("demo", "guide")
        content_files.write_page(
            "demo", "guide", "install", "Install", "Body.", 0, True, reviewed_at="2026-09-04",
        )
        metadata = read_raw(content, "demo", "guide", "install")
        assert "reviewed_by" not in metadata and "reviewed_at" not in metadata
