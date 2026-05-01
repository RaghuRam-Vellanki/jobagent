import os
import json
import shutil
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Profile, Credential, User
from config import RESUME_DIR
from auth_utils import get_current_user
from parsing.resume_parser import parse_resume

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _profile_to_dict(p: Profile) -> dict:
    skills = []
    try:
        skills = json.loads(p.skills) if p.skills else []
    except Exception:
        skills = [s.strip() for s in (p.skills or "").split(",") if s.strip()]
    preferred_cities: list[str] = []
    try:
        preferred_cities = json.loads(p.preferred_cities) if p.preferred_cities else []
        if not isinstance(preferred_cities, list):
            preferred_cities = []
    except Exception:
        preferred_cities = []
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
        # V1 fields
        "persona": p.persona or "early_career",
        "preferred_cities": preferred_cities,
        "graduation_year": p.graduation_year,
        "auto_run_enabled": bool(p.auto_run_enabled),
        "auto_run_time": p.auto_run_time or "09:00",
        # V1.1
        "email_notifications_enabled": bool(p.email_notifications_enabled),
        "notification_email": p.notification_email or "",
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
        # V1 scalar fields
        "persona", "graduation_year", "auto_run_enabled", "auto_run_time",
        # V1.1 email
        "email_notifications_enabled", "notification_email",
    }
    for key, val in payload.items():
        if key in field_map:
            setattr(p, key, val)
        elif key == "skills" and isinstance(val, list):
            p.skills = json.dumps(val)
        elif key == "search_keywords" and isinstance(val, list):
            p.search_keywords = ",".join(val)
        elif key == "preferred_cities" and isinstance(val, list):
            cities = [str(c).strip() for c in val if str(c).strip()]
            p.preferred_cities = json.dumps(cities)

    db.commit()
    return _profile_to_dict(p)


@router.post("/resume")
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_dir = os.path.join(RESUME_DIR, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)
    filename = os.path.basename(file.filename or "resume.pdf")
    dest = os.path.join(user_dir, filename)
    rel_path = f"resume/{current_user.id}/{filename}"

    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except PermissionError:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot overwrite {filename} — close the file in any PDF viewer and retry.",
        )

    p = db.query(Profile).filter_by(user_id=current_user.id).first()
    if p is None:
        p = Profile(user_id=current_user.id, resume_path=rel_path)
        db.add(p)
    else:
        p.resume_path = rel_path

    # Parse the PDF and auto-fill blank profile fields. Never overwrite
    # values the user has already typed.
    parsed = parse_resume(dest)
    autofilled = []
    string_fields = ("full_name", "email", "phone", "city", "current_title", "portfolio_url")
    for k in string_fields:
        if parsed.get(k) and not (getattr(p, k, "") or "").strip():
            setattr(p, k, parsed[k])
            autofilled.append(k)
    if parsed.get("years_of_experience") and not (p.years_of_experience or 0):
        p.years_of_experience = parsed["years_of_experience"]
        autofilled.append("years_of_experience")
    if parsed.get("skills") and not (p.skills or "").strip():
        p.skills = json.dumps(parsed["skills"])
        autofilled.append("skills")

    db.commit()

    return {
        "ok": True,
        "resume_path": rel_path,
        "parsed": parsed,
        "autofilled_fields": autofilled,
    }


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
    # Only overwrite password when a non-empty value is sent. Empty string is
    # treated as "user didn't re-enter password" — preserve what's stored.
    if "password" in payload and payload["password"]:
        c.password = payload["password"]
    db.commit()
    return {"ok": True, "platform": platform}
