from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.file import FileNode
from app.models.project import Project
from app.models.user import User
from app.routers.projects import get_owned_project
from app.schemas.file import FileContent, FileCreate, FileOut, FileTreeNode, FileUpdate
from app.services import file_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api", tags=["files"])


def _get_owned_file(db: Session, file_id: int, user: User) -> tuple[FileNode, Project]:
    row = (
        db.query(FileNode, Project)
        .join(Project, Project.id == FileNode.project_id)
        .filter(FileNode.id == file_id, Project.owner_id == user.id)
        .first()
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File tidak ditemukan")
    return row


@router.get("/projects/{project_id}/files", response_model=list[FileTreeNode])
def project_tree(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(db, project_id, user)
    return file_service.get_tree(db, project)


@router.post("/files", response_model=FileOut, status_code=status.HTTP_201_CREATED)
def create_file(data: FileCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(db, data.project_id, user)
    return file_service.create_node(db, project, data.path, data.is_folder, data.content)


@router.get("/files/{file_id}", response_model=FileContent)
def read_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    node, _ = _get_owned_file(db, file_id, user)
    content = file_service.read_content(db, node)
    return FileContent(**FileOut.model_validate(node).model_dump(), content=content)


@router.put("/files/{file_id}", response_model=FileOut)
def update_file(file_id: int, data: FileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    node, _ = _get_owned_file(db, file_id, user)
    return file_service.write_content(db, node, data.content)


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    node, project = _get_owned_file(db, file_id, user)
    file_service.delete_node(db, project, node)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
