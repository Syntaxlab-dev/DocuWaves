"""Accounts: who may open the editing UI, and as what.

Admin-only, and enforced one level up rather than here -- /api/admin/users
is in auth_guard's _ADMIN_ONLY_PREFIXES, so every route in this file is
already behind that check before it is reached. Nothing below re-states it.

THE THREE THINGS THAT MUST NOT HAPPEN, and where each is stopped:

- An instance with no admin left. Refused in users_store, where set_role
  and delete_user share is_last_admin -- so the check cannot be forgotten
  by a caller, and two admins demoting each other from parallel browser
  tabs cannot race past it: the second request to arrive re-reads the
  count.

  This is the rule that catches an admin STEPPING DOWN, which is allowed
  and is why the self-check below covers only two of the three actions.
  Handing an instance over ("make her an admin, then make me an editor") is
  a real thing to want; being the only admin and demoting yourself is not,
  and it has no undo that does not involve editing the database by hand.

- Deleting your own account. Refused outright: unlike a role change there
  is no version of it that leaves you anywhere, and an admin who wants to
  be gone can be removed by the admin they hand over to.

- Reaching your own password without knowing it. This router's password
  route does not ask for the current one -- it exists for the case where
  somebody is locked out and an admin sets them a new one. Pointing it at
  your own account would turn it into a way around /api/auth/password,
  which does ask. So it is refused here, and that route is the only way to
  change your own.

- A password travelling anywhere it does not have to. It is sent once, in
  the request that sets it, and never read back.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services import session_registry_store, users_store

router = APIRouter(prefix="/api/admin/users", tags=["admin"])


class UserIn(BaseModel):
    username: str
    password: str
    role: str = users_store.VIEWER


class RoleIn(BaseModel):
    role: str


class PasswordIn(BaseModel):
    password: str


def _me(request: Request) -> str:
    return request.session.get("username") or ""


def _require_other_account(request: Request, username: str, action: str) -> None:
    if username == _me(request):
        raise HTTPException(status_code=400, detail=f"You cannot {action} your own account.")


def _require_existing(username: str) -> dict:
    user = users_store.get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="No such account.")
    return user


def _require_valid_role(role: str) -> str:
    if role not in users_store.ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(users_store.ROLES)}.",
        )
    return role


def _require_valid_password(password: str) -> str:
    if len(password) < users_store.MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"A password needs at least {users_store.MIN_PASSWORD_LENGTH} characters.",
        )
    return password


def _with_sessions(user: dict) -> dict:
    return {**user, "sessions": len(session_registry_store.sessions_for(user["username"]))}


@router.get(
    "",
    summary="Every account on this instance",
    description="Name, role, when it was created, when it last signed in, and how many sessions it has open "
    "right now. Never a password hash -- the store does not return one to begin with, so no endpoint here "
    "can leak it by forgetting to strip it.",
)
def list_users(request: Request):
    return {
        "users": [_with_sessions(user) for user in users_store.list_users()],
        "roles": list(users_store.ROLES),
        "me": _me(request),
        "min_password_length": users_store.MIN_PASSWORD_LENGTH,
    }


@router.post("", summary="Create an account", status_code=201)
def create_user(body: UserIn):
    role = _require_valid_role(body.role)
    _require_valid_password(body.password)
    username = users_store.normalize_username(body.username)
    if not username:
        raise HTTPException(status_code=400, detail="A username is required.")
    user = users_store.create_user(username, body.password, role)
    if user is None:
        raise HTTPException(status_code=409, detail="That name is already taken.")
    return user


@router.put(
    "/{username}/role",
    summary="Change what an account may do",
    description="Refused when it would leave the instance with no administrator -- which is also what stops "
    "the last admin from stepping down, the one case an admin may change their OWN role. "
    "Lowering a role signs that account out everywhere: the middleware re-reads the role on every request, so "
    "the change is already in force -- signing them out is what makes it visible, rather than leaving them "
    "clicking around a UI that has quietly started answering 403.",
)
def set_role(username: str, body: RoleIn, request: Request):
    role = _require_valid_role(body.role)
    user = _require_existing(username)
    # No self-check here, deliberately: stepping down is allowed, and what
    # stops the last admin doing it is the count in users_store.set_role.
    if not users_store.set_role(username, role):
        raise HTTPException(
            status_code=409,
            detail="This is the only administrator left. Make somebody else an administrator first.",
        )
    if not users_store.is_admin(role) and users_store.is_admin(user["role"]):
        session_registry_store.revoke_for_user(username)
    return users_store.get_user(username)


@router.put(
    "/{username}/password",
    summary="Set an account's password",
    description="For the case an account is locked out -- an admin sets a new password and tells the person. "
    "It signs that account out everywhere, because a password that was changed for somebody is usually a "
    "password that was changed BECAUSE of somebody. Changing your OWN password is /api/auth/password, which "
    "asks for the current one; this route does not, and so is not a way around that.",
)
def set_password(username: str, body: PasswordIn, request: Request):
    _require_existing(username)
    _require_other_account(request, username, "reset the password of")
    _require_valid_password(body.password)
    users_store.set_password(username, body.password)
    revoked = session_registry_store.revoke_for_user(username)
    return {"ok": True, "sessions_ended": revoked}


@router.delete(
    "/{username}",
    summary="Remove an account",
    description="Refused for your own account, and refused for the last administrator. Everything that person "
    "wrote keeps their name on it: the content repo attributes commits by name, and no account row is needed "
    "for that to stay true.",
)
def delete_user(username: str, request: Request):
    _require_existing(username)
    _require_other_account(request, username, "delete")
    if not users_store.delete_user(username):
        raise HTTPException(
            status_code=409,
            detail="This is the only administrator left. Make somebody else an administrator first.",
        )
    return {"ok": True, "sessions_ended": session_registry_store.revoke_for_user(username)}
