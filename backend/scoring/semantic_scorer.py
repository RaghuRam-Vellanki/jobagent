"""
Semantic scorer — ported and extended from v1 scorer.py.
Works purely on keyword matching, no API key needed.
"""
import re
import logging
from config import TITLE_WHITELIST, TITLE_BLACKLIST, COMPANY_BLACKLIST

logger = logging.getLogger("scoring.semantic")


def _clean(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", (text or "").lower())


def score_job(
    title: str,
    description: str,
    company: str = "",
    candidate_skills: list[str] | None = None,
) -> tuple[float, list[str], str | None]:
    """
    Returns (score 0-100, matched_keywords, skip_reason|None).
    skip_reason is set when the job should be hard-skipped regardless of score.
    """
    if candidate_skills is None:
        candidate_skills = DEFAULT_SKILLS

    title_l = _clean(title)
    desc_l = _clean(description)
    full = title_l + " " + desc_l

    # Hard filter: title blacklist
    for bw in TITLE_BLACKLIST:
        if bw in title_l:
            return 0.0, [], f"title_blacklisted:{bw}"

    # Hard filter: title must contain at least one whitelist term
    if not any(w in title_l for w in TITLE_WHITELIST):
        return 0.0, [], f"title_not_relevant:{title}"

    # Hard filter: company blacklist
    co_l = _clean(company)
    for bc in COMPANY_BLACKLIST:
        if bc.lower() in co_l:
            return 0.0, [], f"company_blacklisted:{bc}"

    # Score model (was: matched / total_skills, which collapses scores when
    # the candidate has many skills). New model:
    #   base 40 for clearing the title whitelist
    #   +5 per matched skill, capped at +35
    #   +bonuses for strong title + agile/PRD combo
    #   -20 if 3+ years experience required
    matched = [kw for kw in candidate_skills if kw in full]
    kw_score = 40 + min(len(matched) * 5, 35)

    # Bonus: strong title match (+15)
    strong_titles = ["product manager", "product owner", "associate product manager", "apm"]
    if any(st in title_l for st in strong_titles):
        kw_score = min(100, kw_score + 15)

    # Bonus: Agile + PRD combo (+10)
    if "agile" in full and ("prd" in full or "product requirement" in full):
        kw_score = min(100, kw_score + 10)

    # Penalty: 3+ years experience required (-20)
    exp_req = re.search(r"(\d+)\+?\s*years?\s*(of\s*)?(experience|exp)", full)
    if exp_req and int(exp_req.group(1)) >= 3:
        kw_score = max(0, kw_score - 20)

    score = round(kw_score, 1)
    logger.debug(f"[SCORE] '{title}' → {score} | matched: {matched[:5]}")
    return score, matched, None


def score_ats(resume_text: str, job_description: str, candidate_skills: list[str]) -> dict:
    """
    Scores resume text against a job description using keyword matching.
    Returns dict with score, matched, missing, suggestions.
    """
    resume_l = _clean(resume_text)
    desc_l = _clean(job_description)

    # Extract all keywords from job description that are in candidate_skills
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
