"""Brief mode orchestrator — V1.3.

Runs discovery across all configured sources (LinkedIn, Naukri, ATS Aggregator,
Unstop, HN, Wellfound, Google Jobs), scores in-memory (no DB writes to `jobs`),
takes top-N, enriches each company via Claude, writes an Excel, emails it,
and records a BriefRun row.

Trigger: `POST /api/brief/run` (manual) or scheduler at `brief_time` (auto).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime

from db.database import SessionLocal
from db.models import Profile, Credential, BriefRun
from scoring.semantic_scorer import score_job
from .extractor import parse_salary, parse_experience
from .enrichment import enrich_company
from .xlsx_writer import write_brief_xlsx

logger = logging.getLogger("brief.orchestrator")

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
BRIEFS_DIR = os.path.join(DATA_DIR, "briefs")


def _agent_classes_for(persona: str) -> dict:
    """Resolved at call-time so import errors in optional agents don't break
    the apply flow."""
    from agents.linkedin_agent import LinkedInAgent
    from agents.naukri_agent import NaukriAgent
    from agents.ats_aggregator_agent import ATSAggregatorAgent

    classes: dict[str, type] = {
        "linkedin": LinkedInAgent,
        "naukri": NaukriAgent,
        "ats": ATSAggregatorAgent,
    }

    # Optional / new sources — import errors here are non-fatal.
    try:
        from agents.unstop_agent import UnstopAgent
        if (persona or "").lower() == "fresher":
            classes["unstop"] = UnstopAgent
    except Exception as e:
        logger.debug(f"unstop agent unavailable: {e}")
    try:
        from agents.hn_whoishiring_agent import HNWhoIsHiringAgent
        classes["hn"] = HNWhoIsHiringAgent
    except Exception as e:
        logger.debug(f"hn agent unavailable: {e}")
    try:
        from agents.wellfound_agent import WellfoundAgent
        classes["wellfound"] = WellfoundAgent
    except Exception as e:
        logger.debug(f"wellfound agent unavailable: {e}")
    try:
        from agents.google_jobs_agent import GoogleJobsAgent
        classes["google_jobs"] = GoogleJobsAgent
    except Exception as e:
        logger.debug(f"google_jobs agent unavailable: {e}")

    return classes


def _profile_dict(db, user_id: int) -> dict:
    """Mirror of api.agent._get_profile_dict — local copy avoids importing from
    api/agent.py (and pulling in WebSocket / scheduler deps)."""
    import json
    p = db.query(Profile).filter_by(user_id=user_id).first()
    if not p:
        return {"user_id": user_id}

    try:
        preferred_cities = json.loads(p.preferred_cities) if p.preferred_cities else []
        if not isinstance(preferred_cities, list):
            preferred_cities = []
    except Exception:
        preferred_cities = []
    try:
        skills = json.loads(p.skills) if p.skills else []
        if not isinstance(skills, list):
            skills = []
    except Exception:
        skills = []

    return {
        "user_id": user_id,
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "city": p.city,
        "years_of_experience": p.years_of_experience or 0,
        "search_keywords": [k.strip() for k in (p.search_keywords or "").split(",") if k.strip()],
        "location_filter": p.location_filter or "India",
        "match_threshold": p.match_threshold or 40,  # lower bar for Brief vs Apply
        "skills": skills,
        "persona": p.persona or "early_career",
        "preferred_cities": preferred_cities,
        "notification_email": p.notification_email or p.email or "",
        "brief_top_n": getattr(p, "brief_top_n", None) or 30,
    }


def _get_credentials(db, platform: str, user_id: int) -> dict:
    c = db.query(Credential).filter_by(user_id=user_id, platform=platform).first()
    email = c.email if c else ""
    password = c.password if c else ""
    login_mode = "auto" if (email and password) else "manual"
    return {"email": email, "password": password, "login_mode": login_mode}


async def _run_one_source(platform: str, AgentClass, profile: dict, credentials: dict,
                          keywords: list[str], location: str, per_source: int) -> list[dict]:
    """Start agent → login (if needed) → search → stop. Returns raw jobs.
    Errors are swallowed; brief continues with the sources that worked."""
    # Most platforms in Brief mode can be headless. LinkedIn and Naukri have
    # the same anti-bot constraints as the Apply flow, so respect their hints.
    headless = not (platform == "linkedin" or getattr(AgentClass, "requires_visible_browser", False))
    agent = AgentClass(profile=profile, credentials=credentials)
    try:
        await agent.start(headless=headless)
        try:
            logged_in = await agent.login()
        except Exception as e:
            logger.warning(f"[brief] {platform} login error: {e}")
            logged_in = True  # public-search agents (HN/Google/Wellfound) often return True regardless
        if not logged_in:
            logger.info(f"[brief] {platform}: login failed, skipping")
            return []
        raw = await agent.search_jobs(
            keywords=keywords,
            location=location,
            filters={"date_posted": "r86400"},
            max_jobs=per_source,
        )
        return raw or []
    except Exception as e:
        logger.warning(f"[brief] {platform} discovery failed: {e}")
        return []
    finally:
        try:
            await agent.stop()
        except Exception:
            pass


async def run_brief(user_id: int, platforms: list[str] | None = None) -> dict:
    """Top-level entry. Returns a result summary dict."""
    started_at = datetime.utcnow()
    t0 = time.time()

    db = SessionLocal()
    try:
        profile = _profile_dict(db, user_id)
        if not profile.get("user_id"):
            return {"ok": False, "error": "no_profile", "run_id": None}

        keywords = profile.get("search_keywords") or ["Product Manager"]
        location = profile.get("location_filter") or "India"
        top_n = profile.get("brief_top_n") or 30
        email_to = profile.get("notification_email") or profile.get("email") or ""

        all_classes = _agent_classes_for(profile.get("persona", "early_career"))
        if platforms:
            selected = {k: v for k, v in all_classes.items() if k in platforms}
        else:
            selected = all_classes

        if not selected:
            return {"ok": False, "error": "no_sources_available", "run_id": None}

        per_source = max(15, (top_n * 2) // max(len(selected), 1))

        # Pre-create the BriefRun row so we can update progress.
        run = BriefRun(
            user_id=user_id,
            platforms=",".join(selected.keys()),
            jobs_count=0,
            email_to=email_to,
            started_at=started_at,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

        # Run sources sequentially (sequential is safer for the 8GB laptop —
        # LinkedIn alone already needs a visible browser).
        all_jobs: list[dict] = []
        for platform, AgentClass in selected.items():
            credentials = _get_credentials(db, platform, user_id)
            logger.info(f"[brief u{user_id}] running {platform}...")
            jobs = await _run_one_source(
                platform, AgentClass, profile, credentials,
                keywords, location, per_source,
            )
            for j in jobs:
                # Ensure platform is set; some adapters omit it.
                j.setdefault("platform", platform)
            all_jobs.extend(jobs)
            logger.info(f"[brief u{user_id}] {platform}: {len(jobs)} jobs")

        # Dedup in-memory by (company, title) — case-insensitive.
        seen: set[tuple[str, str]] = set()
        unique: list[dict] = []
        for j in all_jobs:
            key = ((j.get("company") or "").strip().lower(),
                   (j.get("title") or "").strip().lower())
            if not key[1] or key in seen:
                continue
            seen.add(key)
            unique.append(j)

        # Score
        scored: list[tuple[float, list[str], dict]] = []
        for j in unique:
            score, matched, skip_reason = score_job(
                j.get("title", ""),
                j.get("description", "") or "",
                j.get("company", ""),
                j.get("location", ""),
                profile=profile,
            )
            if skip_reason:
                continue
            j["match_score"] = score
            j["matched_kws"] = matched
            scored.append((score, matched, j))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [j for _, _, j in scored[:top_n]]
        logger.info(f"[brief u{user_id}] scored {len(scored)}, taking top {len(top)}")

        # Enrich in parallel for unique companies
        companies = sorted({(j.get("company") or "").strip() for j in top if j.get("company")})
        enrichment_results = await asyncio.gather(
            *(enrich_company(c, user_id) for c in companies),
            return_exceptions=True,
        )
        enrich_map: dict[str, dict] = {}
        for c, res in zip(companies, enrichment_results):
            if isinstance(res, Exception):
                logger.debug(f"[brief] enrich failed for {c}: {res}")
                continue
            enrich_map[c.lower()] = res

        # Build the rows
        rows: list[dict] = []
        for j in top:
            jd = j.get("description", "") or ""
            company_lc = (j.get("company") or "").strip().lower()
            enr = enrich_map.get(company_lc, {
                "funding_status": "—", "size_band": "—",
                "valuation": "—", "confidence": "none",
            })
            rows.append({
                "platform": j.get("platform", ""),
                "company": j.get("company", ""),
                "title": j.get("title", ""),
                "location": j.get("location", ""),
                "experience": j.get("experience") or parse_experience(jd),
                "salary": j.get("salary") or parse_salary(jd),
                "funding_status": enr["funding_status"],
                "size_band": enr["size_band"],
                "valuation": enr["valuation"],
                "match_score": j.get("match_score", 0),
                "posted_at_source": j.get("posted_at_source") or "",
                "url": j.get("url", ""),
            })

        # Write Excel
        os.makedirs(BRIEFS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        xlsx_path = os.path.join(BRIEFS_DIR, f"brief_{user_id}_{ts}.xlsx")
        try:
            write_brief_xlsx(rows, xlsx_path)
        except Exception as e:
            logger.exception(f"[brief] xlsx write failed: {e}")
            run.error_msg = f"xlsx: {e}"
            db.commit()
            return {"ok": False, "error": f"xlsx: {e}", "run_id": run_id}

        # Email — best-effort
        email_sent = False
        try:
            from notifications import send_brief_email
            if email_to:
                email_sent = send_brief_email(
                    to=email_to,
                    xlsx_path=xlsx_path,
                    summary={
                        "total": len(rows),
                        "platforms": list(selected.keys()),
                        "top_score": rows[0]["match_score"] if rows else 0,
                    },
                    top5=rows[:5],
                )
        except Exception as e:
            logger.warning(f"[brief] email failed: {e}")
            run.error_msg = (run.error_msg or "") + f" | email: {e}"

        # Finalize BriefRun
        run.jobs_count = len(rows)
        run.top_score = rows[0]["match_score"] if rows else 0.0
        run.xlsx_path = xlsx_path
        run.email_sent = email_sent
        run.completed_at = datetime.utcnow()
        run.duration_ms = int((time.time() - t0) * 1000)
        db.commit()

        return {
            "ok": True,
            "run_id": run_id,
            "jobs_count": len(rows),
            "email_sent": email_sent,
            "xlsx_path": xlsx_path,
        }
    finally:
        db.close()
