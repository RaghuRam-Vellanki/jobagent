import json
import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Profile, Job, User
from scoring.semantic_scorer import score_ats, DEFAULT_SKILLS
from config import RESUME_DIR
from auth_utils import get_current_user

router = APIRouter(prefix="/api/ats", tags=["ats"])


def _get_skills(db: Session, user_id: int) -> list[str]:
    p = db.query(Profile).filter_by(user_id=user_id).first()
    if p and p.skills:
        try:
            return json.loads(p.skills)
        except Exception:
            pass
    return DEFAULT_SKILLS


def _read_resume_text(resume_path: str) -> str:
    if not resume_path:
        return ""
    if not os.path.isabs(resume_path):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        resume_path = os.path.join(root, resume_path)
    if not os.path.exists(resume_path):
        return ""
    try:
        from pdfminer.high_level import extract_text
        return extract_text(resume_path)
    except Exception:
        return ""


@router.post("/score")
def score_job_ats(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job_description = payload.get("description", "")
    if not job_description:
        return {"error": "description required"}
    skills = _get_skills(db, current_user.id)
    p = db.query(Profile).filter_by(user_id=current_user.id).first()
    resume_text = _read_resume_text(p.resume_path if p else "")
    return score_ats(resume_text, job_description, skills)


@router.post("/score-all")
def score_all_queued(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    skills = _get_skills(db, current_user.id)
    p = db.query(Profile).filter_by(user_id=current_user.id).first()
    resume_text = _read_resume_text(p.resume_path if p else "")
    jobs = db.query(Job).filter(
        Job.user_id == current_user.id,
        Job.status == "QUEUED",
        Job.ats_score == None,
    ).limit(50).all()
    updated = 0
    for j in jobs:
        result = score_ats(resume_text, j.description or "", skills)
        j.ats_score = result["score"]
        j.ats_gaps = ",".join(result["missing"])
        updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/gap-report")
def gap_report(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from collections import Counter
    from datetime import datetime, timedelta

    week_ago = datetime.utcnow() - timedelta(days=7)
    jobs = db.query(Job).filter(
        Job.user_id == current_user.id,
        Job.discovered_at >= week_ago,
        Job.ats_gaps != None,
    ).all()

    gap_counter: Counter = Counter()
    for j in jobs:
        if j.ats_gaps:
            for kw in j.ats_gaps.split(","):
                kw = kw.strip()
                if kw:
                    gap_counter[kw] += 1

    top_gaps = [{"keyword": kw, "count": cnt} for kw, cnt in gap_counter.most_common(20)]
    return {
        "jobs_analyzed": len(jobs),
        "top_gaps": top_gaps,
        "suggestion": (
            f"Add these {len(top_gaps)} keywords to your resume for better ATS matches."
            if top_gaps else "Your resume covers the most common job keywords well."
        ),
    }
