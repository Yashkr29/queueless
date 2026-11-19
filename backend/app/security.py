from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Role, Staff, User

settings = get_settings()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user.user_id), "role": user.role.value, "exp": exp}, settings.jwt_secret,
                      algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def user_from_token(db: Session, token: str) -> User | None:
    payload = decode_token(token)
    if not payload:
        return None
    try:
        return db.get(User, int(payload["sub"]))
    except (KeyError, ValueError):
        return None


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    user = user_from_token(db, creds.credentials)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_roles(*roles: Role):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user
    return dep


_staff_or_admin = require_roles(Role.staff, Role.admin)


def staff_user(user: User = Depends(_staff_or_admin), db: Session = Depends(get_db)) -> User:
    """Admins may operate on any organization (X-Location-Id); staff are pinned to the one they work at."""
    if user.role == Role.staff:
        st = db.scalar(select(Staff).where(Staff.user_id == user.user_id))
        if st and st.location_id:
            db.info["location_id"] = st.location_id
            db.info["restrict_location"] = st.location_id
    return user
admin_user = require_roles(Role.admin)
