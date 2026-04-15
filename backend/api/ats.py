import json
import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Profile, Job
from scoring.semantic_scorer import score_ats, DEFAULT_SKILLS
from config import RESUME_DIR

router = APIRouter(prefix="/api/ats", tags=["ats"])


def _get_skills(db: Session) -> list[str]:
    p = db.query(Profile).first()
    if p and p.skills:
        try:
            return json.loads(p.skills)
        except Exception:
            pass
    return DEFAULT_SKILLS


def _read_resume_text(resume_path: str) -> str:
    """Extract text from resume PDF using pdfminer."""
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
def score_job_ats(payload: dict, db: Session = Depends(get_db)):
    """Score a job description against the user's resume + skills."""
    job_description = payload.get("description", "")
    if not job_description:
        return {"error": "description required"}

    skills = _get_skills(db)
    p = db.query(Profile).first()
    resume_text = _read_resume_text(p.resume_path if p else "")

    result = score_ats(resume_text, job_description, skills)
    return result


@router.post("/score-all")
def score_all_queued(db: Session = Depends(get_db)):
    """Batch-score all QUEUED jobs that don't have an ATS score yet."""
    skills = _get_skills(db)
    p = db.query(Profile).first()
    resume_text = _read_resume_text(p.resume_path if p else "")

    jobs = db.query(Job).filter(Job.status == "QUEUED", Job.ats_score == None).limit(50).all()
    updated = 0
    for j in jobs:
        result = score_ats(resume_text, j.description or "", skills)
        j.ats_score = result["score"]
        j.ats_gaps = ",".join(result["missing"])
        updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/gap-report")
def gap_report(db: Session = Depends(get_db)):
    """Aggregate missing keywords across all scored jobs this week."""
    from collections import Counter
    from datetime import datetime, timedelta

    week_ago = datetime.utcnow() - timedelta(days=7)
    jobs = db.query(Job).filter(Job.discovered_at >= week_ago, Job.ats_gaps != None).all()

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
