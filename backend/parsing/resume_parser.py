"""Resume PDF parser — pdfminer + regex/keyword heuristics.

Goal: extract enough structured data to pre-fill the Profile form so the user
doesn't retype their basics. Best-effort — every field is optional; on failure
we return what we have and the user edits the rest in Settings.
"""
import os
import re
from datetime import datetime

from scoring.semantic_scorer import DEFAULT_SKILLS

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?91[-\s]?)?[6-9]\d{9}")
URL_RE = re.compile(r"https?://[^\s,;)\]\>]+", re.IGNORECASE)
DATE_RANGE_RE = re.compile(
    r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4})"
    r"\s*[-–—to]+\s*"
    r"(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4}|Present|Current|Now)",
    re.IGNORECASE,
)

INDIAN_CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Bengaluru", "Hyderabad", "Chennai",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat", "Lucknow", "Kanpur",
    "Nagpur", "Indore", "Thane", "Bhopal", "Visakhapatnam", "Patna", "Vadodara",
    "Ghaziabad", "Ludhiana", "Agra", "Nashik", "Faridabad", "Meerut", "Rajkot",
    "Varanasi", "Srinagar", "Aurangabad", "Dhanbad", "Amritsar", "Allahabad",
    "Howrah", "Coimbatore", "Jabalpur", "Gwalior", "Vijayawada", "Jodhpur",
    "Madurai", "Raipur", "Kochi", "Chandigarh", "Mysore", "Mysuru",
    "Guwahati", "Trivandrum", "Thiruvananthapuram", "Noida", "Gurgaon", "Gurugram",
    "Vellanki", "Vijayanagaram", "Vizianagaram",
]

TITLE_KEYWORDS = [
    "Product Manager", "Product Owner", "Associate Product Manager", "APM",
    "Program Manager", "Product Analyst", "Product Lead",
    "Business Analyst", "Project Manager", "Operations Manager",
    "Software Engineer", "Software Developer", "Full Stack Developer",
    "Frontend Developer", "Backend Developer", "Data Scientist",
    "Data Analyst", "ML Engineer", "DevOps Engineer", "QA Engineer",
    "UX Designer", "UI Designer", "Product Designer", "Marketing Manager",
    "Founder", "Co-Founder", "Intern",
]

# Extended skill vocabulary for parsing — superset of scoring DEFAULT_SKILLS
SKILL_VOCAB = list(set(DEFAULT_SKILLS + [
    "javascript", "typescript", "react", "node", "node.js", "next.js", "vue",
    "angular", "django", "flask", "fastapi", "express", "spring", "java",
    "kotlin", "swift", "go", "golang", "rust", "c++", "c#", ".net",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "kafka",
    "docker", "kubernetes", "aws", "gcp", "azure", "terraform", "jenkins",
    "git", "github", "gitlab", "ci/cd", "rest api", "graphql", "websocket",
    "machine learning", "deep learning", "tensorflow", "pytorch", "pandas",
    "numpy", "scikit-learn", "nlp", "computer vision",
    "html", "css", "tailwind", "sass", "webpack", "vite",
    "selenium", "playwright", "pytest", "jest",
    "leadership", "communication", "problem solving", "teamwork",
]))


def extract_text(pdf_path: str) -> str:
    if not os.path.exists(pdf_path):
        return ""
    try:
        from pdfminer.high_level import extract_text as _extract
        return _extract(pdf_path) or ""
    except Exception:
        return ""


def _extract_name(text: str, email: str = "") -> str:
    """First plausible name-like line at the top of the resume."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines[:10]:
        if "@" in line or any(ch.isdigit() for ch in line):
            continue
        if any(kw in line.lower() for kw in ("resume", "cv", "curriculum")):
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(w[0].isupper() for w in words if w[0].isalpha()):
            return line
    # Fallback: derive from email local-part
    if email:
        local = email.split("@")[0]
        parts = re.split(r"[._\-]", local)
        if len(parts) >= 2:
            return " ".join(p.capitalize() for p in parts if p.isalpha())
    return ""


def _extract_city(text: str) -> str:
    """First Indian city mentioned in the first 25 lines (header area)."""
    head = "\n".join(text.splitlines()[:25])
    for city in INDIAN_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", head, re.IGNORECASE):
            return city
    return ""


def _extract_current_title(text: str) -> str:
    """Title in the first ~30 lines or the first one near 'Present'."""
    lines = text.splitlines()
    for ln in lines[:30]:
        for t in TITLE_KEYWORDS:
            if re.search(rf"\b{re.escape(t)}\b", ln, re.IGNORECASE):
                return t
    # Look near "Present" / "Current"
    for i, ln in enumerate(lines):
        if re.search(r"\b(Present|Current|Now)\b", ln, re.IGNORECASE):
            window = " ".join(lines[max(0, i - 2):i + 1])
            for t in TITLE_KEYWORDS:
                if re.search(rf"\b{re.escape(t)}\b", window, re.IGNORECASE):
                    return t
    return ""


def _extract_years_experience(text: str) -> int:
    """Sum date-range spans, capped at the longest single span (avoids
    double-counting overlapping internships). Years rounded down."""
    spans_months = []
    current_year = datetime.utcnow().year
    for m in DATE_RANGE_RE.finditer(text):
        start = _parse_date(m.group("start"))
        end_raw = m.group("end")
        end = current_year * 12 + datetime.utcnow().month if re.match(
            r"present|current|now", end_raw, re.IGNORECASE
        ) else _parse_date(end_raw)
        if start and end and end >= start:
            spans_months.append(end - start)

    if not spans_months:
        # Try explicit "X years of experience"
        m = re.search(r"(\d+)\+?\s*years?\s*(of\s*)?experience", text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return 0

    total = sum(spans_months)
    return max(0, total // 12)


def _parse_date(s: str) -> int | None:
    """Convert 'Jun 2021' or '2021' to absolute month-count for arithmetic."""
    s = s.strip()
    months = {m: i + 1 for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )}
    m = re.match(r"([A-Za-z]+)[a-z]*\s+(\d{4})", s)
    if m:
        mo = months.get(m.group(1)[:3].title())
        if mo:
            return int(m.group(2)) * 12 + mo
    if s.isdigit() and len(s) == 4:
        return int(s) * 12 + 6  # mid-year approximation
    return None


def _extract_skills(text: str) -> list[str]:
    text_l = text.lower()
    found = []
    for skill in SKILL_VOCAB:
        if re.search(rf"\b{re.escape(skill.lower())}\b", text_l):
            found.append(skill)
    return found


def _extract_portfolio(text: str) -> str:
    """Pick first non-LinkedIn URL as portfolio."""
    for url in URL_RE.findall(text):
        url_clean = url.rstrip(".,;)")
        if "linkedin.com" in url_clean.lower():
            continue
        return url_clean
    return ""


def parse_resume(pdf_path: str) -> dict:
    """Parse a resume PDF into structured profile fields. All fields optional."""
    text = extract_text(pdf_path)
    if not text:
        return {}

    email_match = EMAIL_RE.search(text)
    email = email_match.group(0) if email_match else ""

    phone_match = PHONE_RE.search(text)
    phone = phone_match.group(0) if phone_match else ""

    return {
        "full_name": _extract_name(text, email),
        "email": email,
        "phone": phone,
        "city": _extract_city(text),
        "current_title": _extract_current_title(text),
        "years_of_experience": _extract_years_experience(text),
        "skills": _extract_skills(text),
        "portfolio_url": _extract_portfolio(text),
    }
