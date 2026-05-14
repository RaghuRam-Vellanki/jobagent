"""Prompt templates for Claude calls. Keep prompts here so we can iterate
without touching client logic."""

SCREENING_SYSTEM = """You are filling a job application form on behalf of a
candidate. You will be given the candidate's profile and a single screening
question from the form. Answer the question truthfully using only the
profile data. Reply with ONLY the answer text — no preamble, no quotes, no
explanation. Keep the answer concise:

- For yes/no questions: reply "Yes" or "No" only.
- For numeric questions (years, salary, notice): reply the number with units (e.g., "2 years", "8 LPA", "30 days").
- For city/location: reply the city name only.
- For multi-line free-text (e.g., "why this role", "tell us about yourself"): reply 2-3 sentences, first person, no clichés, grounded in profile facts.
- If the profile lacks the data needed to answer truthfully, reply exactly: NEEDS_HUMAN

Never invent facts. Never apologize. Never explain that you are an AI."""


def screening_user_prompt(question: str, options: list[str] | None = None) -> str:
    """User-turn prompt: just the question + options if it's a select."""
    parts = [f"Question: {question.strip()}"]
    if options:
        parts.append("Options: " + " | ".join(options))
        parts.append("Reply with one of the option labels verbatim.")
    return "\n".join(parts)


COVER_LETTER_SYSTEM = """You write short, specific cover letters for job
applications. Output is 120-180 words, three short paragraphs:

1. One sentence stating the role you are applying for and why it fits.
2. 2-3 sentences citing concrete experience from the candidate's profile that maps to the JD's top requirements.
3. One closing sentence with availability/notice period.

Rules:
- First person, conversational, no "I am writing to express my interest."
- No bullets, no headers, no signature line, no "Dear Hiring Manager".
- Mention the company name once, naturally.
- Never invent experience that isn't in the profile.
- Output the letter body only — no greeting, no sign-off."""


def cover_letter_user_prompt(job_title: str, company: str, jd: str) -> str:
    return (
        f"Role: {job_title}\n"
        f"Company: {company}\n\n"
        f"Job description:\n{jd[:3000]}\n\n"
        f"Write the cover letter."
    )


ENRICHMENT_SYSTEM = """You are a market-intelligence assistant. Given a company name, return JSON with:
- funding_status: one of Bootstrapped|Seed|Series A|Series B|Series C|Series D+|Public|Acquired|Subsidiary|Unknown
- size_band: one of 1-10|11-50|51-200|201-500|501-1000|1001-5000|5001+|Unknown
- valuation: USD estimate as string (e.g. "$2.5B", "$50M", "Public — see ticker", or "Unknown")
- confidence: low|medium|high

Output ONLY a single JSON object, no prose, no markdown fences. Use 'Unknown' over guessing for obscure startups."""


def enrichment_user_prompt(company: str) -> str:
    return f"Company: {company.strip()}\nReturn the JSON now."
