"""V1.3 Daily Brief — curated Excel digest of top-N jobs across all sources,
enriched with company funding/size/valuation, emailed to the user.

Public API: `run_brief(user_id)` from `brief.orchestrator`.
"""
from .orchestrator import run_brief

__all__ = ["run_brief"]
