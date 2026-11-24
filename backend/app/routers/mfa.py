"""Two-factor sign-in: the second step of a login, and an account's own 2FA
settings. What the factors are and what they do not cover is in
services/mfa_store.py.

Every route here is under /api/auth/, which auth_guard leaves open (it is
how a session starts), so each one checks for itself what it needs:

  * the login routes need a PENDING login -- a correct password from the
    last five minutes, held in the signed session cookie -- and nothing
    else. They are throttled exactly like a password, per address and per
    account, so a stolen password does not buy unlimited guesses at a
    six-digit code.
  * the settings routes need a live session (checked against the session
    registry, like /api/auth/password), and every route that REMOVES a
    factor asks for the password again: a session left open on somebody
    else's screen must not be enough to switch 2FA off.
"""

import hashlib
import json
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.routers.auth import _refuse_cross_site, _refuse_if_throttled, _start_session
from app.services import login_throttle, mfa_store, seo, session_registry_store, site_branding, users_store
from app.services.client_address import client_address

router = APIRouter(prefix="/api/auth/mfa", tags=["auth"])

# How long a correct password waits for its second factor.
PENDING_SECONDS = 5 * 60
_PENDING_KEY = "mfa_pending"
_CHALLENGE_KEY = "mfa_challenge"

_TRANSPORTS = {t.value for t in AuthenticatorTransport}


class CodeIn(BaseModel):
    code: str


class CredentialIn(BaseModel):
    credential: dict


class NewKeyIn(BaseModel):
    name: str = ""
    credential: dict


class PasswordIn(BaseModel):
    password: str


# ---- Helpers ----


def begin_pending_login(request: Request, username: str) -> dict:
    """Called by /api/auth/login after a correct password, instead of
    starting a session. The reply tells the login screen what to ask for."""
    request.session[_PENDING_KEY] = {"username": username, "until": time.time() + PENDING_SECONDS}
    return {"ok": False, "mfa_required": True, "methods": mfa_store.methods(username)}


def _pending_username(request: Request) -> str:
    pending = request.session.get(_PENDING_KEY)
    if not isinstance(pending, dict) or float(pending.get("until") or 0) < time.time():
        request.session.pop(_PENDING_KEY, None)
        raise HTTPException(status_code=401, detail="mfa_login_expired")
    username = str(pending.get("username") or "")
    if users_store.get_user(username) is None:
        request.session.pop(_PENDING_KEY, None)
        raise HTTPException(status_code=401, detail="mfa_login_expired")
    return username


def _finish_login(request: Request, username: str) -> None:
    request.session.pop(_PENDING_KEY, None)
    request.session.pop(_CHALLENGE_KEY, None)
    login_throttle.record_success(username)
    _start_session(request, username)


def _signed_in_username(request: Request) -> str:
    username = request.session.get("username")
    session_id = request.session.get("session_id")
    if (
        not request.session.get("authenticated")
        or not username
        or not session_id
        or not session_registry_store.exists(session_id)
        or users_store.get_user(username) is None
    ):
        raise HTTPException(status_code=401, detail="Not logged in.")
    return username


def _require_password(request: Request, username: str, password: str) -> None:
    address = client_address(request)
    _refuse_if_throttled(address, username)
    if not users_store.verify_credentials(username, password):
        login_throttle.record_failure(address, username)
        raise HTTPException(status_code=401, detail="Current password is incorrect.")


def _relying_party(request: Request) -> tuple[str, str]:
    """(rp_id, origin). Both come from the instance's public address -- the
    same one links and the sitemap use -- because a key is bound to the
    host name it was registered on, and that must not change with whatever
    Host header a request happened to carry."""
    origin = seo.public_base_url(request).rstrip("/")
    host = origin.split("://", 1)[-1].split("/", 1)[0]
    if host.startswith("["):
        rp_id = host[1 : host.index("]")]
    else:
        rp_id = host.rsplit(":", 1)[0] if ":" in host else host
    return rp_id, origin


def _user_handle(username: str) -> bytes:
    # The spec asks for an opaque handle with nothing personal in it; the
    # username never changes, so a hash of it is stable without a column.
    return hashlib.sha256(f"docuwaves-user:{username}".encode()).digest()


def _take_challenge(request: Request, purpose: str) -> bytes:
    stored = request.session.pop(_CHALLENGE_KEY, None)
    if not isinstance(stored, dict) or stored.get("purpose") != purpose or float(stored.get("until") or 0) < time.time():
        raise HTTPException(status_code=400, detail="mfa_challenge_expired")
    return mfa_store.b64url_decode(stored["challenge"])


def _store_challenge(request: Request, purpose: str, challenge: bytes) -> None:
    request.session[_CHALLENGE_KEY] = {
        "purpose": purpose,
        "challenge": mfa_store.b64url(challenge),
        "until": time.time() + PENDING_SECONDS,
    }


def _descriptors(username: str) -> list[PublicKeyCredentialDescriptor]:
    return [
        PublicKeyCredentialDescriptor(
            id=key["credential_id"],
            transports=[AuthenticatorTransport(t) for t in key["transports"] if t in _TRANSPORTS] or None,
        )
        for key in mfa_store.key_credentials(username)
    ]


def _fresh_recovery_codes(username: str) -> list[str] | None:
    """Ten codes the first time a factor is added, so nobody ends up with 2FA
    and no way back in. Later factors leave the existing codes alone."""
    if mfa_store.has_recovery_codes(username):
        return None
    return mfa_store.regenerate_recovery_codes(username)


def _after_removal(username: str) -> None:
    # The last factor gone means 2FA is off; codes for a 2FA that is off
    # would only be a way to sign in that nobody remembers having.
    if not mfa_store.enabled(username):
        mfa_store.delete_all(username)


# ---- The second step of a login ----


@router.post("/login/webauthn/options", summary="Start signing in with a security key")
def login_webauthn_options(request: Request):
    _refuse_cross_site(request)
    username = _pending_username(request)
    descriptors = _descriptors(username)
    if not descriptors:
        raise HTTPException(status_code=400, detail="No security key is registered for this account.")
    rp_id, _ = _relying_party(request)
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=descriptors,
        user_verification=UserVerificationRequirement.DISCOURAGED,
    )
    _store_challenge(request, "login", options.challenge)
    return json.loads(options_to_json(options))


@router.post("/login/webauthn", summary="Finish signing in with a security key")
def login_webauthn(body: CredentialIn, request: Request):
    _refuse_cross_site(request)
    username = _pending_username(request)
    address = client_address(request)
    _refuse_if_throttled(address, username)
    challenge = _take_challenge(request, "login")
    rp_id, origin = _relying_party(request)
    try:
        raw_id = mfa_store.b64url_decode(str(body.credential.get("rawId") or body.credential.get("id") or ""))
    except ValueError:
        raw_id = b""
    key = next((k for k in mfa_store.key_credentials(username) if k["credential_id"] == raw_id), None)
    try:
        if key is None:
            raise InvalidAuthenticationResponse("unknown credential")
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=key["public_key"],
            credential_current_sign_count=key["sign_count"],
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError):
        login_throttle.record_failure(address, username)
        raise HTTPException(status_code=401, detail="mfa_invalid") from None
    mfa_store.key_used(key["id"], verified.new_sign_count)
    _finish_login(request, username)
    return {"ok": True}


@router.post("/login/totp", summary="Finish signing in with an authenticator code")
def login_totp(body: CodeIn, request: Request):
    _refuse_cross_site(request)
    username = _pending_username(request)
    address = client_address(request)
    _refuse_if_throttled(address, username)
    if not mfa_store.verify_totp(username, body.code):
        login_throttle.record_failure(address, username)
        raise HTTPException(status_code=401, detail="mfa_invalid")
    _finish_login(request, username)
    return {"ok": True}


@router.post("/login/recovery", summary="Finish signing in with a recovery code")
def login_recovery(body: CodeIn, request: Request):
    _refuse_cross_site(request)
    username = _pending_username(request)
    address = client_address(request)
    _refuse_if_throttled(address, username)
    if not mfa_store.use_recovery_code(username, body.code):
        login_throttle.record_failure(address, username)
        raise HTTPException(status_code=401, detail="mfa_invalid")
    _finish_login(request, username)
    return {"ok": True, "recovery_codes_left": mfa_store.recovery_codes_left(username)}


# ---- An account's own 2FA settings ----


@router.get("", summary="This account's two-factor sign-in")
def mfa_status(request: Request):
    return mfa_store.status(_signed_in_username(request))


@router.post("/keys/options", summary="Start adding a security key or passkey")
def key_options(request: Request):
    _refuse_cross_site(request)
    username = _signed_in_username(request)
    rp_id, _ = _relying_party(request)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=site_branding.read_branding().get("name") or "DocuWaves",
        user_name=username,
        user_id=_user_handle(username),
        exclude_credentials=_descriptors(username),
        authenticator_selection=AuthenticatorSelectionCriteria(
            # "Preferred" lets a phone or laptop store it as a passkey, and
            # a YubiKey keep it either way; it is never REQUIRED, so an
            # older key with no storage of its own still works.
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.DISCOURAGED,
        ),
    )
    _store_challenge(request, "register", options.challenge)
    return json.loads(options_to_json(options))


@router.post("/keys", summary="Finish adding a security key or passkey", status_code=201)
def add_key(body: NewKeyIn, request: Request):
    _refuse_cross_site(request)
    username = _signed_in_username(request)
    challenge = _take_challenge(request, "register")
    rp_id, origin = _relying_party(request)
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except (InvalidRegistrationResponse, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"The key could not be registered: {exc}") from exc
    if mfa_store.credential_in_use(verified.credential_id):
        raise HTTPException(status_code=409, detail="This key is already registered.")
    response = body.credential.get("response") if isinstance(body.credential.get("response"), dict) else {}
    transports = [t for t in (response.get("transports") or []) if isinstance(t, str) and t in _TRANSPORTS]
    mfa_store.add_key(
        username, body.name, verified.credential_id, verified.credential_public_key, verified.sign_count, transports
    )
    codes = _fresh_recovery_codes(username)
    return {**mfa_store.status(username), "recovery_codes": codes}


@router.post("/keys/{key_id}/delete", summary="Remove a security key")
def delete_key(key_id: int, body: PasswordIn, request: Request):
    _refuse_cross_site(request)
    username = _signed_in_username(request)
    _require_password(request, username, body.password)
    if not mfa_store.delete_key(username, key_id):
        raise HTTPException(status_code=404, detail="No such key.")
    _after_removal(username)
    return mfa_store.status(username)


@router.post("/totp/setup", summary="Start setting up an authenticator app")
def totp_setup(request: Request):
    _refuse_cross_site(request)
    username = _signed_in_username(request)
    if mfa_store.totp_enabled(username):
        raise HTTPException(status_code=409, detail="An authenticator app is already set up. Remove it first.")
    secret = mfa_store.start_totp(username)
    issuer = site_branding.read_branding().get("name") or "DocuWaves"
    return {"secret": secret, "uri": mfa_store.otpauth_uri(secret, username, issuer)}


@router.post("/totp/confirm", summary="Finish setting up an authenticator app")
def totp_confirm(body: CodeIn, request: Request):
    _refuse_cross_site(request)
    username = _signed_in_username(request)
    if not mfa_store.confirm_totp(username, body.code):
        raise HTTPException(status_code=400, detail="mfa_invalid")
    codes = _fresh_recovery_codes(username)
    return {**mfa_store.status(username), "recovery_codes": codes}


@router.post("/totp/disable", summary="Remove the authenticator app")
def totp_disable(body: PasswordIn, request: Request):
    _refuse_cross_site(request)
    username = _signed_in_username(request)
    _require_password(request, username, body.password)
    mfa_store.disable_totp(username)
    _after_removal(username)
    return mfa_store.status(username)


@router.post("/recovery", summary="Replace the recovery codes")
def new_recovery_codes(body: PasswordIn, request: Request):
    _refuse_cross_site(request)
    username = _signed_in_username(request)
    _require_password(request, username, body.password)
    if not mfa_store.enabled(username):
        raise HTTPException(status_code=400, detail="Two-factor sign-in is not on for this account.")
    codes = mfa_store.regenerate_recovery_codes(username)
    return {**mfa_store.status(username), "recovery_codes": codes}
