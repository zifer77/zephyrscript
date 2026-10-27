import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.routers.projects import get_owned_project
from app.services import file_service
from app.services.auth_service import get_current_user, get_current_user_flex
from app.utils.path_sanitizer import PathError, safe_join
from app.utils.security import create_token, decode_token

router = APIRouter(tags=["preview"])


def _preview_token(user_id: int, project_id: int) -> str:
    return create_token(
        str(user_id), settings.preview_token_expire_minutes, {"scope": "preview", "pid": project_id}
    )


def _resolve(project_id: int, rel: str) -> Path:
    root = file_service.project_dir(project_id)
    rel = rel.strip("/")
    if not rel:
        rel = "index.html"
    try:
        target = safe_join(root, rel)
    except PathError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File tidak ditemukan")
    return target


@router.get("/api/projects/{project_id}/preview", response_class=HTMLResponse)
def preview(
    project_id: int,
    entry: str = Query("index.html"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_flex),
):
    """Serve index.html project. Auth: header Bearer atau ?token=<jwt> (untuk iframe)."""
    project = get_owned_project(db, project_id, user)
    target = _resolve(project.id, entry)
    html = target.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"<base\s", html, re.I):
        # base href berisi token preview (jangka pendek) agar asset relatif (css/js/img) termuat
        base = f'<base href="/api/preview/{_preview_token(user.id, project.id)}/{project.id}/">'
        if re.search(r"<head[^>]*>", html, re.I):
            html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + base, html, count=1, flags=re.I)
        else:
            html = base + html
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.post("/api/projects/{project_id}/preview-token")
def create_preview_token(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Token preview berumur pendek; pakai di URL: /api/preview/<token>/<project_id>/"""
    project = get_owned_project(db, project_id, user)
    token = _preview_token(user.id, project.id)
    return {
        "token": token,
        "url": f"/api/preview/{token}/{project.id}/",
        "expires_in": settings.preview_token_expire_minutes * 60,
    }


@router.get("/api/preview/{token}/{project_id}/{path:path}")
def preview_asset(token: str, project_id: int, path: str = ""):
    """Static serving asset project (css, js, img, html) tanpa header Authorization."""
    payload = decode_token(token)
    if not payload or payload.get("scope") != "preview" or payload.get("pid") != project_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token preview tidak valid")
    target = _resolve(project_id, path)
    return FileResponse(target, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
