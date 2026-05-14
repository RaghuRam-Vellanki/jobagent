"""Company enrichment for the Daily Brief.

Cache-then-LLM:
  1. Look up CompanyEnrichment(user_id, company_name_lc). If present and
     updated_at within 30 days, return it.
  2. Else call ClaudeClient.enrich_company → upsert → return.
  3. If LLM disabled / capped / failed, return a placeholder so the Excel
     still ships ("—" everywhere).
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from db.database import SessionLocal
from db.models import CompanyEnrichment
from llm.claude_client import get_client

logger = logging.getLogger("brief.enrichment")

CACHE_TTL = timedelta(days=30)

_PLACEHOLDER = {
    "funding_status": "—",
    "size_band": "—",
    "valuation": "—",
    "confidence": "none",
}


async def enrich_company(name: str, user_id: int) -> dict:
    if not name or not name.strip():
        return dict(_PLACEHOLDER)
    name_lc = name.strip().lower()

    # 1. Cache read
    db = SessionLocal()
    try:
        row = (
            db.query(CompanyEnrichment)
            .filter(
                CompanyEnrichment.user_id == user_id,
                CompanyEnrichment.company_name_lc == name_lc,
            )
            .first()
        )
        if row and row.updated_at and (datetime.utcnow() - row.updated_at) < CACHE_TTL:
            return {
                "funding_status": row.funding_status or "Unknown",
                "size_band": row.size_band or "Unknown",
                "valuation": row.valuation or "Unknown",
                "confidence": row.confidence or "low",
            }
    finally:
        db.close()

    # 2. LLM call
    client = get_client()
    if not client.enabled:
        return dict(_PLACEHOLDER)

    data = await client.enrich_company(name.strip(), user_id=user_id)
    if not data:
        return dict(_PLACEHOLDER)

    # 3. Upsert
    db = SessionLocal()
    try:
        row = (
            db.query(CompanyEnrichment)
            .filter(
                CompanyEnrichment.user_id == user_id,
                CompanyEnrichment.company_name_lc == name_lc,
            )
            .first()
        )
        if row:
            row.funding_status = data["funding_status"]
            row.size_band = data["size_band"]
            row.valuation = data["valuation"]
            row.confidence = data["confidence"]
            row.updated_at = datetime.utcnow()
        else:
            db.add(CompanyEnrichment(
                user_id=user_id,
                company_name_lc=name_lc,
                funding_status=data["funding_status"],
                size_band=data["size_band"],
                valuation=data["valuation"],
                confidence=data["confidence"],
                source="llm",
            ))
        db.commit()
    except Exception as e:
        logger.warning(f"enrichment cache write failed for '{name}': {e}")
    finally:
        db.close()

    return data
