"""Where an image path is allowed to resolve to.

The containment rules here are the security-relevant ones in this codebase:
a path out of the content repo is a file read, and the public asset endpoint
serves whatever resolve_asset() hands back.
"""
from app.services import content_assets


class TestResolveAsset:
    def test_finds_an_image_inside_the_project(self, content):
        content.project("demo")
        content.asset("demo", "cover.png")
        assert content_assets.resolve_asset("demo", "assets/cover.png") is not None

    def test_refuses_to_climb_out_of_the_project(self, content):
        content.project("demo").project("other")
        content.asset("other", "secret.png")
        assert content_assets.resolve_asset("demo", "../other/assets/secret.png") is None

    def test_refuses_to_climb_out_of_the_repo(self, content):
        content.project("demo")
        assert content_assets.resolve_asset("demo", "../../../../etc/passwd") is None

    def test_refuses_an_absolute_path(self, content):
        content.project("demo")
        # Path("/a") / "/etc/hosts" is "/etc/hosts" -- the join does not
        # protect anything, the containment check does.
        assert content_assets.resolve_asset("demo", "/etc/hosts") is None

    def test_refuses_a_symlink_pointing_out(self, content, tmp_path):
        content.project("demo")
        outside = tmp_path / "outside.png"
        outside.write_bytes(b"x")
        link = content.content_dir("demo") / "link.png"
        link.symlink_to(outside)
        assert content_assets.resolve_asset("demo", "link.png") is None

    def test_refuses_a_disallowed_extension(self, content):
        content.project("demo")
        (content.content_dir("demo") / "notes.md").write_text("x")
        assert content_assets.resolve_asset("demo", "notes.md") is None

    def test_refuses_a_project_slug_that_is_not_a_project(self, content):
        assert content_assets.resolve_asset("..", "anything.png") is None

    def test_missing_file_is_the_same_answer_as_forbidden(self, content):
        content.project("demo")
        assert content_assets.resolve_asset("demo", "assets/gone.png") is None


class TestProjectCoverUrl:
    def test_resolves_from_the_project_directory_while_unversioned(self, content):
        content.project("demo")
        content.asset("demo", "cover.png")
        assert content_assets.project_cover_url("demo", "assets/cover.png") == (
            "/api/public/assets/demo/assets/cover.png"
        )

    def test_still_resolves_after_the_first_freeze(self, content):
        """_project.yml stays at the project level while assets/ moves down
        into current/ -- the regression this fallback exists for."""
        content.project("demo")
        content.asset("demo", "cover.png", version="current")
        content.versions("demo", default="current", frozen=["v1.0"])
        assert content_assets.project_cover_url("demo", "assets/cover.png") == (
            "/api/public/assets/demo/current/assets/cover.png"
        )

    def test_follows_the_default_version_not_the_writable_one(self, content):
        content.project("demo")
        content.asset("demo", "cover.png", version="current")
        content.asset("demo", "cover.png", version="v1.0")
        content.versions("demo", default="v1.0", frozen=["v1.0"])
        assert content_assets.project_cover_url("demo", "assets/cover.png") == (
            "/api/public/assets/demo/v1.0/assets/cover.png"
        )

    def test_the_fallback_does_not_widen_containment(self, content):
        content.project("demo").project("other")
        content.asset("other", "secret.png")
        content.versions("demo", default="current", frozen=[])
        assert content_assets.project_cover_url("demo", "../other/assets/secret.png") is None

    def test_blank_is_no_cover(self, content):
        content.project("demo")
        assert content_assets.project_cover_url("demo", "") is None

    def test_a_path_that_exists_nowhere_is_no_cover(self, content):
        content.project("demo")
        content.versions("demo", default="current", frozen=[])
        assert content_assets.project_cover_url("demo", "assets/gone.png") is None


class TestMediaVersusImages:
    """Everything servable can be embedded in a page; only an image can be a
    cover. Merged into one list, `image: assets/demo.mp4` would resolve and a
    tile would try to paint a video as a picture."""

    def test_media_is_servable(self, content):
        content.project("demo")
        (content.content_dir("demo") / "assets").mkdir(parents=True, exist_ok=True)
        (content.content_dir("demo") / "assets" / "tour.mp4").write_bytes(b"x")
        assert content_assets.resolve_asset("demo", "assets/tour.mp4") is not None

    def test_media_cannot_be_a_cover(self, content):
        content.project("demo")
        (content.content_dir("demo") / "assets").mkdir(parents=True, exist_ok=True)
        (content.content_dir("demo") / "assets" / "tour.mp4").write_bytes(b"x")
        assert content_assets.project_cover_url("demo", "assets/tour.mp4") is None

    def test_the_two_lists_do_not_overlap(self):
        assert not set(content_assets.IMAGE_TYPES) & set(content_assets.MEDIA_TYPES)

    def test_every_servable_type_has_a_content_check(self):
        """rejection_reason() indexes a table by extension. A type accepted by
        the extension check but missing from that table used to be a KeyError
        -- a 500 on upload rather than a refusal."""
        for extension in content_assets.CONTENT_TYPES:
            reason = content_assets.rejection_reason(f"f{extension}", b"definitely not that format")
            assert reason is not None, extension
            assert "No content check is implemented" not in reason, extension


class TestCategoryCoverUrl:
    def test_resolves_the_same_relative_path_a_page_would_use(self, content):
        content.project("demo").category("demo", "guide")
        content.asset("demo", "tile.png")
        assert content_assets.category_cover_url("demo", "", "guide", "../assets/tile.png") == (
            "/api/public/assets/demo/assets/tile.png"
        )

    def test_a_frozen_version_cannot_borrow_another_version_s_image(self, content):
        """Otherwise a released version's tile would change every time
        current's images did."""
        content.project("demo")
        content.category("demo", "guide", version="v1.0")
        content.asset("demo", "tile.png", version="current")
        content.versions("demo", default="current", frozen=["v1.0"])
        assert (
            content_assets.category_cover_url("demo", "v1.0", "guide", "../../current/assets/tile.png")
            is None
        )
