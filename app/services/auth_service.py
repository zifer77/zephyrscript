from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate
from app.utils.security import decode_token, hash_password, verify_password

_bearer = HTTPBearer(auto_error=False)

# Hash dummy agar waktu respons login tetap konstan saat username tidak ada.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def register_user(db: Session, data: UserCreate) -> User:
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registrasi dinonaktifkan")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username sudah dipakai")
    user = User(username=data.username, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


def user_from_token(db: Session, token: str | None, scope: str = "access") -> User | None:
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("scope") != scope:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    return db.get(User, user_id)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Token tidak valid atau kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    user = user_from_token(db, creds.credentials if creds else None)
    if not user:
        raise _unauthorized()
    return user


def get_current_user_flex(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Header Authorization ATAU ?token= (untuk iframe/preview yang tak bisa kirim header)."""
    token = creds.credentials if creds else request.query_params.get("token")
    user = user_from_token(db, token)
    if not user:
        raise _unauthorized()
    return user
