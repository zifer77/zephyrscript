from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import file_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/projects", tags=["projects"])


def get_owned_project(db: Session, project_id: int, user: User) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project tidak ditemukan")
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Project).filter(Project.owner_id == user.id).order_by(Project.updated_at.desc()).all()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = Project(name=data.name, description=data.description, owner_id=user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    file_service.init_project_files(db, project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_owned_project(db, project_id, user)


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int, data: ProjectUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    project = get_owned_project(db, project_id, user)
    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(db, project_id, user)
    pid = project.id
    db.delete(project)
    db.commit()
    file_service.delete_project_dir(pid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
