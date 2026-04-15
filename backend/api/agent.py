"""
Agent API — start/stop/pause agents, stream live log via WebSocket.
Orchestrates multi-platform discovery and apply phases.
"""
import asyncio
import json
import logging
import random
from datetime import datetime, date
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from db.database import get_db, SessionLocal
from db.models import Job, DailyStats, Profile, Credential
from scoring.semantic_scorer import score_job, DEFAULT_SKILLS
from agents.linkedin_agent import LinkedInAgent
from agents.naukri_agent import NaukriAgent
from agents.internshala_agent import IntersthalaAgent
from agents.unstop_agent import UnstopAgent

router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger("agent.orchestrator")

# ── Shared state (in-process, single worker) ──────────────────────────
state: dict[str, Any] = {
    "running": False,
    "phase": "idle",       # idle | discovering | waiting | applying
    "paused": False,
    "today_discovered": 0,
    "today_queued": 0,
    "today_approved": 0,
    "today_applied": 0,
    "today_skipped": 0,
    "today_failed": 0,
    "current_job": "",
    "last_update": "",
    "log": [],
    "error": None,
}

# Connected WebSocket clients
_ws_clients: list[WebSocket] = []
_agent_task: asyncio.Task | None = None


def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    state["log"].append(line)
    if len(state["log"]) > 500:
        state["log"] = state["log"][-500:]
    state["last_update"] = ts
    logger.info(msg)
    # Broadcast to WebSocket clients — only schedule if loop is running
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast({"type": "log", "message": line}))
    except RuntimeError:
        pass  # no running loop (e.g. during startup), skip broadcast


async def _broadcast(data: dict):
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


def _today() -> str:
    return date.today().isoformat()


def _get_or_create_stats(db: Session) -> DailyStats:
    s = db.query(DailyStats).filter_by(date=_today()).first()
    if not s:
        s = DailyStats(date=_today())
        db.add(s)
        db.commit()
    return s


def _inc_stat(db: Session, field: str, n: int = 1):
    s = _get_or_create_stats(db)
    setattr(s, field, getattr(s, field, 0) + n)
    db.commit()
    state[f"today_{field}"] = getattr(s, field)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast({"type": "stats", "state": {k: v for k, v in state.items() if k != "log"}}))
    except RuntimeError:
        pass


def _save_job(db: Session, info: dict, status: str, score: float = 0,
              matched: list | None = None, skip_reason: str | None = None):
    try:
        j = Job(
            job_id=info.get("job_id", ""),
            platform=info.get("platform", "linkedin"),
            title=info.get("title", ""),
            company=info.get("company", ""),
            location=info.get("location", ""),
            url=info.get("url", ""),
            description=(info.get("description", "") or "")[:4000],
            match_score=score,
            matched_kws=",".join(matched or []),
            status=status,
            skip_reason=skip_reason,
            discovered_at=datetime.utcnow(),
        )
        db.add(j)
        db.commit()
    except Exception as e:
        logger.error(f"[DB] save_job: {e}")
        db.rollback()


def _get_profile_dict(db: Session) -> dict:
    p = db.query(Profile).first()
    if not p:
        return {}
    skills = []
    try:
        skills = json.loads(p.skills) if p.skills else DEFAULT_SKILLS
    except Exception:
        skills = DEFAULT_SKILLS
    return {
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "city": p.city,
        "years_of_experience": p.years_of_experience,
        "expected_salary": p.expected_salary,
        "portfolio_url": p.portfolio_url,
        "resume_path": p.resume_path,
        "cover_letter_template": p.cover_letter_template,
        "notice_period": p.notice_period,
        "search_keywords": [k.strip() for k in (p.search_keywords or "").split(",") if k.strip()],
        "location_filter": p.location_filter or "India",
        "date_posted": p.date_posted or "r86400",
        "match_threshold": p.match_threshold or 60,
        "daily_queue_limit": p.daily_queue_limit or 50,
        "daily_apply_limit": p.daily_apply_limit or 25,
        "delay_min": p.delay_min or 4,
        "delay_max": p.delay_max or 10,
        "skills": skills,
    }


def _get_credentials(db: Session, platform: str) -> dict:
    c = db.query(Credential).filter_by(platform=platform).first()
    return {
        "email": c.email if c else "",
        "password": c.password if c else "",
        "login_mode": "manual" if platform == "linkedin" else "auto",
    }


# ── Discovery orchestrator ────────────────────────────────────────────

async def _run_discovery(platforms: list[str]):
    db = SessionLocal()
    try:
        profile = _get_profile_dict(db)
        keywords = profile.get("search_keywords", ["Product Manager"])
        location = profile.get("location_filter", "India")
        threshold = profile.get("match_threshold", 60)
        queue_limit = profile.get("daily_queue_limit", 50)
        skills = profile.get("skills", DEFAULT_SKILLS)
        filters = {"date_posted": profile.get("date_posted", "r86400")}

        queued_today = 0
        agent_classes = {
            "linkedin": LinkedInAgent,
            "naukri": NaukriAgent,
            "internshala": IntersthalaAgent,
            "unstop": UnstopAgent,
        }

        for platform in platforms:
            if not state["running"]:
                break
            if queued_today >= queue_limit:
                break

            AgentClass = agent_classes.get(platform)
            if not AgentClass:
                continue

            credentials = _get_credentials(db, platform)
            agent = AgentClass(profile=profile, credentials=credentials)

            _log(f"🔍 Starting {platform.capitalize()} discovery...")
            try:
                headless = platform != "linkedin"
                await agent.start(headless=headless)
                logged_in = await agent.login()
                if not logged_in:
                    _log(f"❌ {platform.capitalize()} login failed — skipping")
                    continue

                _log(f"✅ {platform.capitalize()} logged in")

                per_platform_limit = max(10, (queue_limit - queued_today) // max(len(platforms), 1))
                raw_jobs = await agent.search_jobs(
                    keywords=keywords,
                    location=location,
                    filters=filters,
                    max_jobs=per_platform_limit + 10,
                )

                _log(f"📋 {platform.capitalize()}: found {len(raw_jobs)} raw jobs")
                _inc_stat(db, "discovered", len(raw_jobs))

                for job in raw_jobs:
                    if not state["running"]:
                        break
                    while state["paused"]:
                        await asyncio.sleep(2)
                    if queued_today >= queue_limit:
                        break

                    job_id = job.get("job_id")
                    if not job_id:
                        continue

                    # Duplicate check
                    if db.query(Job).filter_by(job_id=job_id).first():
                        continue

                    # Fetch description if missing
                    if not job.get("description") and hasattr(agent, "get_description") and job.get("url"):
                        try:
                            job["description"] = await agent.get_description(job["url"])
                        except Exception:
                            pass

                    # Semantic score
                    score, matched, skip_reason = score_job(
                        job.get("title", ""),
                        job.get("description", ""),
                        job.get("company", ""),
                        candidate_skills=skills,
                    )

                    if skip_reason:
                        _save_job(db, job, "SKIPPED", score, matched, skip_reason)
                        _inc_stat(db, "skipped")
                        continue

                    if score < threshold:
                        _save_job(db, job, "SKIPPED", score, matched, f"low_score:{score}")
                        _inc_stat(db, "skipped")
                        continue

                    _save_job(db, job, "QUEUED", score, matched)
                    _inc_stat(db, "queued")
                    queued_today += 1
                    state["today_queued"] = queued_today
                    _log(f"✅ Queued [{score}]: {job['title']} @ {job['company']} [{platform}]")

                    await asyncio.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                _log(f"💥 {platform.capitalize()} error: {e}")
                logger.exception(e)
            finally:
                await agent.stop()

        _log(f"🏁 Discovery done. Queued {queued_today} jobs.")
        state["phase"] = "waiting"
    finally:
        db.close()


# ── Apply orchestrator ────────────────────────────────────────────────

async def _run_apply():
    db = SessionLocal()
    try:
        profile = _get_profile_dict(db)
        apply_limit = profile.get("daily_apply_limit", 25)
        delay_min = profile.get("delay_min", 4)
        delay_max = profile.get("delay_max", 10)
        credentials = _get_credentials(db, "linkedin")

        agent = LinkedInAgent(profile=profile, credentials=credentials)
        await agent.start(headless=False)

        _log("🔐 Logging into LinkedIn for apply phase...")
        if not await agent.login():
            _log("❌ LinkedIn login failed — cannot apply.")
            return

        applied_today = 0
        state["phase"] = "applying"

        while state["running"]:
            while state["paused"]:
                await asyncio.sleep(2)

            if applied_today >= apply_limit:
                _log(f"🎯 Daily apply limit ({apply_limit}) reached.")
                break

            job = db.query(Job).filter_by(status="APPROVED").order_by(
                Job.match_score.desc()
            ).first()

            if not job:
                await asyncio.sleep(5)
                db.expire_all()
                continue

            state["current_job"] = f"{job.title} @ {job.company}"
            asyncio.get_running_loop().create_task(_broadcast({"type": "stats", "state": {k: v for k, v in state.items() if k != "log"}}))
            _log(f"🚀 Applying [{job.match_score}]: {job.title} @ {job.company}")

            result = await agent.apply_to_job({
                "job_id": job.job_id, "title": job.title, "company": job.company,
                "url": job.url, "description": job.description,
            })

            if result == "applied":
                job.status = "APPLIED"
                job.applied_at = datetime.utcnow()
                db.commit()
                _inc_stat(db, "applied")
                applied_today += 1
                _log(f"✅ Applied: {job.title} [{applied_today}/{apply_limit}]")
            elif result == "failed":
                job.status = "FAILED"
                db.commit()
                _inc_stat(db, "failed")
                _log(f"❌ Failed: {job.title}")
            elif result == "skipped":
                job.status = "SKIPPED"
                job.skip_reason = "no_easy_apply_btn"
                db.commit()
                _inc_stat(db, "skipped")

            await asyncio.sleep(random.uniform(delay_min, delay_max))

        await agent.stop()
        state["phase"] = "idle"
        state["current_job"] = ""
        _log(f"🏁 Apply phase done. Applied: {applied_today}")
    finally:
        db.close()


async def _run_agent_task(phase: str, platforms: list[str]):
    state["running"] = True
    state["paused"] = False
    state["error"] = None

    try:
        if phase in ("discover", "full"):
            state["phase"] = "discovering"
            await _run_discovery(platforms)
        if phase in ("apply", "full") and state["running"]:
            await _run_apply()
    except Exception as e:
        state["error"] = str(e)
        _log(f"💥 Agent crashed: {e}")
        logger.exception(e)
    finally:
        state["running"] = False
        state["phase"] = "idle"
        state["current_job"] = ""
        try:
            asyncio.get_running_loop().create_task(_broadcast({"type": "stats", "state": {k: v for k, v in state.items() if k != "log"}}))
        except RuntimeError:
            pass


# ── REST endpoints ────────────────────────────────────────────────────

@router.get("/state")
def get_state():
    return {k: v for k, v in state.items() if k != "log"}


@router.get("/log")
def get_log(limit: int = 100):
    return {"log": state["log"][-limit:]}


@router.post("/start/discover")
async def start_discover(payload: dict = {}):
    global _agent_task
    if state["running"]:
        return {"error": "Agent already running"}
    platforms = payload.get("platforms", ["linkedin", "naukri", "internshala", "unstop"])
    _agent_task = asyncio.create_task(_run_agent_task("discover", platforms))
    return {"ok": True, "phase": "discover", "platforms": platforms}


@router.post("/start/apply")
async def start_apply():
    global _agent_task
    if state["running"]:
        return {"error": "Agent already running"}
    _agent_task = asyncio.create_task(_run_agent_task("apply", []))
    return {"ok": True, "phase": "apply"}


@router.post("/stop")
async def stop_agent():
    state["running"] = False
    state["paused"] = False
    return {"ok": True}


@router.post("/pause")
async def pause_agent():
    state["paused"] = not state["paused"]
    return {"ok": True, "paused": state["paused"]}


# ── WebSocket live log ────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    # Send current state on connect
    await ws.send_json({"type": "init", "state": state})
    try:
        while True:
            # Keep connection alive, handle ping
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in _ws_clients:
            _ws_clients.remove(ws)
