"""User registration and login."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User
from auth_utils import hash_password, verify_password, create_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(payload: dict, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 characters")
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(status_code=409, detail="email already registered")
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "access_token": create_token(user.id),
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
    }


@router.post("/login")
def login(payload: dict, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    user = db.query(User).filter_by(email=email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "access_token": create_token(user.id),
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
    }


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"user_id": current_user.id, "email": current_user.email}
