"""Preview links: the parts that decide whether a link still works.

The storage itself needs a database and is not tested here (see conftest's
note on that boundary). What is tested is everything that answers "is this
link still good?", because every one of those answers is the difference
between a draft being readable by someone who was sent it and a draft being
readable by whoever kept the URL.
"""
from datetime import date

from app.services import preview_links_store as store

TODAY = date(2026, 9, 4)


class TestExpiry:
    def test_valid_through_the_whole_of_its_last_day(self):
        """The date is what the author picked in the UI. A link that stopped
        working at some hour of the day they typed would be a surprise."""
        assert store.is_expired("2026-09-04", TODAY) is False

    def test_expired_the_day_after(self):
        assert store.is_expired("2026-09-03", TODAY) is True

    def test_a_future_date_is_live(self):
        assert store.is_expired("2026-12-31", TODAY) is False

    def test_no_date_at_all_counts_as_expired(self):
        """There is deliberately no never-expiring preview link, so a row
        with no date is a broken row -- and the safe reading of a broken
        expiry on a credential is that it is over."""
        assert store.is_expired("", TODAY) is True

    def test_an_unparseable_date_counts_as_expired(self):
        assert store.is_expired("whenever", TODAY) is True
        assert store.is_expired("2026-13-45", TODAY) is True


class TestDays:
    def test_clamped_into_range(self):
        assert store.clamp_days(0) == store.MIN_DAYS
        assert store.clamp_days(-30) == store.MIN_DAYS
        assert store.clamp_days(9999) == store.MAX_DAYS

    def test_a_value_in_range_is_kept(self):
        assert store.clamp_days(14) == 14

    def test_nonsense_falls_back_to_the_default(self):
        assert store.clamp_days("soon") == store.DEFAULT_DAYS  # type: ignore[arg-type]
        assert store.clamp_days(None) == store.DEFAULT_DAYS  # type: ignore[arg-type]

    def test_the_default_is_itself_in_range(self):
        assert store.MIN_DAYS <= store.DEFAULT_DAYS <= store.MAX_DAYS


class TestTokens:
    def test_carries_the_prefix_that_marks_it(self):
        token = store.generate_token()
        assert token.startswith(store.TOKEN_PREFIX)
        assert store.looks_like_token(token)

    def test_is_distinct_from_an_api_token(self):
        """A secret scanner, and a person reading a log, have to be able to
        tell a read-one-page link from a credential that writes the docs."""
        from app.services import api_tokens_store

        assert store.TOKEN_PREFIX != api_tokens_store.TOKEN_PREFIX

    def test_two_tokens_are_never_the_same(self):
        assert len({store.generate_token() for _ in range(200)}) == 200

    def test_a_foreign_value_is_not_even_looked_up(self):
        assert store.looks_like_token("dwt_something") is False
        assert store.looks_like_token("") is False

    def test_hashing_is_stable_and_hides_the_value(self):
        token = store.generate_token()
        digest = store.hash_token(token)
        assert digest == store.hash_token(token)
        assert token not in digest
        assert len(digest) == 64


class TestUrl:
    def test_is_the_route_the_frontend_serves(self):
        """One spelling of this path: App.tsx routes /preview/:token, and the
        admin UI builds the link it hands the author out of this."""
        assert store.url_path("dwp_abc") == "/preview/dwp_abc"
