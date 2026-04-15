from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, timedelta

from db.database import get_db
from db.models import DailyStats, Job

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats(days: int = 7, db: Session = Depends(get_db)):
    today = date.today()
    result = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        s = db.query(DailyStats).filter_by(date=d).first()
        result.append({
            "date": d,
            "discovered": s.discovered if s else 0,
            "queued": s.queued if s else 0,
            "approved": s.approved if s else 0,
            "applied": s.applied if s else 0,
            "skipped": s.skipped if s else 0,
            "failed": s.failed if s else 0,
        })
    return result


@router.get("/totals")
def get_totals(db: Session = Depends(get_db)):
    counts = {}
    for status in ["QUEUED", "APPROVED", "APPLIED", "SKIPPED", "FAILED", "DUPLICATE"]:
        counts[status.lower()] = db.query(Job).filter_by(status=status).count()
    counts["total"] = db.query(Job).count()

    # Response status breakdown
    for rs in ["no_response", "viewed", "interview", "rejected", "offer"]:
        counts[f"response_{rs}"] = (
            db.query(Job).filter_by(status="APPLIED", response_status=rs).count()
        )

    # Platform breakdown
    platforms = {}
    for p in ["linkedin", "naukri", "internshala", "unstop"]:
        platforms[p] = db.query(Job).filter_by(platform=p).count()
    counts["by_platform"] = platforms

    return counts
