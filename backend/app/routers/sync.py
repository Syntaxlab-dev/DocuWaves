"""Docs-as-code: the endpoint a code repository's CI pushes its docs to
(services/docs_sync.py). Authorized by a SYNC token only, and only for the
one project that token was made for -- auth_guard.py turns everything else
away before this runs."""
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.services import api_tokens_store, content_versions, docs_sync, git_content_repo, importer

router = APIRouter(prefix="/api/sync", tags=["sync"])


async def _read_body(request: Request) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > importer.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail=f"The archive is larger than {importer.MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/{project_slug}",
    summary="Replace a project's content with the docs from a code repository",
    description="The body is a ZIP of the docs folder (at most 50 MB, any format the importer reads). `ref` is "
    "the code commit or tag it came from, for the commit message and the history. Pages become what the archive "
    "says: added, changed, removed -- published unless their front matter says `draft: true`. One commit, none "
    "when nothing changed. Requires `Authorization: Bearer <sync token for this project>`.",
)
async def sync_project(project_slug: str, request: Request, ref: str = ""):
    token = getattr(request.state, "api_token", None)
    if token is None or token.get("scope") != api_tokens_store.SYNC_SCOPE:
        raise HTTPException(status_code=403, detail="This endpoint needs a sync token.")
    if token.get("project") != project_slug:
        raise HTTPException(status_code=403, detail=f"This token syncs '{token.get('project')}', not '{project_slug}'.")
    data = await _read_body(request)
    author = api_tokens_store.author_name(token["name"])
    try:
        return await run_in_threadpool(docs_sync.sync, data, project_slug, author, ref)
    except (docs_sync.SyncError, importer.ImportError_) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except content_versions.FrozenVersionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except git_content_repo.GitContentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
