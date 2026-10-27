from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Nama tidak boleh kosong")
    return v


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)

    @field_validator("name")
    @classmethod
    def _n(cls, v: str) -> str:
        return _clean_name(v)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def _n(cls, v: str | None) -> str | None:
        return _clean_name(v) if v is not None else v


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
