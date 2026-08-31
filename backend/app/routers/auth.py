import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.services import auth_credentials_store, oidc_client, session_registry_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _start_session(request: Request, username: str) -> None:
    session_id = secrets.token_urlsafe(24)
    request.session["authenticated"] = True
    request.session["username"] = username
    request.session["session_id"] = session_id
    session_registry_store.create(session_id, username, _client_ip(request), request.headers.get("user-agent", ""))


@router.get("/status", summary="Auth status")
def auth_status(request: Request):
    if not auth_credentials_store.is_configured():
        return {"setup_required": True, "authenticated": False, "username": None}
    authenticated = bool(request.session.get("authenticated"))
    return {
        "setup_required": False,
        "authenticated": authenticated,
        "username": request.session.get("username") if authenticated else None,
    }


@router.post("/setup", summary="First-run admin account setup")
def auth_setup(body: Credentials, request: Request):
    if auth_credentials_store.is_configured():
        raise HTTPException(status_code=409, detail="An admin account already exists.")
    if not body.username.strip() or len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Username required, password needs at least 8 characters.")
    auth_credentials_store.set_credentials(body.username.strip(), body.password)
    _start_session(request, body.username.strip())
    return {"ok": True}


@router.post("/login", summary="Admin login")
def auth_login(body: Credentials, request: Request):
    username = body.username.strip()
    if not auth_credentials_store.verify_credentials(username, body.password):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    _start_session(request, username)
    return {"ok": True}


@router.post("/logout", summary="Logout")
def auth_logout(request: Request):
    session_id = request.session.get("session_id")
    if session_id:
        session_registry_store.revoke(session_id)
    request.session.clear()
    return {"ok": True}


@router.post("/password", summary="Change the admin password")
def change_password(body: PasswordChange, request: Request):
    username = request.session.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in.")
    if not auth_credentials_store.verify_credentials(username, body.current_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password needs at least 8 characters.")
    auth_credentials_store.set_password(username, body.new_password)
    return {"ok": True}


def _oidc_redirect_uri(request: Request) -> str:
    return f"{str(request.base_url).rstrip('/')}/api/auth/oidc/callback"


@router.get("/oidc/status", summary="Whether SSO login is configured")
def oidc_status():
    return {"enabled": oidc_client.is_enabled(), "provider_name": oidc_client.provider_name()}


@router.get("/oidc/login", summary="Start an SSO login")
def oidc_login(request: Request):
    if not oidc_client.is_enabled():
        raise HTTPException(status_code=404, detail="OIDC is not configured.")
    try:
        auth_request = oidc_client.build_authorization_request(_oidc_redirect_uri(request))
    except oidc_client.OidcError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    request.session["oidc_state"] = auth_request["state"]
    request.session["oidc_nonce"] = auth_request["nonce"]
    request.session["oidc_code_verifier"] = auth_request["code_verifier"]
    return RedirectResponse(auth_request["url"])


@router.get("/oidc/callback", summary="SSO login callback")
def oidc_callback(request: Request):
    error = request.query_params.get("error")
    if error:
        return RedirectResponse("/?oidc_login=failed")

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

    username = oidc_client.username_from_claims(claims)
    if not username:
        return RedirectResponse("/?oidc_login=failed")

    if not auth_credentials_store.is_configured():
        # First-run bootstrap: whoever completes a valid OIDC login first on
        # a totally unconfigured instance becomes the one admin account --
        # same trust model as POST /api/auth/setup. Random password (never
        # surfaced) since the schema always needs a password_hash; this
        # account is OIDC-only until the admin sets a real password from
        # the account settings page.
        auth_credentials_store.set_credentials(username, secrets.token_urlsafe(32))
        _start_session(request, username)
        return RedirectResponse("/")

    # Already configured: v1 has exactly one admin account, so the OIDC
    # username must match it exactly, or the login is rejected -- anyone
    # who can authenticate against the identity provider is NOT
    # automatically granted access, only the one identity that either
    # bootstrapped this instance or was explicitly matched at setup time.
    existing = auth_credentials_store.get_user(username)
    if existing is None:
        return RedirectResponse("/?oidc_login=no_account")

    _start_session(request, username)
    return RedirectResponse("/")
