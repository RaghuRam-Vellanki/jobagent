import os
import json
import shutil
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Profile, Credential, User
from config import RESUME_DIR
from auth_utils import get_current_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _profile_to_dict(p: Profile) -> dict:
    skills = []
    try:
        skills = json.loads(p.skills) if p.skills else []
    except Exception:
        skills = [s.strip() for s in (p.skills or "").split(",") if s.strip()]
    return {
        "id": p.id,
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "city": p.city,
        "state": p.state,
        "country": p.country,
        "current_title": p.current_title,
        "years_of_experience": p.years_of_experience,
        "notice_period": p.notice_period,
        "expected_salary": p.expected_salary,
        "portfolio_url": p.portfolio_url,
        "resume_path": p.resume_path,
        "cover_letter_template": p.cover_letter_template,
        "skills": skills,
        "search_keywords": [k.strip() for k in (p.search_keywords or "").split(",") if k.strip()],
        "location_filter": p.location_filter,
        "experience_level": p.experience_level,
        "job_type": p.job_type,
        "date_posted": p.date_posted,
        "match_threshold": p.match_threshold,
        "daily_queue_limit": p.daily_queue_limit,
        "daily_apply_limit": p.daily_apply_limit,
        "delay_min": p.delay_min,
        "delay_max": p.delay_max,
    }


@router.get("")
def get_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Profile).filter_by(user_id=current_user.id).first()
    if not p:
        return {}
    return _profile_to_dict(p)


@router.put("")
def update_profile(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = db.query(Profile).filter_by(user_id=current_user.id).first()
    if not p:
        p = Profile(user_id=current_user.id)
        db.add(p)

    field_map = {
        "full_name", "email", "phone", "city", "state", "country",
        "current_title", "years_of_experience", "notice_period", "expected_salary",
        "portfolio_url", "cover_letter_template", "location_filter",
        "experience_level", "job_type", "date_posted", "match_threshold",
        "daily_queue_limit", "daily_apply_limit", "delay_min", "delay_max",
    }
    for key, val in payload.items():
        if key in field_map:
            setattr(p, key, val)
        elif key == "skills" and isinstance(val, list):
            p.skills = json.dumps(val)
        elif key == "search_keywords" and isinstance(val, list):
            p.search_keywords = ",".join(val)

    db.commit()
    return _profile_to_dict(p)


@router.post("/resume")
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    os.makedirs(RESUME_DIR, exist_ok=True)
    filename = file.filename or "resume.pdf"
    dest = os.path.join(RESUME_DIR, filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    p = db.query(Profile).filter_by(user_id=current_user.id).first()
    if p:
        p.resume_path = f"resume/{filename}"
        db.commit()

    return {"ok": True, "resume_path": f"resume/{filename}"}


@router.get("/credentials/{platform}")
def get_credentials(platform: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    c = db.query(Credential).filter_by(user_id=current_user.id, platform=platform).first()
    if not c:
        return {"platform": platform, "email": "", "has_password": False}
    return {"platform": platform, "email": c.email, "has_password": bool(c.password)}


@router.put("/credentials/{platform}")
def set_credentials(platform: str, payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    c = db.query(Credential).filter_by(user_id=current_user.id, platform=platform).first()
    if not c:
        c = Credential(user_id=current_user.id, platform=platform)
        db.add(c)
    if "email" in payload:
        c.email = payload["email"]
    if "password" in payload:
        c.password = payload["password"]
    db.commit()
    return {"ok": True, "platform": platform}
