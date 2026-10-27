from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.path_sanitizer import PathError, normalize_rel_path


class FileCreate(BaseModel):
    project_id: int
    path: str = Field(description="Path relatif, mis. 'src/index.js'")
    is_folder: bool = False
    content: str = ""

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        try:
            return normalize_rel_path(v)
        except PathError as e:
            raise ValueError(str(e))


class FileUpdate(BaseModel):
    content: str


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    path: str
    name: str
    is_folder: bool
    created_at: datetime
    updated_at: datetime


class FileContent(FileOut):
    content: str


class FileTreeNode(BaseModel):
    id: int
    name: str
    path: str
    is_folder: bool
    children: list[FileTreeNode] = []


FileTreeNode.model_rebuild()
