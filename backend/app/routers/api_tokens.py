"""Managing the API tokens an operator hands to an AI assistant (see
services/api_tokens_store.py for what a token is and where it is stored,
and routers/mcp.py for what one is used on).

Admin-only, by construction: this router sits under /api/admin/, which
AuthGuardMiddleware requires an admin SESSION for -- and which it explicitly
refuses an API token on. So a token can never be used to mint another token,
widen its own scope, or read the list of what else exists. Issuing
credentials stays something a human does after logging in.

Three routes and no more: create, list, revoke. There is deliberately no
"edit" -- a token's scope and expiry are what its holder was given, and
quietly upgrading a read token to write would change what a credential
already in someone else's hands can do, without that hand ever knowing.
Changing either means issuing a new token and revoking the old one, which is
the same thing but visible.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import api_tokens_store

router = APIRouter(prefix="/api/admin/tokens", tags=["admin"])


class TokenIn(BaseModel):
    name: str
    # 'read' or 'write'; write implies read. Validated in the store, which
    # is also what the MCP endpoint checks against, so there is one list of
    # valid scopes rather than one here and one there.
    scope: str = api_tokens_store.READ_SCOPE
    # ISO date (YYYY-MM-DD), or "" for a token that never expires. A date
    # rather than a duration because "expires 2027-01-01" is a fact the
    # operator can check against their own calendar, while "expires in 90
    # days" is one they would have to compute every time they look.
    expires_at: str = ""


@router.get(
    "",
    summary="List the API tokens",
    description="Name, scope, expiry, when it was created and when it was last used -- never the token value "
    "itself, which is unrecoverable after creation (only a SHA-256 hash is stored). `last_used_at` is empty for "
    "a token nothing has ever authenticated with, which is what a token worth revoking looks like.",
)
def list_tokens():
    return {"tokens": api_tokens_store.list_tokens(), "max_tokens": api_tokens_store.MAX_TOKENS}


@router.post(
    "",
    summary="Create an API token",
    description="Returns the token value ONCE, in `token`. It is not stored and cannot be shown again -- only "
    "its hash is kept, so a lost token is replaced rather than looked up. A `write` token can create and change "
    "documentation pages through the MCP endpoint; hand one out accordingly.",
)
def create_token(body: TokenIn):
    name = api_tokens_store.normalize_name(body.name)
    scope = (body.scope or "").strip().lower()
    expires_at = (body.expires_at or "").strip()
    reason = api_tokens_store.rejection_reason(name, scope, expires_at)
    if reason is not None:
        raise HTTPException(status_code=400, detail=reason)
    record, token = api_tokens_store.create(name, scope, expires_at)
    # The one and only time the plaintext leaves this process. Not logged,
    # here or anywhere else.
    return {**record, "token": token}


@router.delete(
    "/{token_id}",
    summary="Revoke an API token",
    description="Deletes the token's row. It stops working on the very next request -- an assistant still "
    "holding the value gets exactly the same answer as one holding a value that never existed.",
)
def revoke_token(token_id: int):
    if not api_tokens_store.revoke(token_id):
        raise HTTPException(status_code=404, detail="Token not found.")
    return {"ok": True}
