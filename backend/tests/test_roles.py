"""Who may do what.

Two things are pinned here, and they are the two that would be expensive to
get wrong:

1. The RULE the middleware applies -- which method counts as a write, which
   prefixes are admin-only. Read straight out of auth_guard so a change to
   the rule has to change this file too, rather than quietly widening what a
   viewer can do.
2. Resolving a role. It resolves DOWN for anything unknown, so a hand-edited
   row saying `role: superuser` is a viewer and not an accident.

The store's own database operations are not tested here (no database in this
suite -- see conftest); the store keeps its last-admin rule inside the same
function that writes, precisely so no caller can perform one without the
other.
"""
import pytest

from app import auth_guard
from app.services import users_store


class TestRoleResolution:
    def test_the_three_roles_are_themselves(self):
        for role in users_store.ROLES:
            assert users_store.normalize_role(role) == role

    @pytest.mark.parametrize("value", ["superuser", "root", "ADMIN", "", "owner", "editor "])
    def test_anything_else_resolves_down_to_viewer(self, value):
        """Never up. A typo, an invented role in a hand-edited row, or a
        value from a future version must not grant anything."""
        assert users_store.normalize_role(value) == users_store.VIEWER

    def test_the_account_that_predates_roles_is_an_admin(self):
        """The database column's DEFAULT is what migrates the single account
        this app used to have -- if this ever stopped being admin, upgrading
        would lock that person out of their own instance."""
        assert users_store.DEFAULT_ROLE == users_store.ADMIN


class TestWhatEachRoleMay:
    def test_only_editor_and_admin_write(self):
        assert users_store.may_write(users_store.EDITOR)
        assert users_store.may_write(users_store.ADMIN)
        assert not users_store.may_write(users_store.VIEWER)

    def test_only_admin_is_admin(self):
        assert users_store.is_admin(users_store.ADMIN)
        assert not users_store.is_admin(users_store.EDITOR)
        assert not users_store.is_admin(users_store.VIEWER)

    def test_an_unknown_role_may_nothing(self):
        assert not users_store.may_write("superuser")
        assert not users_store.is_admin("superuser")


class TestTheMiddlewareRule:
    def test_reading_is_get_and_head_and_nothing_else(self):
        """The write rule is the HTTP method rather than a list of
        endpoints, so an endpoint added later is guarded before anyone
        remembers to think about it. Widening this set widens what every
        read-only account can do."""
        assert set(auth_guard._READ_METHODS) == {"GET", "HEAD"}

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/users",
            "/api/admin/users/someone/role",
            "/api/admin/tokens",
            "/api/admin/site",
            "/api/admin/site/assets",
            "/api/admin/diagnostics",
            "/api/admin/export",
            "/api/admin/export/summary",
        ],
    )
    def test_instance_level_paths_are_admin_only(self, path):
        """Each of these is authority over the INSTANCE rather than over its
        documentation: handing out a credential, changing what the site
        claims to be, downloading the whole thing."""
        assert path.startswith(auth_guard._ADMIN_ONLY_PREFIXES)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/projects",
            "/api/admin/pages/1",
            "/api/admin/pages/1/preview-links",
            "/api/admin/categories/2",
            "/api/admin/feedback",
            "/api/admin/link-check",
            "/api/admin/page-templates",
            "/api/admin/content-repo/status",
        ],
    )
    def test_documentation_paths_are_not(self, path):
        """An editor edits the documentation. If one of these ever became
        admin-only by accident, every editor account would silently stop
        being able to do its job."""
        assert not path.startswith(auth_guard._ADMIN_ONLY_PREFIXES)


class TestPasswords:
    def test_the_minimum_is_the_one_the_setup_form_already_enforced(self):
        assert users_store.MIN_PASSWORD_LENGTH == 8

    def test_bcrypt_s_72_byte_limit_is_applied_to_bytes_not_characters(self):
        """bcrypt 5 raises above 72 bytes where 4.x truncated silently.
        Truncating the ENCODED bytes is what keeps every hash written under
        4.x verifying -- slicing characters instead would invalidate every
        non-ASCII password ever set here."""
        passphrase = "ü" * 50  # 100 bytes in utf-8, 50 characters
        assert len(users_store._password_bytes(passphrase)) == 72

    def test_a_short_password_is_untouched(self):
        assert users_store._password_bytes("hunter22") == b"hunter22"


class TestVerification:
    def test_an_unknown_account_still_costs_a_bcrypt_round(self, monkeypatch):
        """Otherwise the no-such-account branch returns measurably faster
        than the wrong-password branch, and the login form becomes a way to
        enumerate account names."""
        calls = []
        monkeypatch.setattr(users_store.bcrypt, "checkpw", lambda password, hashed: calls.append(hashed) or False)

        class _Conn:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, *args):
                class _Cursor:
                    def fetchone(self):
                        return None

                return _Cursor()

        monkeypatch.setattr(users_store.db, "get_connection", lambda: _Conn())
        assert users_store.verify_credentials("nobody", "whatever") is False
        assert len(calls) == 1
