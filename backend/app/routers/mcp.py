"""The MCP endpoint: one JSON-RPC 2.0 route at POST /api/mcp that lets an AI
assistant read this instance's documentation -- and, with a `write` token,
edit it.

WHAT THIS IS FOR. The admin editor is a browser UI for a human. This is the
same content behind a machine interface, so an operator can hand an
assistant a token and say "document the new release" or "fix every broken
link in the installation guide" and have the result arrive as real commits
in the content repo, reviewable and revertable like any other contribution.

AUTHENTICATION happens entirely in auth_guard.py, before this module is
reached: /api/mcp is the one prefix an API token authorizes and the one
prefix an admin session does NOT. So every request that gets here is already
authenticated, and `request.state.api_token` holds which token it was. A
failure to authenticate is answered as an HTTP 401/403/429 with the usual
`detail` body rather than as a JSON-RPC error -- it is a transport-level
refusal, the caller is not yet a JSON-RPC peer, and every MCP client already
understands an HTTP status on its POST.

SCOPE is enforced in exactly one place, `_call_tool` below, against the
`write` flag each tool carries in mcp_tools.TOOLS. A read token calling a
write tool gets a tool error that names the scope it has, the scope it
needs, and the tools it CAN use -- not a bare failure it has to guess at.

WHICH ERRORS ARE WHICH. A JSON-RPC `error` object means the request itself
was wrong: malformed JSON, an unknown method, an unknown tool name. A
successful `result` carrying `isError: true` means the request was
well-formed and the tool refused it -- no such page, a frozen version, the
wrong scope. That split is the MCP convention and it matters here: an
`error` is a protocol fault the client handles, while an `isError` result is
handed to the MODEL, which is precisely who needs to read "no category 'foo'
in project 'bar'; available: ..." and try again.

TRANSPORT. Plain POST of one JSON-RPC message, answered with one JSON-RPC
message -- no SSE stream and no batching (batches were removed from the
protocol in the 2025-06-18 revision, and this endpoint has no long-running
call that would need a stream). A notification (a message with no `id`) is
answered with 202 and an empty body, as JSON-RPC requires.
"""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.services import api_tokens_store, content_versions, git_content_repo, mcp_tools

log = logging.getLogger("docuwaves")

router = APIRouter(tags=["mcp"])

# MCP revisions this server speaks, newest first. The client names the one it
# wants in `initialize`; a version we know is echoed back, anything else gets
# our newest and the client decides whether it can live with that -- which is
# what the spec asks for, and what keeps an older client working instead of
# failing the handshake outright.
_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

# DocuWaves does not carry a release version of its own anywhere yet, so
# there is nothing truthful to interpolate here; "1" says "the first shape of
# this interface" rather than inventing a number that matches nothing.
_SERVER_VERSION = "1"

# JSON-RPC 2.0's own codes. Spelled out rather than inlined so the two places
# each is used can't drift.
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602


def _result(request_id, payload: dict) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": payload})


def _error(request_id, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _tool_text(payload: dict) -> dict:
    """A successful tool result. The payload goes in as pretty-printed JSON
    text because that is the one content type every MCP client renders and
    every model reads; `structuredContent` is deliberately not used, since
    without a declared outputSchema it would only repeat this same object in
    a field some clients ignore."""
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}]}


def _tool_error(message: str) -> dict:
    """A tool that refused. `isError` rather than a JSON-RPC error, so the
    message reaches the model rather than only the client library."""
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _instructions(token: dict) -> str:
    """The `instructions` an MCP client puts in front of the model alongside
    the tool list. Worth filling in properly: it is the only place to state
    the rules that are not visible in any single tool's schema -- that a
    write is a real commit under this token's name, that frozen versions are
    read-only, and that there is no way to delete anything here."""
    scope = token["scope"]
    lines = [
        "DocuWaves is a documentation CMS whose content lives as Markdown files in a Git repository.",
        f"You are connected with an API token named '{token['name']}' with '{scope}' scope.",
        "Start with list_projects to get the project slugs everything else is addressed by.",
    ]
    if api_tokens_store.may_write(token):
        lines += [
            "This token may write. Every write is a real git commit in the documentation repository, authored "
            f"as \"{api_tokens_store.author_name(token['name'])}\", so the operator can see exactly what you "
            "changed and revert it.",
            "update_page REPLACES a page's body: read_page first and send the complete new text.",
            "Frozen documentation versions are snapshots of past releases and are read-only; writes must target "
            "the version being edited.",
            "There is deliberately no tool for deleting a page, a category or a project. If something should be "
            "removed, say so and let the operator do it in the admin UI.",
        ]
    else:
        lines += [
            "This token is read-only: you can list, read and search the documentation, but not change it. "
            "Creating or editing a page requires a token with 'write' scope, which the operator issues.",
        ]
    return " ".join(lines)


class _JsonRpcFault(Exception):
    """The CALL was wrong, not the tool: no tool name, a name that isn't in
    the catalogue, arguments that aren't an object. Raised rather than
    returned so the two shapes `_call_tool` can produce (a tool result and a
    protocol error) never have to be told apart by inspecting a dict."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _schema_fault(tool: dict, arguments: dict) -> str | None:
    """Checks the arguments against the tool's OWN declared inputSchema, and
    returns a sentence naming what is wrong, or None.

    Nothing did this before, so the schema was documentation rather than a
    contract: a call could omit a `required` parameter and pass an unknown
    one instead, and the tool ran anyway with its default. That is not a
    theoretical hole -- it produced 29 documentation pages created
    successfully and entirely empty, because the caller sent
    `markdown_content` (the name the store uses internally) instead of
    `markdown`, and the endpoint answered "created".

    A wrong name is the likeliest mistake at this interface: every caller is
    a model reading the schema and writing JSON from it, and a silent success
    is the one answer it cannot learn from. Validation only covers what the
    schemas here actually use -- required keys, unknown keys, and the
    declared type -- rather than pulling in a JSON Schema library for a
    handful of flat objects."""
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") or {}

    missing = [key for key in schema.get("required", []) if arguments.get(key) in (None, "")]
    if missing:
        return (
            f"Missing required parameter(s) for '{tool['name']}': {', '.join(missing)}. "
            f"Nothing was written. Accepted parameters: {', '.join(properties)}."
        )

    if schema.get("additionalProperties") is False:
        unknown = [key for key in arguments if key not in properties]
        if unknown:
            return (
                f"Unknown parameter(s) for '{tool['name']}': {', '.join(unknown)}. "
                f"Nothing was written. Accepted parameters: {', '.join(properties)}."
            )

    types = {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list}
    for key, value in arguments.items():
        expected = types.get((properties.get(key) or {}).get("type"))
        # bool is a subclass of int in Python, so an integer parameter would
        # otherwise silently accept true.
        if expected is None or value is None:
            continue
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            return (
                f"Parameter '{key}' of '{tool['name']}' must be "
                f"{(properties[key] or {}).get('type')}. Nothing was written."
            )
    return None


def _call_tool(params: dict, token: dict) -> dict:
    """`tools/call`, answering with the tool RESULT payload. Raises
    _JsonRpcFault when the call itself was malformed."""
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise _JsonRpcFault(_INVALID_PARAMS, "A tools/call needs a tool 'name'.")
    tool = mcp_tools.get(name)
    if tool is None:
        # A protocol-level fault, not a tool refusing: the client asked for
        # something that is not in the catalogue it was given.
        raise _JsonRpcFault(_INVALID_PARAMS, f"No such tool: '{name}'. Available: {', '.join(mcp_tools.tool_names())}.")

    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise _JsonRpcFault(_INVALID_PARAMS, "'arguments' must be an object.")

    if tool["write"] and not api_tokens_store.may_write(token):
        # The one refusal that must never look like a generic failure: an
        # assistant that reads "denied" retries; one that reads this stops
        # and tells the operator what to change.
        return _tool_error(
            f"Permission denied: '{name}' changes the documentation, and the API token you are using "
            f"('{token['name']}') has '{token['scope']}' scope, which is read-only. Nothing was written. "
            f"Ask the operator to issue a token with 'write' scope (admin area -> API tokens); a new token "
            f"is needed, an existing one's scope cannot be changed. "
            f"Tools this token can use: {', '.join(mcp_tools.read_only_names())}."
        )

    # After the scope check, not before it: a read-only token calling a
    # write tool should be told that, whatever else is wrong with its
    # arguments -- the scope is the thing it has to act on.
    fault = _schema_fault(tool, arguments)
    if fault is not None:
        return _tool_error(fault)

    try:
        return _tool_text(tool["handler"](arguments, token))
    except mcp_tools.ToolError as exc:
        return _tool_error(str(exc))
    except content_versions.FrozenVersionError as exc:
        # The same sentence the admin API answers a frozen write with (see
        # main.py's handler), reached here instead of there because this
        # endpoint has to hand it to the model rather than to a browser.
        return _tool_error(str(exc))
    except git_content_repo.GitContentError as exc:
        return _tool_error(
            f"The change could not be committed to the content repo: {exc} "
            f"Nothing further was written; the operator may need to resolve this in the repository."
        )
    except Exception:
        # Logged in full (with the traceback), answered in summary. A bare
        # 500 through a JSON-RPC transport is the least actionable thing a
        # model can receive, and the exception text could name a filesystem
        # path the caller has no business seeing.
        log.exception("MCP tool %r failed", name)
        return _tool_error(
            f"'{name}' failed with an unexpected internal error. It has been logged on the server; the operator "
            f"can find it in the container log. Do not retry the identical call."
        )


def _dispatch(message: dict, token: dict) -> JSONResponse | None:
    """One JSON-RPC message in, one response out -- or None for a
    notification, which by definition gets no answer."""
    request_id = message.get("id")
    is_notification = "id" not in message
    method = message.get("method")

    if message.get("jsonrpc") != "2.0":
        return None if is_notification else _error(request_id, _INVALID_REQUEST, "Expected \"jsonrpc\": \"2.0\".")
    if not isinstance(method, str):
        return None if is_notification else _error(request_id, _INVALID_REQUEST, "A request needs a 'method'.")

    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return None if is_notification else _error(request_id, _INVALID_PARAMS, "'params' must be an object.")

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in _PROTOCOL_VERSIONS else _PROTOCOL_VERSIONS[0]
        return _result(
            request_id,
            {
                "protocolVersion": version,
                # Only tools. This server has no resources, prompts,
                # sampling or logging to offer, and announcing a capability
                # it does not implement would have clients calling methods
                # that answer nothing.
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "docuwaves", "title": "DocuWaves", "version": _SERVER_VERSION},
                "instructions": _instructions(token),
            },
        )

    # The client's post-handshake notification. Nothing to do, but it must
    # not be answered with "method not found" -- a client that gets one may
    # abandon the session.
    if method.startswith("notifications/"):
        return None

    if method == "ping":
        return None if is_notification else _result(request_id, {})

    if method == "tools/list":
        # No pagination: this catalogue is seven fixed tools, and a
        # nextCursor a client would then have to follow buys nothing.
        return _result(request_id, {"tools": mcp_tools.public_catalogue()})

    if method == "tools/call":
        try:
            outcome = _call_tool(params, token)
        except _JsonRpcFault as fault:
            return None if is_notification else _error(request_id, fault.code, str(fault))
        return None if is_notification else _result(request_id, outcome)

    return None if is_notification else _error(
        request_id,
        _METHOD_NOT_FOUND,
        f"Unknown method '{method}'. This server implements: initialize, ping, tools/list, tools/call.",
    )


@router.post(
    "/api/mcp",
    summary="MCP (Model Context Protocol) endpoint -- JSON-RPC 2.0",
    description="Lets an AI assistant read this instance's documentation, and write it when the token allows. "
    "Requires an API token: `Authorization: Bearer dwt_...` (create one under 'API tokens' in the admin area). "
    "An admin session is deliberately NOT accepted here. Implements initialize, ping, tools/list and tools/call; "
    "see the README's 'MCP endpoint' section.",
)
async def mcp_endpoint(request: Request):
    # Set by AuthGuardMiddleware, which is the only way to reach this route.
    # Read defensively anyway: a route that answered as if it were
    # authenticated because a middleware ordering changed would be the worst
    # possible failure here.
    token = getattr(request.state, "api_token", None)
    if not token:
        return JSONResponse({"detail": "invalid_token"}, status_code=401)

    try:
        message = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _error(None, _PARSE_ERROR, f"Request body is not valid JSON: {exc}")

    if isinstance(message, list):
        return _error(
            None,
            _INVALID_REQUEST,
            "Batched requests are not supported (they were removed from MCP in revision 2025-06-18). "
            "Send one JSON-RPC message per request.",
        )
    if not isinstance(message, dict):
        return _error(None, _INVALID_REQUEST, "A JSON-RPC message must be an object.")

    response = _dispatch(message, token)
    if response is None:
        # A notification. 202 with no body, which is what JSON-RPC's "no
        # response to a notification" looks like over HTTP.
        return Response(status_code=202)
    return response
