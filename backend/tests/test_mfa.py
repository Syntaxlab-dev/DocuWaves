"""Two-factor sign-in: the authenticator-app arithmetic, recovery codes, the
login that stops after the password, security keys (with a software
authenticator standing in for a YubiKey), and the admin reset."""
import base64
import hashlib
import importlib
import json
import os
import struct
import time

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.services import db, login_throttle, mfa_store, session_secret, users_store
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}
ADMIN = ("chef", "chef-passwort-123")
EDITOR = ("autorin", "autorin-passwort-123")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "content_repo_path", str(tmp_path / "repo"))
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "public_base_url", "")
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    login_throttle.reset()
    db.init_schema()
    users_store.create_first_admin(*ADMIN)
    users_store.create_user(EDITOR[0], EDITOR[1], users_store.EDITOR)
    yield importlib.import_module("app.main").app
    login_throttle.reset()


def signed_in(app, user) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN)
    assert r.json() == {"ok": True}, r.text
    return c


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# ---- The authenticator app's arithmetic ----

class TestTotp:
    def test_rfc_6238_vectors(self):
        # RFC 6238 appendix B, SHA-1, the 8-digit values cut to six.
        secret = base64.b32encode(b"12345678901234567890").decode()
        assert mfa_store.totp_code(secret, 59) == "287082"
        assert mfa_store.totp_code(secret, 1111111109) == "081804"
        assert mfa_store.totp_code(secret, 2000000000) == "279037"

    def test_uri_names_issuer_and_account(self):
        uri = mfa_store.otpauth_uri("ABC", "michel", "Meine Doku")
        assert uri.startswith("otpauth://totp/Meine%20Doku%3Amichel?secret=ABC&issuer=Meine%20Doku")

    def test_confirm_then_verify_once_per_step(self, app):
        secret = mfa_store.start_totp("chef")
        assert not mfa_store.totp_enabled("chef")
        now = time.time()
        assert not mfa_store.confirm_totp("chef", "000000" if mfa_store.totp_code(secret, now) != "000000" else "111111", now)
        assert mfa_store.confirm_totp("chef", mfa_store.totp_code(secret, now), now)
        assert mfa_store.totp_enabled("chef")
        # The code used to confirm is spent; the next step's works once.
        assert not mfa_store.verify_totp("chef", mfa_store.totp_code(secret, now), now)
        later = now + mfa_store.TOTP_PERIOD
        assert mfa_store.verify_totp("chef", mfa_store.totp_code(secret, later), later)
        assert not mfa_store.verify_totp("chef", mfa_store.totp_code(secret, later), later)

    def test_a_drifting_clock_is_forgiven_by_one_step(self, app):
        secret = mfa_store.start_totp("chef")
        now = time.time()
        assert mfa_store.confirm_totp("chef", mfa_store.totp_code(secret, now - mfa_store.TOTP_PERIOD), now)
        far = now + 10 * mfa_store.TOTP_PERIOD
        assert not mfa_store.verify_totp("chef", mfa_store.totp_code(secret, far - 3 * mfa_store.TOTP_PERIOD), far)


class TestRecoveryCodes:
    def test_ten_codes_each_works_once(self, app):
        codes = mfa_store.regenerate_recovery_codes("chef")
        assert len(codes) == 10 and len(set(codes)) == 10
        assert mfa_store.use_recovery_code("chef", codes[0].upper().replace("-", " "))
        assert not mfa_store.use_recovery_code("chef", codes[0])
        assert mfa_store.recovery_codes_left("chef") == 9

    def test_regenerating_invalidates_the_old_ones(self, app):
        old = mfa_store.regenerate_recovery_codes("chef")
        mfa_store.regenerate_recovery_codes("chef")
        assert not mfa_store.use_recovery_code("chef", old[1])

    def test_codes_are_not_shared_between_accounts(self, app):
        codes = mfa_store.regenerate_recovery_codes("chef")
        assert not mfa_store.use_recovery_code("autorin", codes[0])

    def test_only_hashes_are_stored(self, app):
        codes = mfa_store.regenerate_recovery_codes("chef")
        raw = open(settings.sqlite_path, "rb").read()
        assert codes[0].encode() not in raw


# ---- Login with an authenticator app ----

def enable_totp(app, user) -> tuple[TestClient, str, list[str]]:
    c = signed_in(app, user)
    setup = c.post("/api/auth/mfa/totp/setup", headers=ORIGIN).json()
    assert setup["uri"].startswith("otpauth://totp/")
    r = c.post("/api/auth/mfa/totp/confirm", json={"code": mfa_store.totp_code(setup["secret"])}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] and len(r.json()["recovery_codes"]) == 10
    return c, setup["secret"], r.json()["recovery_codes"]


def advance_step(user: str) -> None:
    # The confirming code spent the current step; pretend it was the last one.
    with db.get_connection() as conn:
        conn.execute("UPDATE mfa_totp SET last_step = last_step - 1 WHERE username = ?", (user,))


class TestLogin:
    def test_without_2fa_a_password_is_enough(self, app):
        signed_in(app, ADMIN)

    def test_with_2fa_the_password_alone_starts_no_session(self, app):
        enable_totp(app, ADMIN)
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}, headers=ORIGIN)
        assert r.json() == {"ok": False, "mfa_required": True, "methods": ["totp", "recovery"]}
        assert c.get("/api/auth/status").json()["authenticated"] is False
        assert c.get("/api/admin/users").status_code == 401

    def test_the_code_finishes_the_login(self, app):
        _, secret, _ = enable_totp(app, ADMIN)
        advance_step(ADMIN[0])
        c = TestClient(app)
        c.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}, headers=ORIGIN)
        r = c.post("/api/auth/mfa/login/totp", json={"code": mfa_store.totp_code(secret)}, headers=ORIGIN)
        assert r.json() == {"ok": True}
        assert c.get("/api/auth/status").json()["authenticated"] is True

    def test_a_wrong_code_is_refused_and_counted(self, app):
        enable_totp(app, ADMIN)
        c = TestClient(app)
        c.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}, headers=ORIGIN)
        for _ in range(login_throttle.MAX_FAILURES_PER_ADDRESS):
            assert c.post("/api/auth/mfa/login/totp", json={"code": "12"}, headers=ORIGIN).status_code == 401
        assert c.post("/api/auth/mfa/login/totp", json={"code": "12"}, headers=ORIGIN).status_code == 429

    def test_no_second_step_without_the_password(self, app):
        _, secret, _ = enable_totp(app, ADMIN)
        r = TestClient(app).post("/api/auth/mfa/login/totp", json={"code": mfa_store.totp_code(secret)}, headers=ORIGIN)
        assert r.status_code == 401

    def test_the_pending_login_expires(self, app, monkeypatch):
        _, secret, _ = enable_totp(app, ADMIN)
        advance_step(ADMIN[0])
        c = TestClient(app)
        c.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}, headers=ORIGIN)
        real = time.time
        monkeypatch.setattr(time, "time", lambda: real() + 301)
        r = c.post("/api/auth/mfa/login/totp", json={"code": mfa_store.totp_code(secret, real())}, headers=ORIGIN)
        assert r.status_code == 401 and r.json()["detail"] == "mfa_login_expired"

    def test_a_recovery_code_works_once(self, app):
        _, _, codes = enable_totp(app, ADMIN)
        for expected in (200, 401):
            c = TestClient(app)
            c.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}, headers=ORIGIN)
            r = c.post("/api/auth/mfa/login/recovery", json={"code": codes[3]}, headers=ORIGIN)
            assert r.status_code == expected
        assert r.status_code == 401

    def test_cross_site_is_refused(self, app):
        r = TestClient(app).post("/api/auth/mfa/login/totp", json={"code": "123456"}, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403


class TestSettings:
    def test_needs_a_session(self, app):
        assert TestClient(app).get("/api/auth/mfa").status_code == 401
        assert TestClient(app).post("/api/auth/mfa/totp/setup", headers=ORIGIN).status_code == 401

    def test_removing_needs_the_password_and_takes_the_codes_with_it(self, app):
        c, _, _ = enable_totp(app, ADMIN)
        assert c.post("/api/auth/mfa/totp/disable", json={"password": "falsch"}, headers=ORIGIN).status_code == 401
        r = c.post("/api/auth/mfa/totp/disable", json={"password": ADMIN[1]}, headers=ORIGIN)
        assert r.json() == {"enabled": False, "keys": [], "totp": False, "recovery_codes_left": 0}
        assert signed_in(app, ADMIN)

    def test_new_recovery_codes(self, app):
        c, _, old = enable_totp(app, ADMIN)
        r = c.post("/api/auth/mfa/recovery", json={"password": ADMIN[1]}, headers=ORIGIN)
        assert len(r.json()["recovery_codes"]) == 10 and set(r.json()["recovery_codes"]).isdisjoint(old)

    def test_a_second_app_needs_the_first_removed(self, app):
        c, _, _ = enable_totp(app, ADMIN)
        assert c.post("/api/auth/mfa/totp/setup", headers=ORIGIN).status_code == 409


class TestAdminReset:
    def test_admin_resets_somebody_else(self, app):
        _, _, _ = enable_totp(app, EDITOR)
        admin = signed_in(app, ADMIN)
        users = {u["username"]: u for u in admin.get("/api/admin/users").json()["users"]}
        assert users["autorin"]["mfa"] is True and users["chef"]["mfa"] is False
        r = admin.post("/api/admin/users/autorin/mfa/reset", headers=ORIGIN)
        assert r.status_code == 200
        assert not mfa_store.enabled("autorin") and mfa_store.recovery_codes_left("autorin") == 0
        assert signed_in(app, EDITOR)

    def test_not_for_your_own_account(self, app):
        enable_totp(app, ADMIN)
        # Signing in now needs the code; use the store to get a session.
        mfa_store.delete_all(ADMIN[0])
        admin = signed_in(app, ADMIN)
        assert admin.post("/api/admin/users/chef/mfa/reset", headers=ORIGIN).status_code == 400

    def test_an_editor_cannot(self, app):
        editor = signed_in(app, EDITOR)
        assert editor.post("/api/admin/users/chef/mfa/reset", headers=ORIGIN).status_code == 403

    def test_deleting_an_account_deletes_its_factors(self, app):
        enable_totp(app, EDITOR)
        assert users_store.delete_user(EDITOR[0])
        assert not mfa_store.enabled(EDITOR[0])
        with db.get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM mfa_recovery_codes").fetchone()[0] == 0


# ---- Security keys, with a software authenticator ----

class SoftKey:
    """Just enough of a FIDO2 authenticator to register and sign in: an
    ES256 key pair, "none" attestation, a counter."""

    def __init__(self, rp_id="testserver", origin="http://testserver"):
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.rp_id, self.origin = rp_id, origin
        self.counter = 0

    def _client_data(self, kind, challenge):
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}).encode()

    def _cose(self):
        numbers = self.private.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})

    def register(self, options):
        client_data = self._client_data("webauthn.create", options["challenge"])
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x41]) + struct.pack(">I", self.counter)
            + bytes(16) + struct.pack(">H", len(self.credential_id)) + self.credential_id + self._cose()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.credential_id), "rawId": b64url(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64url(client_data), "attestationObject": b64url(attestation), "transports": ["usb", "nfc"]},
        }

    def sign(self, options):
        self.counter += 1
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x01]) + struct.pack(">I", self.counter)
        signature = self.private.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64url(self.credential_id), "rawId": b64url(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64url(client_data), "authenticatorData": b64url(auth_data), "signature": b64url(signature)},
        }


def add_key(c, key, name="YubiKey 5C"):
    options = c.post("/api/auth/mfa/keys/options", headers=ORIGIN).json()
    assert options["rp"]["id"] == "testserver"
    return c.post("/api/auth/mfa/keys", json={"name": name, "credential": key.register(options)}, headers=ORIGIN)


def key_login(app, key, user=ADMIN):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN)
    assert r.json()["mfa_required"] and r.json()["methods"][0] == "webauthn"
    options = c.post("/api/auth/mfa/login/webauthn/options", headers=ORIGIN).json()
    return c, c.post("/api/auth/mfa/login/webauthn", json={"credential": key.sign(options)}, headers=ORIGIN)


class TestSecurityKeys:
    def test_register_and_sign_in(self, app):
        key = SoftKey()
        r = add_key(signed_in(app, ADMIN), key)
        assert r.status_code == 201, r.text
        assert r.json()["keys"][0]["name"] == "YubiKey 5C" and len(r.json()["recovery_codes"]) == 10
        assert r.json()["recovery_codes_left"] == 10
        c, r = key_login(app, key)
        assert r.json() == {"ok": True}
        assert c.get("/api/auth/status").json()["authenticated"] is True
        assert mfa_store.list_keys("chef")[0]["last_used_at"]

    def test_a_second_key_keeps_the_codes(self, app):
        c = signed_in(app, ADMIN)
        add_key(c, SoftKey())
        r = add_key(c, SoftKey(), "Ersatzschlüssel")
        assert r.json()["recovery_codes"] is None and len(r.json()["keys"]) == 2

    def test_somebody_elses_key_is_refused(self, app):
        add_key(signed_in(app, ADMIN), SoftKey())
        _, r = key_login(app, SoftKey())
        assert r.status_code == 401

    def test_a_key_for_another_site_is_refused(self, app):
        key = SoftKey()
        add_key(signed_in(app, ADMIN), key)
        key.origin = "https://evil.example"
        _, r = key_login(app, key)
        assert r.status_code == 401

    def test_a_replayed_assertion_is_refused(self, app):
        key = SoftKey()
        add_key(signed_in(app, ADMIN), key)
        c = TestClient(app)
        c.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}, headers=ORIGIN)
        options = c.post("/api/auth/mfa/login/webauthn/options", headers=ORIGIN).json()
        assertion = key.sign(options)
        assert c.post("/api/auth/mfa/login/webauthn", json={"credential": assertion}, headers=ORIGIN).status_code == 200
        c2 = TestClient(app)
        c2.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}, headers=ORIGIN)
        assert c2.post("/api/auth/mfa/login/webauthn", json={"credential": assertion}, headers=ORIGIN).status_code == 400

    def test_the_same_key_twice_is_refused(self, app):
        c = signed_in(app, ADMIN)
        key = SoftKey()
        add_key(c, key)
        options = c.post("/api/auth/mfa/keys/options", headers=ORIGIN).json()
        assert [d["id"] for d in options["excludeCredentials"]] == [b64url(key.credential_id)]
        r = c.post("/api/auth/mfa/keys", json={"name": "x", "credential": key.register(options)}, headers=ORIGIN)
        assert r.status_code == 409

    def test_removing_the_last_key_switches_2fa_off(self, app):
        c = signed_in(app, ADMIN)
        add_key(c, SoftKey())
        key_id = mfa_store.list_keys("chef")[0]["id"]
        assert c.post(f"/api/auth/mfa/keys/{key_id}/delete", json={"password": "nope"}, headers=ORIGIN).status_code == 401
        r = c.post(f"/api/auth/mfa/keys/{key_id}/delete", json={"password": ADMIN[1]}, headers=ORIGIN)
        assert r.json()["enabled"] is False and r.json()["recovery_codes_left"] == 0

    def test_cannot_remove_somebody_elses_key(self, app):
        add_key(signed_in(app, EDITOR), SoftKey())
        key_id = mfa_store.list_keys("autorin")[0]["id"]
        mine = signed_in(app, ADMIN)
        r = mine.post(f"/api/auth/mfa/keys/{key_id}/delete", json={"password": ADMIN[1]}, headers=ORIGIN)
        assert r.status_code == 404 and mfa_store.list_keys("autorin")
