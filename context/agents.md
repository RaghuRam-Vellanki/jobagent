# Subagents on JobAgent

The Phase 1 build used a **tech-lead-and-subagents** pattern: the main session played tech lead and dispatched specialized subagents in parallel waves over non-overlapping file trees. This file records who did what and the dispatch contract for each role.

## Phase 1 dispatch (2026-05-01)

### Wave 1 — three parallel agents over disjoint file trees

| Agent | Role | Files owned | Status |
|-------|------|-------------|--------|
| Agent A | backend-architect | `backend/db/models.py`, `backend/db/database.py` | Completed |
| Agent B | frontend-designer | `frontend/tailwind.config.ts`, `frontend/index.html`, `frontend/src/index.css` | Completed |
| Agent C | apply-engine | `backend/agents/universal_filler.py` (new file) | Did not start (quota) — written directly by tech lead |

**Why disjoint trees:** parallel agents must not race on the same files. Each wave's owners are picked so file-set intersection is empty.

### Wave 2 — sequential, dependent on Wave 1

| Wave | Owner | Files |
|------|-------|-------|
| 2 (apply-engine wiring) | tech-lead-direct | `backend/agents/linkedin_agent.py`, `backend/agents/ats_aggregator_agent.py`, `backend/api/agent.py`, `backend/agents/_workday_preflow.py` |
| 2B (Genesis token application) | tech-lead-direct | 7 frontend pages/components (`hover:bg-blue-*` → Genesis indigo hover) |

### Wave 3 — QA

End-to-end import smoke + DB schema verification + apply_channel persistence test. Run by tech lead directly because the test itself is a 50-line Python script, not subagent-shaped work.

## Subagent dispatch contract

When dispatching a subagent for this project, the prompt MUST include:

1. **Goal** — one-sentence outcome.
2. **Owned files** — full absolute paths. Anything not on this list is read-only.
3. **Skills to load** — by name (see `skills.md`). The agent must call `Skill` with each.
4. **Project constraints**:
   - Windows ProactorEventLoop required for Playwright (use `python backend/serve.py`, never raw uvicorn).
   - SQLite at `data/jobs.db` — never delete; runtime ALTER TABLE only.
   - Apply-channel taxonomy: `in_board` / `easy_apply` / `external` (tagged at discovery).
   - The agent NEVER clicks final-submission buttons (Submit / Apply Now / Confirm).
   - Genesis design tokens are authoritative; old `accent` / `danger` are aliased for back-compat — don't strip the aliases yet.
5. **Definition of done** — concrete verification steps (e.g. "run `npx tsc --noEmit` clean", "import the module without ModuleNotFoundError", "run the 3-scenario apply_channel test").
6. **Context budget** — agents are told to summarize work in ≤200 words; long output gets dropped on the floor.

## Heuristics for when to spawn a subagent

**Spawn one when:**
- The task is bounded and self-contained (single file or single feature surface).
- The work needs heavy file reads or grep that would burn the main context window (e.g. design-system migration touching 12 files).
- Multiple independent pieces of work can run in parallel on disjoint file trees.

**Don't spawn one when:**
- The task is < 100 LOC of straightforward edit on a known file (just edit it).
- The task requires holding context that the subagent can't pick up cold (multi-step plan continuation).
- The user is iterating in conversation — speed of feedback matters more than parallelism.

## Anti-patterns (learned the hard way)

1. **Don't dispatch background agents during a tight quota window.** Wave 1B and 1C were dispatched in background; Agent C never started because the quota reset happened mid-flight. Foreground or write-it-yourself when the quota is uncertain.

2. **Don't trust agent self-reports without verification.** Agent B's notification said "completed with quota notice" — but inspecting the actual files showed the writes had landed cleanly. Always read the files after the agent returns.

3. **Don't overlap file trees between parallel agents.** If Agent A and Agent B both want to touch `backend/db/models.py`, they're now sequential — give one of them a different file or run them in series.

4. **Don't push a subagent to "synthesize from research."** The prompt must include exact file paths + line numbers + what to change. Anything more abstract turns into the agent generating plausible-looking but wrong code.

## Phase 2 planned dispatch

| Wave | Role | Owned files | Skills |
|------|------|-------------|--------|
| 2.1 | onboarding-frontend | `frontend/src/pages/Onboarding.tsx`, persona/city pickers in `components/` | `frontend-design`, `ui-ux-pro-max` |
| 2.2 | scorer-rewrite | `backend/scoring/semantic_scorer.py` | `senior-architect` |
| 2.3 | scheduler | `backend/scheduler.py` (new), `backend/main.py` lifespan | `senior-architect` |
| 2.4 | filler-smoke-tests | `tests/probe_easy_apply.py`, `tests/probe_external_redirect.py`, `tests/probe_workday.py` | `webapp-testing` |

Run 2.1 and 2.2 in parallel (disjoint trees). 2.3 sequential after 2.2. 2.4 last, gated on real test URLs from the founder.
