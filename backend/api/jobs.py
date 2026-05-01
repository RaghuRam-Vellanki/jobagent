import csv
import io
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
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


@router.get("/export.csv")
def export_csv(
    status: Optional[str] = Query("APPLIED", description="Comma-separated status filter; default APPLIED"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """E6-S3: download all jobs (default: APPLIED) as a UTF-8 CSV."""
    q = db.query(Job).filter(Job.user_id == current_user.id)
    if status:
        statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
        if statuses:
            q = q.filter(Job.status.in_(statuses))
    rows = q.order_by(Job.applied_at.desc().nullslast(), Job.discovered_at.desc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "title", "company", "platform", "location", "status",
        "match_score", "ats_score", "applied_at", "response_status",
        "url", "matched_kws",
    ])
    for j in rows:
        writer.writerow([
            j.title or "",
            j.company or "",
            j.platform or "",
            j.location or "",
            j.status or "",
            j.match_score if j.match_score is not None else "",
            j.ats_score if j.ats_score is not None else "",
            j.applied_at.isoformat() if j.applied_at else "",
            j.response_status or "",
            j.url or "",
            (j.matched_kws or "").replace(",", "|"),
        ])

    buf.seek(0)
    filename = f"jobagent-export-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


# Bulk approve must be declared BEFORE the /{job_id}/approve route, otherwise
# FastAPI matches "approve-all" as a job_id and returns 405.
@router.post("/approve-all")
def approve_all(
    min_score: float = Query(0, description="Only approve QUEUED jobs with match_score >= this"),
    platform: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Job).filter(
        Job.user_id == current_user.id,
        Job.status == "QUEUED",
        Job.match_score >= min_score,
    )
    if platform:
        q = q.filter(Job.platform == platform.lower())
    matched = q.all()
    for j in matched:
        j.status = "APPROVED"
    db.commit()
    return {"ok": True, "approved": len(matched), "min_score": min_score}


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
