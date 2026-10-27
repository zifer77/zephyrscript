import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


class UserCreate(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError("Username 3-32 karakter: huruf, angka, underscore")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password minimal 8 karakter")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password maksimal 72 byte (batas bcrypt)")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
