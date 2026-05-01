# JobAgent V2 — Project Context

## What this is

JobAgent (LazyApply) is a personal job-application automation tool for the Indian early-career market. Built by a single founder (Raghu Ram Vellanki). The codebase is a multi-tenant FastAPI + SQLAlchemy + SQLite backend with a React + Vite + TypeScript + Tailwind + Zustand frontend, driving Playwright-based browser agents for LinkedIn, Naukri, and ATS aggregator boards (Greenhouse + Ashby).

## Target personas

**P1 — Fresh Graduate (18–22, India)**
- Final-year or just-graduated B.Tech / B.Com / B.Sc / BBA / BA.
- 0 years full-time experience; may have internships.
- Wants entry-level / associate / trainee / graduate-program roles.
- Willing to apply to 25–50 jobs/day if surfaced.

**P2 — Early-Career Switcher (22–25, India, 1–3 yrs exp)**
- Working full-time, switching for salary / role / location / company tier.
- Cannot spend 2 hrs/day on applications during work hours.
- Prefers fewer, higher-quality applications (10–25/day) with personalization.

Shared: India-only locations (Hyderabad, Bengaluru, Delhi NCR / Gurgaon / Noida, Mumbai, Pune, Chennai, Ahmedabad / Gujarat, Remote-India). INR LPA salary; Hindi/English bilingual but UI is English-only for V1.

## Apply-channel priority (V1)

1. **Job-board listings** — discover + apply directly inside LinkedIn / Naukri search results.
2. **Easy Apply** — LinkedIn Easy Apply modal, Naukri Quick Apply (in-platform).
3. **Company website apply** — board listing has "Apply on company website" button that redirects off-board (e.g. Boat Lifestyle careers, Greenhouse / Ashby / Lever / Workday tenant).
4. **Workday** — treated as **just one ATS variant of #3**, NOT first-class. Gets a ≤30-LOC entry shim that hands off to the universal filler.

V1's apply engine is fundamentally a **Universal Form Auto-Filler** that runs on any URL we navigate to, not a stack of per-platform agents.

## V1 epics

| # | Epic | Status |
|---|------|--------|
| E1 | Persona-aware onboarding & profile | Schema landed (Phase 1); UI Phase 2 |
| E2 | Multi-source real-time discovery | Mostly built — LinkedIn / Naukri / Top-Companies live; apply_channel tagging landed Phase 1 |
| E3 | India-aware personalized matching | Partial — location ignored, no persona filter; rewrite Phase 2 |
| **E4** | **Universal Form Auto-Filler** | **Skeleton landed Phase 1**; smoke tests Phase 2 |
| E5 | Daily auto-run with cap & pacing | Schema landed Phase 1; scheduler Phase 2 |
| E6 | Application tracking & weekly insights | Mostly built — needs weekly gap report |

## Phase 1 scope (shipped 2026-05-01)

**Backend**
- `backend/agents/universal_filler.py` — shared Playwright form filler. 23-key synonym table, label resolution chain (aria-label → label[for] → placeholder → name → id → parent label), multi-pass progressive disclosure (≤5 passes), regex submit-blacklist, captcha detection.
- `backend/agents/_workday_preflow.py` — 30-line Workday entry shim. Detects myworkdayjobs.com and clicks "Apply Manually" before the universal filler takes over.
- `backend/db/models.py` — Profile gains `persona`, `preferred_cities`, `graduation_year`, `auto_run_enabled`, `auto_run_time`. Job gains `apply_channel`, `external_apply_url`.
- `backend/db/database.py` — idempotent runtime ALTER TABLE for the 7 V1 columns.
- `backend/agents/linkedin_agent.py` — `apply_to_job` branches on `apply_channel`. New `_apply_external` follows "Apply on company website" links and runs UniversalFormFiller.
- `backend/agents/ats_aggregator_agent.py` — discovery rows tag `apply_channel="external"` + `external_apply_url`. Apply path runs UniversalFormFiller with legacy filler as fallback.
- `backend/api/agent.py` — `_save_job` derives `apply_channel` from explicit field or legacy `easy_apply` flag.

**Frontend (Genesis design system)**
- `frontend/tailwind.config.ts` — indigo primary `#6366F1`, secondary `#20970B` (brand-only), General Sans + DM Sans + JetBrains Mono fonts, 4/6/8/12px radii, focus-ring + btn-glow + card-hover shadows. Back-compat aliases (`accent` → primary, `danger` → error).
- `frontend/index.html` + `frontend/src/index.css` — Fontshare General Sans, Google DM Sans, JetBrains Mono loaded; body/headings/code use the three Genesis fonts.
- 7 pages/components: `hover:bg-blue-600/700` → Genesis indigo hover `#4F46E5`.

## V1 Launch Definition of Done

1. Onboarding ≤5 minutes; profile has persona, ≥1 preferred city, resume, skills, keywords.
2. One-click discovery returns ≥10 jobs from ≥2 sources for a typical Bengaluru fresher.
3. ≥80% of queued jobs in a preferred city or remote-India.
4. UniversalFormFiller reaches review on ALL FOUR cases: LinkedIn Easy Apply, Naukri Quick Apply, LinkedIn → external company site (Boat Lifestyle), LinkedIn → Workday tenant.
5. ≥70% of approved jobs across a 25-job daily run reach review with all standard fields filled.
6. Daily auto-run triggers reliably for 7 consecutive days for an opted-in user.
7. Daily apply cap honored.
8. 10 internal beta users complete a full week with manual intervention only at final Submit + credential entry.
9. Applied page shows accurate stats; CSV export works.

## Non-goals (deferred past V1)

- Mobile apps (web-only).
- LLM-rewritten cover letters / resumes per job.
- Geographies outside India.
- Stripe/Razorpay billing — V1 is free for early users.
- Email/SMS/WhatsApp notifications (in-app log only).
- Naukri/LinkedIn fully-headless apply (requires visible browser; user-attended).
- Indeed India / Glassdoor — descoped (Cloudflare wall / paid API).

## Critical Windows constraint

Never start the backend with `python -m uvicorn backend.main:app` directly — uvicorn uses `_WindowsSelectorEventLoop` which cannot spawn subprocesses, and Playwright requires `ProactorEventLoop`. Always use `python backend/serve.py` or `python run.py`. Agent runs in a `threading.Thread` with its own ProactorEventLoop.

## Database

SQLite at `data/jobs.db`. WAL mode, `Base.metadata.create_all()` on startup, idempotent ALTER TABLE for V1 columns. To reset: delete `data/jobs.db`.
