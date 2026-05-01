"""
Semantic scorer — V1 rewrite.

Adds persona-aware filtering (P1 fresher / P2 early_career) and India-aware
location scoring on top of the existing keyword-match base. Pure deterministic
keyword matching; no API key needed.

Caller passes a `profile` dict containing at least:
    persona: "fresher" | "early_career"
    preferred_cities: list[str]   # subset of SUPPORTED_CITIES
    skills: list[str]
    years_of_experience: int      # used as a soft signal for early_career band
"""
from __future__ import annotations
import re
import logging
from typing import Iterable
from config import TITLE_WHITELIST, TITLE_BLACKLIST, COMPANY_BLACKLIST

logger = logging.getLogger("scoring.semantic")


def _clean(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", (text or "").lower())


# ─── India-awareness ────────────────────────────────────────────────────

# Cities the user can pick in onboarding. Keep in sync with the frontend
# SUPPORTED_CITIES list in pages/Onboarding.tsx.
SUPPORTED_CITIES = [
    "bengaluru", "bangalore", "hyderabad", "delhi ncr", "delhi",
    "gurgaon", "gurugram", "noida", "mumbai", "pune", "chennai",
    "ahmedabad", "kolkata", "remote-india", "anywhere-india",
]

# Substrings that, when present in `location`, mark the role as Indian.
INDIA_SIGNALS = [
    "india", "bengaluru", "bangalore", "hyderabad", "delhi", "ncr",
    "gurgaon", "gurugram", "noida", "mumbai", "pune", "chennai",
    "ahmedabad", "kolkata", "remote-india", "anywhere-india",
]

# Substrings that, when present in `location` AND no India signal is found,
# mark the role as outside India and trigger a hard skip.
NON_INDIA_HINTS = [
    "san francisco", "sf bay", "new york", "nyc", "london", "berlin",
    "dublin", "tokyo", "singapore", "sydney", "melbourne", "toronto",
    "vancouver", "amsterdam", "paris", "munich", "remote - us",
    "remote-us", "remote us", "remote-uk", "remote uk", "remote-emea",
    "emea", "apac", "americas",
]

# NCR sub-cities so picking "Gurgaon" still matches "Delhi NCR" jobs.
NCR_GROUP = {"delhi ncr", "delhi", "gurgaon", "gurugram", "noida"}


def _location_match(loc: str, preferred: list[str]) -> str:
    """Returns one of: 'preferred' | 'india_other' | 'non_india' | 'unknown'."""
    if not loc:
        return "unknown"
    low = loc.lower()
    pref_low = [p.lower() for p in preferred]

    # Preferred city hit?
    for p in pref_low:
        if p in low:
            return "preferred"
        if p in NCR_GROUP and any(x in low for x in NCR_GROUP):
            return "preferred"
        if p in ("remote-india", "anywhere-india") and ("india" in low and "remote" in low):
            return "preferred"

    # Any India signal at all?
    if any(s in low for s in INDIA_SIGNALS):
        return "india_other"

    # Strong non-India hint?
    if any(s in low for s in NON_INDIA_HINTS):
        return "non_india"

    return "unknown"


# ─── Persona band detection ─────────────────────────────────────────────

_FRESHER_FRIENDLY = [
    "fresher", "freshers welcome", "graduate program", "graduate trainee",
    "campus hire", "entry level", "entry-level", "0-1 year", "0 to 1 year",
    "0-2 year", "trainee", "intern", "associate engineer trainee",
    "0 years",
]
_EARLY_CAREER_FRIENDLY = [
    "1-3 year", "1 to 3 year", "1-2 year", "2-3 year", "2-4 year",
    "associate", "apm", "junior", "early career",
]
_SENIOR_TITLE_HINTS = [
    "senior director", "vice president", "vp of", "head of", "principal",
    "staff product", "staff engineer", "staff designer", "lead architect",
    "director of engineering", "director of product", "chief", "cto", "cpo",
]


def _years_required(text: str) -> int | None:
    """Returns the maximum 'X+ years' number found in `text`, else None."""
    m = re.findall(r"(\d+)\s*\+?\s*years?\s*(?:of\s*)?(?:experience|exp)", text)
    if not m:
        # Also catch "X-Y years" — use the lower bound as the requirement.
        m2 = re.findall(r"(\d+)\s*[-–]\s*\d+\s*years?", text)
        if m2:
            try:
                return min(int(x) for x in m2)
            except Exception:
                return None
        return None
    try:
        return max(int(x) for x in m)
    except Exception:
        return None


# ─── Public API ─────────────────────────────────────────────────────────

def score_job(
    title: str,
    description: str,
    company: str = "",
    location: str = "",
    profile: dict | None = None,
) -> tuple[float, list[str], str | None]:
    """Returns `(score 0-100, matched_keywords, skip_reason | None)`.

    `skip_reason` is set when the job should be hard-skipped regardless of
    score (title blacklist, persona band mismatch, outside India, etc.).
    """
    profile = profile or {}
    persona = (profile.get("persona") or "early_career").lower()
    preferred_cities: list[str] = profile.get("preferred_cities") or []
    candidate_skills: list[str] = profile.get("skills") or DEFAULT_SKILLS
    yoe = int(profile.get("years_of_experience") or 0)

    title_l = _clean(title)
    desc_l = _clean(description)
    full = title_l + " " + desc_l

    # ── Hard filters ────────────────────────────────────────────────────
    for bw in TITLE_BLACKLIST:
        if bw in title_l:
            return 0.0, [], f"title_blacklisted:{bw}"

    if not any(w in title_l for w in TITLE_WHITELIST):
        return 0.0, [], f"title_not_relevant:{title}"

    co_l = _clean(company)
    for bc in COMPANY_BLACKLIST:
        if bc.lower() in co_l:
            return 0.0, [], f"company_blacklisted:{bc}"

    # ── Location: hard-skip non-India ───────────────────────────────────
    loc_class = _location_match(location, preferred_cities)
    if loc_class == "non_india":
        return 0.0, [], "outside_india"

    # ── Persona band hard filter ────────────────────────────────────────
    yrs_req = _years_required(full)

    if persona == "fresher":
        # Any role explicitly demanding 2+ years is above the fresher band.
        if yrs_req is not None and yrs_req >= 2:
            return 0.0, [], "requires_experience_above_persona"
        # Senior titles are a stronger signal — skip even without explicit years.
        if any(s in title_l for s in _SENIOR_TITLE_HINTS):
            return 0.0, [], "senior_title_above_persona"
    elif persona == "early_career":
        # P2 can take 1–3 yr roles; skip 8+ years and senior/principal/staff.
        if yrs_req is not None and yrs_req >= 8:
            return 0.0, [], "above_persona_band"
        if any(s in title_l for s in _SENIOR_TITLE_HINTS):
            return 0.0, [], "senior_title_above_persona"

    # ── Base score ──────────────────────────────────────────────────────
    matched = [kw for kw in candidate_skills if kw in full]
    score = 40 + min(len(matched) * 5, 35)

    # Strong title bonus
    strong_titles = ["product manager", "product owner",
                     "associate product manager", "apm"]
    if any(st in title_l for st in strong_titles):
        score += 15

    # Agile + PRD combo bonus
    if "agile" in full and ("prd" in full or "product requirement" in full):
        score += 10

    # ── Persona-fit bonus ───────────────────────────────────────────────
    if persona == "fresher" and any(p in full for p in _FRESHER_FRIENDLY):
        score += 10
    elif persona == "early_career" and any(p in full for p in _EARLY_CAREER_FRIENDLY):
        score += 10

    # ── Years-required soft penalty (only meaningful for early_career
    # since fresher already hard-filters at 2+) ─────────────────────────
    if persona == "early_career" and yrs_req is not None:
        if yrs_req > yoe + 2:
            score -= 20  # role wants meaningfully more than user has

    # ── Location score ──────────────────────────────────────────────────
    if loc_class == "preferred":
        score += 15
    elif loc_class == "india_other":
        score -= 10  # Indian but not in user's picks — keep but rank lower
    # 'unknown' (location string was empty / unparseable) — no adjustment

    score = round(max(0.0, min(100.0, score)), 1)
    logger.debug(
        f"[SCORE] '{title}' loc={location!r}({loc_class}) yrs_req={yrs_req} "
        f"persona={persona} → {score} | matched: {matched[:5]}"
    )
    return score, matched, None


def score_ats(resume_text: str, job_description: str, candidate_skills: list[str]) -> dict:
    """Scores resume text against a JD using keyword matching.
    Returns dict with score, matched, missing, suggestions."""
    resume_l = _clean(resume_text)
    desc_l = _clean(job_description)

    jd_keywords = [kw for kw in candidate_skills if kw in desc_l]
    if not jd_keywords:
        return {"score": 50, "matched": [], "missing": [], "suggestions": []}

    matched = [kw for kw in jd_keywords if kw in resume_l]
    missing = [kw for kw in jd_keywords if kw not in resume_l]

    score = round((len(matched) / max(len(jd_keywords), 1)) * 100, 1)

    suggestions = []
    if missing:
        suggestions.append(f"Add these keywords to your resume: {', '.join(missing[:8])}")
    if score >= 80:
        suggestions.append("Strong ATS match — apply with confidence.")
    elif score >= 60:
        suggestions.append("Good match. Tailor your summary to mention missing terms.")
    else:
        suggestions.append("Low match. Consider updating your resume for this role type.")

    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "suggestions": suggestions,
    }


DEFAULT_SKILLS = [
    "product manager", "product owner", "product management", "apm",
    "prd", "user story", "acceptance criteria", "gherkin", "sprint",
    "backlog", "roadmap", "agile", "scrum", "jira", "confluence",
    "stakeholder", "lti", "saas", "edtech", "k12", "lms",
    "ux", "user research", "figma", "wireframe", "mvp",
    "sql", "analytics", "kpi", "okr", "go-to-market",
    "cross-functional", "a/b testing", "data-driven",
    "python", "notion", "miro", "power bi", "tableau",
    "competitive analysis", "market research", "prioritization",
]
