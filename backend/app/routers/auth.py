import re
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.services import login_throttle, mail_notifications, mailer, mfa_store, oidc_client, project_access, session_registry_store, users_store, visibility
from app.services.client_address import client_address
from app.services.same_origin import is_same_origin
from app.settings import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str


class SetupCredentials(Credentials):
    setup_token: str = ""


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def _client_ip(request: Request) -> str:
    return client_address(request) or "unknown"


def _refuse_cross_site(request: Request) -> None:
    # These routes are exempt from the admin middleware (they are how a
    # session starts, ends or changes), so they check the origin themselves.
    if not is_same_origin(request):
        raise HTTPException(status_code=403, detail="cross_site_request")


def _refuse_if_throttled(address: str, username: str) -> None:
    wait = login_throttle.retry_after(address, username)
    if wait:
        minutes = max(1, -(-wait // 60))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(wait)},
        )


def _start_session(request: Request, username: str) -> None:
    users_store.touch_login(username)
    session_id = secrets.token_urlsafe(24)
    request.session["authenticated"] = True
    request.session["username"] = username
    request.session["session_id"] = session_id
    session_registry_store.create(session_id, username, _client_ip(request), request.headers.get("user-agent", ""))


def safe_next(target: str | None) -> str:
    """Where to send somebody after signing in: a path on THIS site, or "/".
    It must start with exactly one slash -- that alone rules out a scheme
    (`https:`, `javascript:`) and a protocol-relative `//host` -- and may not
    contain a backslash (browsers read it as a slash) or a line break. So a
    crafted sign-in link cannot become a redirect to somebody else's site."""
    target = (target or "").strip()
    if not target.startswith("/") or target.startswith("//") or any(c in target for c in "\\\r\n"):
        return "/"
    return target[:500]


# Failed setup codes count against this name, not against any account.
_SETUP_THROTTLE_KEY = "(setup)"


@router.get("/status", summary="Auth status")
def auth_status(request: Request):
    if not users_store.is_configured():
        return {
            "setup_required": True,
            "setup_token_required": bool(settings.setup_token),
            "authenticated": False,
            "username": None,
        }
    # The same check the public site uses to show private projects
    # (services/visibility.py): a revoked or signed-out session is not
    # "authenticated" just because the cookie still says so.
    authenticated = visibility.signed_in(request)
    # The role comes from the account, not from the session: it is what the
    # UI hides controls by, and a UI that kept showing yesterday's role
    # would offer buttons the middleware then refuses. (The middleware is
    # the enforcement either way -- this only decides what is worth showing.)
    user = users_store.get_user(request.session.get("username") or "") if authenticated else None
    return {
        "setup_required": False,
        "authenticated": authenticated and user is not None,
        "username": user["username"] if user else None,
        "role": user["role"] if user else None,
        # Exceptions to that role per project, {slug: role} -- what the
        # editor shows as writable (services/project_access.py).
        "project_roles": project_access.writable_projects(user) if user else {},
    }


@router.post("/setup", summary="First-run admin account setup")
def auth_setup(body: SetupCredentials, request: Request):
    _refuse_cross_site(request)
    if users_store.is_configured():
        raise HTTPException(status_code=409, detail="An admin account already exists.")
    if settings.setup_token:
        # Throttled like a password: the installer's code is far too long to
        # guess, but a code somebody chose by hand might not be.
        address = client_address(request)
        _refuse_if_throttled(address, _SETUP_THROTTLE_KEY)
        if not secrets.compare_digest(body.setup_token.strip().encode(), settings.setup_token.encode()):
            login_throttle.record_failure(address, _SETUP_THROTTLE_KEY)
            raise HTTPException(status_code=403, detail="setup_token_invalid")
    if not body.username.strip() or len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Username required, password needs at least 8 characters.")
    users_store.create_first_admin(body.username.strip(), body.password)
    _start_session(request, body.username.strip())
    return {"ok": True}


@router.post("/login", summary="Admin login")
def auth_login(body: Credentials, request: Request):
    _refuse_cross_site(request)
    username = body.username.strip()
    address = client_address(request)
    _refuse_if_throttled(address, username)
    if not users_store.verify_credentials(username, body.password):
        login_throttle.record_failure(address, username)
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    if mfa_store.enabled(username):
        # The password was right, and that is all it proves: the session
        # starts once the second factor is given too (routers/mfa.py). The
        # throttle is not reset yet, so guessing the code is still counted.
        from app.routers.mfa import begin_pending_login

        return begin_pending_login(request, username)
    login_throttle.record_success(username)
    _start_session(request, username)
    return {"ok": True}


@router.post("/logout", summary="Logout")
def auth_logout(request: Request):
    _refuse_cross_site(request)
    session_id = request.session.get("session_id")
    if session_id:
        session_registry_store.revoke(session_id)
    request.session.clear()
    return {"ok": True}


@router.post("/password", summary="Change the admin password")
def change_password(body: PasswordChange, request: Request):
    _refuse_cross_site(request)
    username = request.session.get("username")
    session_id = request.session.get("session_id")
    # Exempt from the middleware, so the session registry is checked here:
    # a session that was revoked (account deleted, signed out elsewhere) must
    # not still be able to change the password.
    if not username or not session_id or not session_registry_store.exists(session_id):
        raise HTTPException(status_code=401, detail="Not logged in.")
    address = client_address(request)
    _refuse_if_throttled(address, username)
    if not users_store.verify_credentials(username, body.current_password):
        login_throttle.record_failure(address, username)
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password needs at least 8 characters.")
    users_store.set_password(username, body.new_password)
    # A password is usually changed because it may have leaked; whatever
    # session the leak was used to open ends here too. This one stays.
    signed_out = session_registry_store.revoke_others(username, session_id)
    return {"ok": True, "other_sessions_signed_out": signed_out}


class NotificationsIn(BaseModel):
    email: str = ""
    notify: list[str] = []


_EMAIL_RE = re.compile(r"^[^@\s<>,;\"]+@[^@\s<>,;\"]+\.[^@\s<>,;\"]+$")


def _signed_in_user(request: Request) -> dict:
    """The account behind this session, checked the way the middleware
    checks it -- /api/auth/ is exempt from the middleware."""
    username = request.session.get("username")
    session_id = request.session.get("session_id")
    if not username or not session_id or not session_registry_store.exists(session_id):
        raise HTTPException(status_code=401, detail="Not logged in.")
    user = users_store.get_user(username)
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return user


@router.get(
    "/notifications",
    summary="Your own e-mail notifications",
    description="`enabled` false when this instance has no SMTP server (SMTP_HOST), in which case nothing is "
    "ever sent and the settings are not offered. `kinds` lists what can be chosen.",
)
def get_notifications(request: Request):
    user = _signed_in_user(request)
    return {
        **users_store.get_notifications(user["username"]),
        "enabled": mailer.is_enabled(),
        "kinds": list(mail_notifications.KINDS),
    }


@router.put("/notifications", summary="Set your own e-mail address and notifications")
def set_notifications(body: NotificationsIn, request: Request):
    _refuse_cross_site(request)
    user = _signed_in_user(request)
    email = body.email.strip()
    if email and (len(email) > 254 or not _EMAIL_RE.match(email)):
        raise HTTPException(status_code=400, detail="That is not an e-mail address.")
    unknown = [kind for kind in body.notify if kind not in mail_notifications.KINDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown notification: {', '.join(unknown)}.")
    if body.notify and not email:
        raise HTTPException(status_code=400, detail="Notifications need an e-mail address.")
    kinds = [kind for kind in mail_notifications.KINDS if kind in body.notify]
    users_store.set_notifications(user["username"], email, kinds)
    return {**users_store.get_notifications(user["username"]), "enabled": mailer.is_enabled()}


@router.post(
    "/notifications/test",
    summary="Send yourself a test e-mail",
    description="Sends now and waits for the SMTP server's answer, so a wrong SMTP setting shows up here "
    "rather than as notifications that never arrive. 409 `not_configured` without SMTP_HOST, 400 without an "
    "address, 502 with the kind of error (never the password) when the server refuses.",
)
def test_notification(request: Request):
    _refuse_cross_site(request)
    user = _signed_in_user(request)
    if not mailer.is_enabled():
        raise HTTPException(status_code=409, detail="not_configured")
    email = users_store.get_notifications(user["username"])["email"]
    if not email:
        raise HTTPException(status_code=400, detail="Save an e-mail address first.")
    message = mailer.build(
        email,
        "DocuWaves: test",
        "This is a test message from DocuWaves. E-mail notifications work.\n",
    )
    try:
        mailer.deliver(message)
    except Exception as exc:  # noqa: BLE001 -- reported by kind, never with its text (may echo credentials)
        raise HTTPException(status_code=502, detail=f"The mail server refused: {type(exc).__name__}") from exc
    return {"ok": True}


def _oidc_redirect_uri(request: Request) -> str:
    return f"{str(request.base_url).rstrip('/')}/api/auth/oidc/callback"


@router.get("/oidc/status", summary="Whether SSO login is configured")
def oidc_status():
    return {"enabled": oidc_client.is_enabled(), "provider_name": oidc_client.provider_name()}


@router.get("/oidc/login", summary="Start an SSO login")
def oidc_login(request: Request, next: str = ""):
    if not oidc_client.is_enabled():
        raise HTTPException(status_code=404, detail="OIDC is not configured.")
    try:
        auth_request = oidc_client.build_authorization_request(_oidc_redirect_uri(request))
    except oidc_client.OidcError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    request.session["oidc_state"] = auth_request["state"]
    request.session["oidc_nonce"] = auth_request["nonce"]
    request.session["oidc_code_verifier"] = auth_request["code_verifier"]
    # Where the reader was when they chose to sign in -- a private project's
    # page, typically -- so SSO brings them back there instead of to "/".
    request.session["oidc_next"] = safe_next(next)
    return RedirectResponse(auth_request["url"])


@router.get("/oidc/callback", summary="SSO login callback")
def oidc_callback(request: Request):
    error = request.query_params.get("error")
    if error:
        return RedirectResponse("/?oidc_login=failed")

    next_url = safe_next(request.session.pop("oidc_next", "/"))
    expected_state = request.session.pop("oidc_state", None)
    nonce = request.session.pop("oidc_nonce", None)
    code_verifier = request.session.pop("oidc_code_verifier", None)
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state or not expected_state or state != expected_state or not nonce or not code_verifier:
        return RedirectResponse("/?oidc_login=failed")

    try:
        claims = oidc_client.complete_login(code, _oidc_redirect_uri(request), code_verifier, nonce)
    except oidc_client.OidcError:
        return RedirectResponse("/?oidc_login=failed")

    subject = oidc_client.subject_from_claims(claims)
    if not subject:
        return RedirectResponse("/?oidc_login=failed")

    # An account already bound to this identity: that account, whatever the
    # provider now says the person's username or email is.
    bound = users_store.get_user_by_oidc_subject(subject)
    if bound is not None:
        _start_session(request, bound["username"])
        return RedirectResponse(next_url)

    username = oidc_client.username_from_claims(claims)
    if not username:
        return RedirectResponse("/?oidc_login=failed")

    if not users_store.is_configured():
        if settings.setup_token:
            # A provider login carries no setup code, so it cannot be what
            # claims an instance that asks for one: set up with the code and a
            # password first; this identity binds to that account on its
            # first sign-in, by username, as below.
            return RedirectResponse("/?oidc_login=setup_token")
        # First-run bootstrap: whoever completes a valid OIDC login first on
        # a totally unconfigured instance becomes the one admin account --
        # same trust model as POST /api/auth/setup. Random password (never
        # surfaced) since the schema always needs a password_hash; this
        # account is OIDC-only until the admin sets a real password from
        # the account settings page.
        users_store.create_first_admin(username, secrets.token_urlsafe(32))
        users_store.bind_oidc_subject(username, subject)
        _start_session(request, username)
        return RedirectResponse(next_url)

    # Already configured: the OIDC username must match an account that
    # exists here, or the login is rejected. Anyone who can authenticate
    # against the identity provider is NOT automatically granted access --
    # accounts are created deliberately, by an admin, and the role they get
    # is decided there rather than by whoever the provider lets in. That is
    # the same rule as before multi-user; what changed is only how many
    # accounts it can match.
    existing = users_store.get_user(username)
    if existing is None:
        return RedirectResponse("/?oidc_login=no_account")
    # First SSO sign-in for this account: bind it to this identity from now
    # on. An account already bound to a DIFFERENT identity is not taken over
    # by somebody who merely carries the same username or email -- which is
    # exactly what a person who can pick their own username at the provider
    # would otherwise be able to do to an account called "admin".
    if users_store.oidc_subject(username):
        return RedirectResponse("/?oidc_login=failed")
    users_store.bind_oidc_subject(username, subject)
    _start_session(request, username)
    return RedirectResponse(next_url)
