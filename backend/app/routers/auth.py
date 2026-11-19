from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Role, User
from ..schemas import AuthOut, LoginIn, ProfileUpdate, RegisterIn, UserOut
from ..security import create_access_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User.user_id).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "An account with this email already exists")
    user = User(name=body.name.strip(), email=body.email.lower(), phone=body.phone, password_hash=hash_password(body.password), role=Role.customer)
    db.add(user)
    db.commit()
    return AuthOut(access_token=create_access_token(user), user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return AuthOut(access_token=create_access_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name.strip()
    if body.phone is not None:
        user.phone = body.phone
    db.commit()
    return user
