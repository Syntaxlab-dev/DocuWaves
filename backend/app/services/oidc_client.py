"""Generic OIDC Authorization Code Flow (with PKCE) for admin SSO login --
not hardcoded to any specific provider: authorize/token/jwks endpoints are
read from `{OIDC_ISSUER_URL}/.well-known/openid-configuration` rather than
assumed.

Configuration lives in plain environment variables (settings.py), not a
database row -- same chicken-and-egg reasoning as CachePanel's identical
feature: the only place OIDC settings could otherwise live requires an
authenticated session to reach, which is exactly what this feature needs
to provide on a fresh, unconfigured instance.

Issuer check is normalized (rstrip("/")) on both sides rather than a
strict string match -- a real lesson from building this exact feature for
CachePanel: providers commonly issue tokens with a trailing slash in `iss`
(e.g. Authentik's per-provider issuer is always ".../application/o/<slug>/")
even when the configured issuer URL doesn't have one, and a strict compare
rejects every real login. Same reasoning for always fetching JWKS fresh
(no caching): a provider that has zero signing keys today but gets one
configured five minutes from now must work on the very next login attempt,
not fail forever against a stale cached discovery document.
"""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests
from joserfc import jwt
from joserfc.jwk import KeySet

from app.settings import settings

_HTTP_TIMEOUT = 10


class OidcError(RuntimeError):
    pass


def is_enabled() -> bool:
    return bool(settings.oidc_issuer_url and settings.oidc_client_id and settings.oidc_client_secret)


def provider_name() -> str:
    return settings.oidc_provider_name or "SSO"


def _discovery_document() -> dict:
    url = settings.oidc_issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = requests.get(url, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise OidcError(f"Could not fetch the identity provider's discovery document: {exc}") from exc


def build_authorization_request(redirect_uri: str) -> dict:
    if not is_enabled():
        raise OidcError("OIDC is not configured.")

    discovery = _discovery_document()
    authorization_endpoint = discovery.get("authorization_endpoint")
    if not authorization_endpoint:
        raise OidcError("The identity provider's discovery document has no authorization_endpoint.")

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")

    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return {
        "url": f"{authorization_endpoint}?{urlencode(params)}",
        "state": state,
        "nonce": nonce,
        "code_verifier": code_verifier,
    }


def _exchange_code(discovery: dict, code: str, redirect_uri: str, code_verifier: str) -> dict:
    token_endpoint = discovery.get("token_endpoint")
    if not token_endpoint:
        raise OidcError("The identity provider's discovery document has no token_endpoint.")

    resp = requests.post(
        token_endpoint,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "code_verifier": code_verifier,
        },
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        raise OidcError(f"Token exchange failed (HTTP {resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    if "id_token" not in data:
        raise OidcError("The identity provider's token response has no id_token.")
    return data


def _validate_id_token(discovery: dict, id_token: str, nonce: str) -> dict:
    jwks_uri = discovery.get("jwks_uri")
    if not jwks_uri:
        raise OidcError("The identity provider's discovery document has no jwks_uri.")

    try:
        jwks_resp = requests.get(jwks_uri, timeout=_HTTP_TIMEOUT)
        jwks_resp.raise_for_status()
        jwks_raw = jwks_resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise OidcError(f"Could not fetch the identity provider's signing keys: {exc}") from exc

    if not jwks_raw.get("keys"):
        raise OidcError(
            "The identity provider's JWKS endpoint returned no signing keys -- it likely needs an RS256 "
            "signing key/certificate configured on the provider side before OIDC clients can validate its tokens."
        )

    key_set = KeySet.import_key_set(jwks_raw)

    try:
        token = jwt.decode(id_token, key_set, algorithms=["RS256"])
    except Exception as exc:
        raise OidcError(f"ID token signature validation failed: {exc}") from exc

    claims_registry = jwt.JWTClaimsRegistry(
        aud={"essential": True, "value": settings.oidc_client_id},
        exp={"essential": True},
    )
    try:
        claims_registry.validate(token.claims)
    except Exception as exc:
        raise OidcError(f"ID token claims validation failed: {exc}") from exc

    actual_issuer = str(token.claims.get("iss") or "").rstrip("/")
    if actual_issuer != settings.oidc_issuer_url.rstrip("/"):
        raise OidcError(f"ID token issuer mismatch: expected {settings.oidc_issuer_url!r}, got {actual_issuer!r}.")

    if token.claims.get("nonce") != nonce:
        raise OidcError("ID token nonce mismatch -- possible replay of an old login attempt.")

    return token.claims


def complete_login(code: str, redirect_uri: str, code_verifier: str, nonce: str) -> dict:
    if not is_enabled():
        raise OidcError("OIDC is not configured.")
    discovery = _discovery_document()
    tokens = _exchange_code(discovery, code, redirect_uri, code_verifier)
    return _validate_id_token(discovery, tokens["id_token"], nonce)


def username_from_claims(claims: dict) -> str | None:
    for key in ("preferred_username", "email", "sub"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
