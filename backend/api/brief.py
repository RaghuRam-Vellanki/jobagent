"""V1.3 Daily Brief API.

Endpoints:
  POST /api/brief/run         — trigger a brief on demand
  GET  /api/brief/history     — recent BriefRun rows
  GET  /api/brief/{id}/download — download the xlsx attached to a run
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User, BriefRun
from auth_utils import get_current_user

router = APIRouter(prefix="/api/brief", tags=["brief"])
logger = logging.getLogger("api.brief")


def _start_brief_thread(user_id: int, platforms: list[str] | None) -> threading.Thread:
    """Run the brief on a dedicated event loop in a daemon thread.
    Same pattern as api.agent._start_agent_thread — needed on Windows to keep
    Playwright happy (ProactorEventLoop)."""
    def _target():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from brief.orchestrator import run_brief
            result = loop.run_until_complete(run_brief(user_id, platforms=platforms))
            logger.info(f"[brief] user={user_id} done: {result}")
        except Exception as e:
            logger.exception(f"[brief] user={user_id} crashed: {e}")
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True, name=f"brief-u{user_id}")
    t.start()
    return t


@router.post("/run")
async def run_brief_now(
    payload: dict = Body(default={}),
    current_user: User = Depends(get_current_user),
):
    """Kicks off the brief in the background. Returns immediately with 'queued'."""
    platforms = payload.get("platforms")
    if platforms is not None and not isinstance(platforms, list):
        raise HTTPException(400, "platforms must be a list of strings or null")

    _start_brief_thread(current_user.id, platforms)
    return {"ok": True, "queued": True, "user_id": current_user.id}


@router.get("/history")
def list_briefs(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(BriefRun)
        .filter(BriefRun.user_id == current_user.id)
        .order_by(BriefRun.started_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [
        {
            "id": r.id,
            "platforms": r.platforms,
            "jobs_count": r.jobs_count,
            "top_score": r.top_score,
            "email_sent": bool(r.email_sent),
            "email_to": r.email_to,
            "error_msg": r.error_msg,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "duration_ms": r.duration_ms,
            "has_xlsx": bool(r.xlsx_path and os.path.exists(r.xlsx_path)),
        }
        for r in rows
    ]


@router.get("/{run_id}/download")
def download_brief_xlsx(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(BriefRun).filter_by(id=run_id, user_id=current_user.id).first()
    if not row:
        raise HTTPException(404, "Brief run not found")
    if not row.xlsx_path or not os.path.exists(row.xlsx_path):
        raise HTTPException(410, "Excel file no longer available on disk")
    return FileResponse(
        row.xlsx_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(row.xlsx_path),
    )
