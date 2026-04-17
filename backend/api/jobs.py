from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from db.database import get_db
from db.models import Job, User
from auth_utils import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_to_dict(j: Job) -> dict:
    return {
        "id": j.id,
        "job_id": j.job_id,
        "platform": j.platform,
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "url": j.url,
        "match_score": j.match_score,
        "ats_score": j.ats_score,
        "matched_kws": j.matched_kws.split(",") if j.matched_kws else [],
        "ats_gaps": j.ats_gaps.split(",") if j.ats_gaps else [],
        "status": j.status,
        "skip_reason": j.skip_reason,
        "notes": j.notes,
        "response_status": j.response_status,
        "follow_up_date": j.follow_up_date.isoformat() if j.follow_up_date else None,
        "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
        "applied_at": j.applied_at.isoformat() if j.applied_at else None,
    }


@router.get("")
def list_jobs(
    status: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Job).filter(Job.user_id == current_user.id)
    if status:
        statuses = status.upper().split(",")
        q = q.filter(Job.status.in_(statuses))
    if platform:
        q = q.filter(Job.platform == platform.lower())
    total = q.count()
    jobs = q.order_by(Job.match_score.desc(), Job.discovered_at.desc()) \
             .offset(offset).limit(limit).all()
    return {"total": total, "jobs": [_job_to_dict(j) for j in jobs]}


@router.post("/{job_id}/approve")
def approve_job(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    j = db.query(Job).filter_by(user_id=current_user.id, job_id=job_id).first()
    if not j:
        return {"error": "not found"}
    j.status = "APPROVED"
    db.commit()
    return {"ok": True, "job_id": job_id, "status": "APPROVED"}


@router.post("/{job_id}/reject")
def reject_job(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    j = db.query(Job).filter_by(user_id=current_user.id, job_id=job_id).first()
    if not j:
        return {"error": "not found"}
    j.status = "SKIPPED"
    db.commit()
    return {"ok": True, "job_id": job_id, "status": "SKIPPED"}


@router.patch("/{job_id}")
def update_job(job_id: str, payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    j = db.query(Job).filter_by(user_id=current_user.id, job_id=job_id).first()
    if not j:
        return {"error": "not found"}
    allowed = {"notes", "response_status", "follow_up_date", "status"}
    for key, val in payload.items():
        if key in allowed:
            setattr(j, key, val)
    db.commit()
    return _job_to_dict(j)


@router.delete("/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    j = db.query(Job).filter_by(user_id=current_user.id, job_id=job_id).first()
    if not j:
        return {"error": "not found"}
    db.delete(j)
    db.commit()
    return {"ok": True}
