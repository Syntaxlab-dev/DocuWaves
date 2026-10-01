"""'Being edited': who has a page open in the editor -- a warning, never a
lock; gone a minute after the last heartbeat or at once on close."""
import pytest

from app.services import editing_presence as presence

KEY = presence.page_key("demo", {"version": "", "slug": "install", "language": "de"})
TAB_A, TAB_B, TAB_C = "tab-aaaaaaaa", "tab-bbbbbbbb", "tab-cccccccc"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    presence.reset()
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(presence.time, "time", lambda: clock["now"])
    yield clock
    presence.reset()


def test_somebody_else_on_the_page_is_reported_with_unsaved_changes(clean):
    for _ in range(16):  # five minutes of heartbeats, every 20 seconds
        presence.heartbeat(KEY, TAB_A, "michel", dirty=True)
        clean["now"] += 20
    clean["now"] -= 20
    seen = presence.others(KEY, TAB_B, "anna")
    assert seen == [{"username": "michel", "since": 1_000_000, "seconds": 300, "dirty": True, "same_account": False}]


def test_you_are_not_reported_to_yourself_but_your_other_tab_is():
    presence.heartbeat(KEY, TAB_A, "michel", dirty=False)
    assert presence.others(KEY, TAB_A, "michel") == []
    presence.heartbeat(KEY, TAB_B, "michel", dirty=False)
    assert presence.others(KEY, TAB_A, "michel")[0]["same_account"] is True


def test_a_silent_editor_disappears_after_a_minute(clean):
    presence.heartbeat(KEY, TAB_A, "michel", dirty=False)
    clean["now"] += presence.TTL_SECONDS + 1
    assert presence.others(KEY, TAB_B, "anna") == []


def test_closing_the_editor_removes_it_at_once():
    presence.heartbeat(KEY, TAB_A, "michel", dirty=False)
    presence.leave(KEY, TAB_A)
    assert presence.others(KEY, TAB_B, "anna") == []


def test_other_pages_are_not_mixed_up():
    other = presence.page_key("demo", {"version": "", "slug": "install", "language": "en"})
    presence.heartbeat(other, TAB_A, "michel", dirty=False)
    assert presence.others(KEY, TAB_B, "anna") == []
    assert presence.on_pages({1: KEY, 2: other}) == {2: [{"username": "michel", "dirty": False}]}


def test_tab_ids_are_checked_and_the_table_is_bounded(monkeypatch):
    assert presence.valid_tab("tab-aaaaaaaa")
    assert not presence.valid_tab("x") and not presence.valid_tab("../../etc") and not presence.valid_tab("a" * 65)
    monkeypatch.setattr(presence, "_MAX_ENTRIES", 3)
    for i in range(10):
        presence.heartbeat(KEY, f"tab-{i:08d}", "flood", dirty=False)
    assert len(presence.others(KEY, TAB_C, "anna")) == 3



@pytest.fixture
def app_world(world):
    from app.services import users_store

    users_store.create_user("anna", "anna-passwort-123", users_store.EDITOR)
    users_store.create_user("vera", "vera-passwort-123", users_store.VIEWER)
    return world


from tests.test_private_projects import world  # noqa: E402,F401  (shared fixture)


def test_two_editors_and_a_viewer(app_world):
    from tests.test_private_projects import ORIGIN, client

    chef = client(app_world, ("chef", "chef-passwort-123"))
    anna = client(app_world, ("anna", "anna-passwort-123"))
    vera = client(app_world, ("vera", "vera-passwort-123"))
    page_id = chef.get("/api/admin/categories/1/pages").json()["pages"][0]["id"]
    url = f"/api/admin/pages/{page_id}/presence"

    assert chef.post(url, json={"tab": TAB_A, "dirty": True}, headers=ORIGIN).json() == {"others": []}
    seen = anna.post(url, json={"tab": TAB_B}, headers=ORIGIN).json()["others"]
    assert [(o["username"], o["dirty"]) for o in seen] == [("chef", True)]
    # A viewer may not announce itself (a POST), but may look.
    assert vera.post(url, json={"tab": TAB_C}, headers=ORIGIN).status_code == 403
    assert {o["username"] for o in vera.get(url, params={"tab": TAB_C}).json()["others"]} == {"chef", "anna"}
    marks = chef.get("/api/admin/categories/1/presence").json()["pages"]
    assert {o["username"] for o in marks[str(page_id)]} == {"chef", "anna"}

    chef.delete(url, params={"tab": TAB_A}, headers=ORIGIN)
    assert anna.post(url, json={"tab": TAB_B}, headers=ORIGIN).json()["others"] == []
    assert chef.post(url, json={"tab": "bad"}, headers=ORIGIN).status_code == 400
