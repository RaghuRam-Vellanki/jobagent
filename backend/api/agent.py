"""
Agent API — start/stop/pause agents, stream live log via WebSocket.
Multi-tenant: each user has isolated state. Max 3 concurrent browsers (semaphore).
"""
import asyncio
import json
import logging
import random
import sys
import threading
from datetime import datetime, date
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from db.database import get_db, SessionLocal
from db.models import Job, DailyStats, Profile, Credential, User
from scoring.semantic_scorer import score_job, DEFAULT_SKILLS
from agents.linkedin_agent import LinkedInAgent
from agents.naukri_agent import NaukriAgent
from agents.ats_aggregator_agent import ATSAggregatorAgent
# Internshala + Unstop descoped 2026-04-26 — files retained for reversibility
from auth_utils import get_current_user, decode_token

router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger("agent.orchestrator")

# ── Per-user state ────────────────────────────────────────────────────
_state: dict[int, dict[str, Any]] = {}
_ws_clients: dict[int, list[WebSocket]] = {}
_agent_threads: dict[int, threading.Thread] = {}

# Max 3 concurrent Playwright browser instances across all users
_browser_semaphore = threading.Semaphore(3)

# Main uvicorn event loop (captured on first request)
_main_loop: asyncio.AbstractEventLoop | None = None


def _make_fresh_state() -> dict[str, Any]:
    return {
        "running": False,
        "phase": "idle",
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


def _get_user_state(user_id: int) -> dict[str, Any]:
    if user_id not in _state:
        _state[user_id] = _make_fresh_state()
    return _state[user_id]


def _log(msg: str, user_id: int):
    st = _get_user_state(user_id)
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    st["log"].append(line)
    if len(st["log"]) > 500:
        st["log"] = st["log"][-500:]
    st["last_update"] = ts
    logger.info(f"[user={user_id}] {msg}")
    _schedule_broadcast({"type": "log", "message": line}, user_id)


def _schedule_broadcast(data: dict, user_id: int):
    if _main_loop and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(data, user_id), _main_loop)


async def _broadcast(data: dict, user_id: int):
    clients = _ws_clients.get(user_id, [])
    dead = []
    for ws in clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.remove(ws)


def _today() -> str:
    return date.today().isoformat()


def _get_or_create_stats(db: Session, user_id: int) -> DailyStats:
    s = db.query(DailyStats).filter_by(user_id=user_id, date=_today()).first()
    if not s:
        s = DailyStats(user_id=user_id, date=_today())
        db.add(s)
        db.commit()
    return s


def _inc_stat(db: Session, field: str, user_id: int, n: int = 1):
    s = _get_or_create_stats(db, user_id)
    setattr(s, field, getattr(s, field, 0) + n)
    db.commit()
    st = _get_user_state(user_id)
    st[f"today_{field}"] = getattr(s, field)
    _schedule_broadcast({"type": "stats", "state": {k: v for k, v in st.items() if k != "log"}}, user_id)


def _save_job(db: Session, info: dict, status: str, user_id: int,
              score: float = 0, matched: list | None = None, skip_reason: str | None = None):
    try:
        # V1: derive apply_channel — scrapers may set it explicitly; otherwise
        # fall back from the legacy `easy_apply` boolean. Default is "external".
        apply_channel = info.get("apply_channel")
        if not apply_channel:
            apply_channel = "easy_apply" if info.get("easy_apply") else "external"

        j = Job(
            user_id=user_id,
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
            apply_channel=apply_channel,
            external_apply_url=info.get("external_apply_url"),
            discovered_at=datetime.utcnow(),
        )
        db.add(j)
        db.commit()
    except Exception as e:
        logger.error(f"[DB] save_job: {e}")
        db.rollback()


def _get_profile_dict(db: Session, user_id: int) -> dict:
    p = db.query(Profile).filter_by(user_id=user_id).first()
    if not p:
        return {}
    skills = []
    try:
        skills = json.loads(p.skills) if p.skills else DEFAULT_SKILLS
    except Exception:
        skills = DEFAULT_SKILLS
    preferred_cities: list[str] = []
    try:
        preferred_cities = json.loads(p.preferred_cities) if p.preferred_cities else []
        if not isinstance(preferred_cities, list):
            preferred_cities = []
    except Exception:
        preferred_cities = []

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
        # V1 fields used by scorer
        "persona": p.persona or "early_career",
        "preferred_cities": preferred_cities,
        # V1.1 fields used by email notifications
        "email_notifications_enabled": bool(p.email_notifications_enabled),
        "notification_email": p.notification_email or "",
    }


def _get_credentials(db: Session, platform: str, user_id: int) -> dict:
    c = db.query(Credential).filter_by(user_id=user_id, platform=platform).first()
    email = c.email if c else ""
    password = c.password if c else ""
    if platform == "linkedin":
        login_mode = "auto" if (email and password) else "manual"
    else:
        login_mode = "auto"
    return {"email": email, "password": password, "login_mode": login_mode}


# ── Discovery orchestrator ────────────────────────────────────────────

async def _run_discovery(platforms: list[str], user_id: int):
    db = SessionLocal()
    st = _get_user_state(user_id)
    try:
        profile = _get_profile_dict(db, user_id)
        # Use `or` rather than dict.get's default so empty lists from the UI
        # still fall back to sensible defaults (otherwise discovery does nothing).
        keywords = profile.get("search_keywords") or ["Product Manager"]
        location = profile.get("location_filter") or "India"
        threshold = profile.get("match_threshold") or 60
        queue_limit = profile.get("daily_queue_limit") or 50
        filters = {"date_posted": profile.get("date_posted", "r86400")}

        queued_today = 0
        agent_classes = {
            "linkedin": LinkedInAgent,
            "naukri": NaukriAgent,
            "ats": ATSAggregatorAgent,
        }

        for platform in platforms:
            if not st["running"]:
                break
            if queued_today >= queue_limit:
                break

            AgentClass = agent_classes.get(platform)
            if not AgentClass:
                continue

            credentials = _get_credentials(db, platform, user_id)
            agent = AgentClass(profile=profile, credentials=credentials)

            _log(f"🔍 Starting {platform.capitalize()} discovery...", user_id)
            try:
                # LinkedIn always needs a visible window for manual login;
                # other platforms can opt in via `requires_visible_browser`
                # (Naukri does — its anti-bot serves a blank SPA to headless).
                headless = not (platform == "linkedin" or getattr(AgentClass, "requires_visible_browser", False))
                await agent.start(headless=headless)
                logged_in = await agent.login()
                if not logged_in:
                    _log(f"❌ {platform.capitalize()} login failed — skipping", user_id)
                    continue

                _log(f"✅ {platform.capitalize()} logged in", user_id)

                per_platform_limit = max(10, (queue_limit - queued_today) // max(len(platforms), 1))
                raw_jobs = await agent.search_jobs(
                    keywords=keywords,
                    location=location,
                    filters=filters,
                    max_jobs=per_platform_limit + 10,
                )

                _log(f"📋 {platform.capitalize()}: found {len(raw_jobs)} raw jobs", user_id)
                _inc_stat(db, "discovered", user_id, len(raw_jobs))

                for job in raw_jobs:
                    if not st["running"]:
                        break
                    while st["paused"]:
                        await asyncio.sleep(2)
                    if queued_today >= queue_limit:
                        break

                    job_id = job.get("job_id")
                    if not job_id:
                        continue

                    if db.query(Job).filter_by(user_id=user_id, job_id=job_id).first():
                        continue

                    if not job.get("description") and hasattr(agent, "get_description") and job.get("url"):
                        try:
                            job["description"] = await agent.get_description(job["url"])
                        except Exception:
                            pass

                    score, matched, skip_reason = score_job(
                        job.get("title", ""),
                        job.get("description", ""),
                        job.get("company", ""),
                        location=job.get("location", ""),
                        profile=profile,
                    )

                    if skip_reason:
                        _save_job(db, job, "SKIPPED", user_id, score, matched, skip_reason)
                        _inc_stat(db, "skipped", user_id)
                        continue

                    if score < threshold:
                        _save_job(db, job, "SKIPPED", user_id, score, matched, f"low_score:{score}")
                        _inc_stat(db, "skipped", user_id)
                        continue

                    _save_job(db, job, "QUEUED", user_id, score, matched)
                    _inc_stat(db, "queued", user_id)
                    queued_today += 1
                    st["today_queued"] = queued_today
                    _log(f"✅ Queued [{score}]: {job['title']} @ {job['company']} [{platform}]", user_id)

                    await asyncio.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                _log(f"💥 {platform.capitalize()} error: {type(e).__name__}: {e}", user_id)
                _log(f"   {tb.splitlines()[-1]}", user_id)
                logger.exception(e)
            finally:
                await agent.stop()

        _log(f"🏁 Discovery done. Queued {queued_today} jobs.", user_id)
        st["phase"] = "waiting"
    finally:
        db.close()


# ── Apply orchestrator ────────────────────────────────────────────────

_APPLY_AGENT_CLASSES = {
    "linkedin": LinkedInAgent,
    "naukri": NaukriAgent,
    "ats": ATSAggregatorAgent,
}


async def _run_apply(user_id: int):
    db = SessionLocal()
    st = _get_user_state(user_id)
    try:
        profile = _get_profile_dict(db, user_id)
        apply_limit = profile.get("daily_apply_limit") or 25
        delay_min = profile.get("delay_min") or 4
        delay_max = profile.get("delay_max") or 10

        applied_today = 0
        st["phase"] = "applying"

        # Group APPROVED jobs by platform so we open one browser per platform
        # instead of restarting it per job. Highest-scoring jobs first.
        approved = db.query(Job).filter_by(user_id=user_id, status="APPROVED") \
            .order_by(Job.match_score.desc()).all()
        if not approved:
            _log("📭 No approved jobs to apply to. Approve some from the Queue first.", user_id)
            return
        by_platform: dict[str, list[Job]] = {}
        for j in approved:
            by_platform.setdefault(j.platform or "linkedin", []).append(j)

        for platform, jobs in by_platform.items():
            if not st["running"]:
                break
            if applied_today >= apply_limit:
                break

            AgentClass = _APPLY_AGENT_CLASSES.get(platform)
            if not AgentClass:
                _log(f"⚠️ No agent for platform '{platform}' — skipping {len(jobs)} job(s)", user_id)
                continue

            credentials = _get_credentials(db, platform, user_id)
            agent = AgentClass(profile=profile, credentials=credentials)
            # LinkedIn always needs a visible window (manual login). Other
            # platforms opt in via requires_visible_browser (Naukri does).
            headless = not (platform == "linkedin" or getattr(AgentClass, "requires_visible_browser", False))
            await agent.start(headless=headless)

            try:
                _log(f"🔐 Logging into {platform.capitalize()} for apply phase...", user_id)
                if not await agent.login():
                    _log(f"❌ {platform.capitalize()} login failed — skipping {len(jobs)} job(s)", user_id)
                    continue
                _log(f"✅ {platform.capitalize()} ready — {len(jobs)} approved job(s)", user_id)

                for job in jobs:
                    if not st["running"]:
                        break
                    while st["paused"]:
                        await asyncio.sleep(2)
                    if applied_today >= apply_limit:
                        _log(f"🎯 Daily apply limit ({apply_limit}) reached.", user_id)
                        break

                    st["current_job"] = f"{job.title} @ {job.company}"
                    _schedule_broadcast({"type": "stats", "state": {k: v for k, v in st.items() if k != "log"}}, user_id)
                    _log(f"🚀 Applying [{job.match_score}]: {job.title} @ {job.company} [{platform}]", user_id)

                    try:
                        result = await agent.apply_to_job({
                            "job_id": job.job_id, "title": job.title, "company": job.company,
                            "url": job.url, "description": job.description,
                        })
                    except Exception as e:
                        logger.exception(e)
                        _log(f"💥 {platform} apply error: {type(e).__name__}: {e}", user_id)
                        result = "failed"

                    if result == "applied":
                        job.status = "APPLIED"
                        job.applied_at = datetime.utcnow()
                        db.commit()
                        _inc_stat(db, "applied", user_id)
                        applied_today += 1
                        _log(f"✅ Applied: {job.title} [{applied_today}/{apply_limit}]", user_id)
                        # E5-S5: per-job email notification (best-effort, never
                        # blocks the apply pipeline)
                        try:
                            from notifications import send_apply_email
                            sent = send_apply_email(profile, {
                                "title": job.title, "company": job.company,
                                "location": job.location, "url": job.url,
                                "platform": job.platform, "match_score": job.match_score,
                                "applied_at": job.applied_at.strftime("%Y-%m-%d %H:%M UTC"),
                            })
                            if sent:
                                _log(f"✉️  Email sent for {job.title}", user_id)
                        except Exception as e:
                            logger.debug(f"email notify error: {e}")
                    elif result == "failed":
                        job.status = "FAILED"
                        db.commit()
                        _inc_stat(db, "failed", user_id)
                        _log(f"❌ Failed: {job.title}", user_id)
                    elif result == "skipped":
                        job.status = "SKIPPED"
                        job.skip_reason = "no_easy_apply_btn"
                        db.commit()
                        _inc_stat(db, "skipped", user_id)

                    await asyncio.sleep(random.uniform(delay_min, delay_max))
            finally:
                await agent.stop()

        st["phase"] = "idle"
        st["current_job"] = ""
        _log(f"🏁 Apply phase done. Applied: {applied_today}", user_id)
    finally:
        db.close()


def _start_agent_thread(phase: str, platforms: list[str], user_id: int):
    if not _browser_semaphore.acquire(blocking=False):
        return None, "server_busy"

    def target():
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run_agent_task(phase, platforms, user_id))
            finally:
                loop.close()
        finally:
            _browser_semaphore.release()

    t = threading.Thread(target=target, daemon=True, name=f"agent-{phase}-u{user_id}")
    t.start()
    return t, None


async def _run_agent_task(phase: str, platforms: list[str], user_id: int):
    st = _get_user_state(user_id)
    st["running"] = True
    st["paused"] = False
    st["error"] = None

    try:
        if phase in ("discover", "full"):
            st["phase"] = "discovering"
            await _run_discovery(platforms, user_id)
        if phase in ("apply", "full") and st["running"]:
            await _run_apply(user_id)
    except Exception as e:
        st["error"] = str(e)
        _log(f"💥 Agent crashed: {e}", user_id)
        logger.exception(e)
    finally:
        st["running"] = False
        st["phase"] = "idle"
        st["current_job"] = ""
        _schedule_broadcast({"type": "stats", "state": {k: v for k, v in st.items() if k != "log"}}, user_id)


# ── REST endpoints ────────────────────────────────────────────────────

@router.get("/state")
def get_state(current_user: User = Depends(get_current_user)):
    st = _get_user_state(current_user.id)
    return {k: v for k, v in st.items() if k != "log"}


@router.get("/log")
def get_log(limit: int = 100, current_user: User = Depends(get_current_user)):
    st = _get_user_state(current_user.id)
    return {"log": st["log"][-limit:]}


@router.post("/start/discover")
async def start_discover(payload: dict = {}, current_user: User = Depends(get_current_user)):
    global _main_loop
    user_id = current_user.id
    st = _get_user_state(user_id)
    if st["running"]:
        return {"error": "Agent already running"}
    _main_loop = asyncio.get_running_loop()
    platforms = payload.get("platforms", ["linkedin", "naukri", "internshala", "unstop"])
    t, err = _start_agent_thread("discover", platforms, user_id)
    if err:
        return {"error": err}
    _agent_threads[user_id] = t
    return {"ok": True, "phase": "discover", "platforms": platforms}


@router.post("/start/apply")
async def start_apply(current_user: User = Depends(get_current_user)):
    global _main_loop
    user_id = current_user.id
    st = _get_user_state(user_id)
    if st["running"]:
        return {"error": "Agent already running"}
    _main_loop = asyncio.get_running_loop()
    t, err = _start_agent_thread("apply", [], user_id)
    if err:
        return {"error": err}
    _agent_threads[user_id] = t
    return {"ok": True, "phase": "apply"}


@router.post("/stop")
async def stop_agent(current_user: User = Depends(get_current_user)):
    st = _get_user_state(current_user.id)
    st["running"] = False
    st["paused"] = False
    return {"ok": True}


@router.post("/pause")
async def pause_agent(current_user: User = Depends(get_current_user)):
    st = _get_user_state(current_user.id)
    st["paused"] = not st["paused"]
    return {"ok": True, "paused": st["paused"]}


# ── WebSocket live log ────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")):
    await ws.accept()
    user_id = decode_token(token) if token else None
    if not user_id:
        await ws.close(code=4001, reason="Unauthorized")
        return

    if user_id not in _ws_clients:
        _ws_clients[user_id] = []
    _ws_clients[user_id].append(ws)

    st = _get_user_state(user_id)
    await ws.send_json({"type": "init", "state": st})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients = _ws_clients.get(user_id, [])
        if ws in clients:
            clients.remove(ws)
