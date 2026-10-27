from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserOut
from app.services import auth_service
from app.utils.rate_limit import limiter
from app.utils.security import create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth)
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    return auth_service.register_user(db, data)


@router.post("/login", response_model=Token)
@limiter.limit(settings.rate_limit_auth)
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, data.username, data.password)
    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Username atau password salah", headers={"WWW-Authenticate": "Bearer"}
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(auth_service.get_current_user)):
    return user
