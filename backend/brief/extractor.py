"""Regex-based fallbacks for fields the scrapers couldn't pull cleanly.
Used by the Brief orchestrator before writing the Excel."""
from __future__ import annotations
import re


_SALARY_PATTERNS = [
    # INR LPA forms: "8-12 LPA", "8 LPA", "₹8L - ₹12L"
    re.compile(r"(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*(?:LPA|lpa|lakhs?\s*per\s*annum)", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:LPA|lpa|lakhs?\s*per\s*annum)", re.I),
    # USD forms: "$80k-$120k", "$120,000"
    re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d{2,3})\s*[kK]?\s*[-–to]+\s*\$?\s*(\d{1,3}(?:,\d{3})+|\d{2,3})\s*[kK]?", re.I),
    re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+)", re.I),
]

_EXP_PATTERNS = [
    # "2-4 years", "2 to 4 years"
    re.compile(r"(\d+)\s*[-–]+\s*(\d+)\s*\+?\s*years?", re.I),
    re.compile(r"(\d+)\s*to\s*(\d+)\s*years?", re.I),
    # "3+ years", "3 years", "minimum 3 years"
    re.compile(r"(?:minimum|at least|min\.?)\s*(\d+)\s*\+?\s*years?", re.I),
    re.compile(r"(\d+)\s*\+\s*years?", re.I),
    re.compile(r"(\d+)\s*years?\s+of\s+experience", re.I),
]


def parse_salary(text: str) -> str:
    if not text:
        return ""
    for pat in _SALARY_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        groups = [g for g in m.groups() if g]
        if len(groups) >= 2:
            return f"{groups[0]}–{groups[1]} {'LPA' if 'lpa' in m.group(0).lower() or 'lakh' in m.group(0).lower() else 'USD'}"
        if len(groups) == 1:
            unit = "LPA" if "lpa" in m.group(0).lower() or "lakh" in m.group(0).lower() else "USD"
            return f"{groups[0]} {unit}"
    return ""


def parse_experience(text: str) -> str:
    if not text:
        return ""
    for pat in _EXP_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        groups = [g for g in m.groups() if g]
        if len(groups) >= 2:
            return f"{groups[0]}–{groups[1]} yrs"
        if len(groups) == 1:
            return f"{groups[0]}+ yrs"
    return ""
