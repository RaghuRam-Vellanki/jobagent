"""Async wrapper around the Anthropic SDK with:
- Prompt caching on the profile block (cuts cost ~5x across questions).
- Per-user cost tracking (writes LLMCall rows).
- Graceful disable when ANTHROPIC_API_KEY is not set.
- Hard daily cap per user (defaults to USD 1.50/day, override via env).

Models:
- Haiku 4.5 for short answers (screening questions) — fast, cheap.
- Sonnet 4.6 for generation (cover letters) — better prose.
"""

from __future__ import annotations

import os
import json
import logging
import hashlib
from datetime import datetime, date
from typing import Any

logger = logging.getLogger("llm")

# Pricing (USD per 1M tokens, as of 2026-05).
# https://docs.anthropic.com/en/docs/about-claude/pricing
_PRICE = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
}

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

DAILY_CAP_USD = float(os.getenv("LLM_DAILY_CAP_USD", "1.50"))


def is_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


class ClaudeClient:
    def __init__(self):
        if not is_enabled():
            self._client = None
            return
        # Lazy import — keeps backend importable when SDK isn't installed.
        from anthropic import AsyncAnthropic
        self._client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def answer_screening_question(
        self,
        question: str,
        profile: dict,
        options: list[str] | None = None,
        user_id: int | None = None,
    ) -> str | None:
        """Returns the answer string, or None if disabled / over cap / refused.
        The string "NEEDS_HUMAN" means the model declined — caller should
        treat as silent-skip (leave field blank)."""
        if not self.enabled:
            return None
        if user_id is not None and not _under_daily_cap(user_id):
            logger.warning(f"LLM daily cap hit for user {user_id} — skipping question")
            return None

        from . import prompts

        profile_block = _profile_to_text(profile)

        try:
            resp = await self._client.messages.create(
                model=HAIKU,
                max_tokens=200,
                system=[
                    {
                        "type": "text",
                        "text": prompts.SCREENING_SYSTEM + "\n\nCandidate profile:\n" + profile_block,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": prompts.screening_user_prompt(question, options),
                    }
                ],
            )
        except Exception as e:
            logger.warning(f"Claude screening call failed: {e}")
            return None

        answer = _extract_text(resp).strip()
        _record_call(resp, HAIKU, user_id=user_id, purpose="screening")

        if not answer or answer.upper().startswith("NEEDS_HUMAN"):
            return None
        # Strip surrounding quotes if model added them despite instructions.
        if len(answer) > 1 and answer[0] in "\"'" and answer[-1] == answer[0]:
            answer = answer[1:-1]
        return answer

    async def write_cover_letter(
        self,
        job_title: str,
        company: str,
        jd: str,
        profile: dict,
        user_id: int | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        if user_id is not None and not _under_daily_cap(user_id):
            return None

        from . import prompts

        profile_block = _profile_to_text(profile)

        try:
            resp = await self._client.messages.create(
                model=SONNET,
                max_tokens=400,
                system=[
                    {
                        "type": "text",
                        "text": prompts.COVER_LETTER_SYSTEM + "\n\nCandidate profile:\n" + profile_block,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": prompts.cover_letter_user_prompt(job_title, company, jd),
                    }
                ],
            )
        except Exception as e:
            logger.warning(f"Claude cover-letter call failed: {e}")
            return None

        body = _extract_text(resp).strip()
        _record_call(resp, SONNET, user_id=user_id, purpose="cover_letter")
        return body or None

    async def enrich_company(
        self,
        company: str,
        user_id: int | None = None,
    ) -> dict | None:
        """V1.3: Returns {funding_status, size_band, valuation, confidence} or
        None when disabled / capped / parse-failed. Uses Haiku."""
        if not self.enabled:
            return None
        if user_id is not None and not _under_daily_cap(user_id):
            return None

        from . import prompts

        try:
            resp = await self._client.messages.create(
                model=HAIKU,
                max_tokens=200,
                system=[
                    {
                        "type": "text",
                        "text": prompts.ENRICHMENT_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": prompts.enrichment_user_prompt(company),
                    }
                ],
            )
        except Exception as e:
            logger.warning(f"Claude enrichment call failed for '{company}': {e}")
            return None

        raw = _extract_text(resp).strip()
        _record_call(resp, HAIKU, user_id=user_id, purpose="company_enrichment")

        # Strip markdown fences if model added them despite instructions.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].lstrip()
        try:
            data = json.loads(raw)
        except Exception:
            logger.debug(f"enrichment JSON parse failed for '{company}': {raw[:120]!r}")
            return {
                "funding_status": "Unknown",
                "size_band": "Unknown",
                "valuation": "Unknown",
                "confidence": "low",
            }
        return {
            "funding_status": str(data.get("funding_status") or "Unknown")[:64],
            "size_band": str(data.get("size_band") or "Unknown")[:32],
            "valuation": str(data.get("valuation") or "Unknown")[:64],
            "confidence": str(data.get("confidence") or "low")[:16],
        }


# ---------- helpers ----------

def _extract_text(resp) -> str:
    parts = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


def _profile_to_text(profile: dict) -> str:
    """Compact profile dump for the system block (cached). Keep only
    fields useful for answering screening questions."""
    keep = [
        "full_name", "email", "phone", "city", "state", "country",
        "current_title", "current_company", "years_of_experience",
        "notice_period", "expected_salary", "current_ctc",
        "linkedin_url", "portfolio_url", "skills", "search_keywords",
        "persona", "preferred_cities", "graduation_year", "degree",
    ]
    lines = []
    for k in keep:
        v = profile.get(k)
        if v in (None, "", [], 0):
            continue
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        lines.append(f"{k}: {v}")
    return "\n".join(lines) if lines else "(empty profile)"


def _record_call(resp, model: str, user_id: int | None, purpose: str) -> None:
    """Best-effort write of an LLMCall row. Never raise."""
    try:
        usage = getattr(resp, "usage", None)
        if not usage:
            return
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        price = _PRICE.get(model, {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0})
        cost = (
            inp * price["input"]
            + out * price["output"]
            + cache_read * price["cache_read"]
            + cache_write * price["cache_write"]
        ) / 1_000_000

        from ..db.database import SessionLocal
        from ..db.models import LLMCall
        with SessionLocal() as db:
            db.add(LLMCall(
                user_id=user_id,
                model=model,
                purpose=purpose,
                input_tokens=inp,
                output_tokens=out,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                cost_usd=cost,
            ))
            db.commit()
    except Exception as e:
        logger.debug(f"LLMCall record failed: {e}")


def _under_daily_cap(user_id: int) -> bool:
    """Return True if today's spend for user is under DAILY_CAP_USD."""
    try:
        from sqlalchemy import func
        from ..db.database import SessionLocal
        from ..db.models import LLMCall
        today_start = datetime.combine(date.today(), datetime.min.time())
        with SessionLocal() as db:
            spent = db.query(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).filter(
                LLMCall.user_id == user_id,
                LLMCall.created_at >= today_start,
            ).scalar() or 0.0
        return float(spent) < DAILY_CAP_USD
    except Exception as e:
        logger.debug(f"daily-cap check failed (allowing): {e}")
        return True


def question_hash(question: str, profile_version: str = "v1") -> str:
    """Stable cache key for ScreeningAnswer reuse across applications."""
    norm = " ".join(question.lower().split())
    return hashlib.sha256(f"{profile_version}|{norm}".encode("utf-8")).hexdigest()[:32]


_singleton: ClaudeClient | None = None


def get_client() -> ClaudeClient:
    global _singleton
    if _singleton is None:
        _singleton = ClaudeClient()
    return _singleton
