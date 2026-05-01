# Skills used on JobAgent

This is the working set of Claude Code skills useful for this project, with the role each plays. Trigger names match `~/.claude/skills/` entries.

## Active skills

### `frontend-design` / `frontend-design-anthropic`
Used to land the **Genesis design system** in Phase 1: indigo primary, General Sans + DM Sans + JetBrains Mono, 4/6/8/12px radius scale, focus-ring + btn-glow + card-hover shadows. Triggered when changing tokens in `frontend/tailwind.config.ts`, `index.html` (font loaders), and `src/index.css` (body/headings).

**When to invoke:** new pages, page-level visual rework, design-system migrations, or when the user references a `*-DESIGN.md` spec.

### `senior-architect`
For system-architecture decisions — DB schema additions (V1 columns), apply-channel taxonomy, agent-orchestration patterns. Used to validate the "one shared `UniversalFormFiller` vs. per-platform agents" decision.

**When to invoke:** when a change spans backend + frontend + agent-orchestration boundaries, or when picking between two architectures.

### `ui-ux-pro-max`
Component-level UI refinements (buttons, modals, navbar, kanban, charts). Has shadcn/ui MCP integration — useful for the Applied kanban (E6) and onboarding wizard (E1).

**When to invoke:** new components or refining existing ones in `frontend/src/components/` and `frontend/src/pages/`.

### `webapp-testing`
Playwright-based interaction with the local Vite dev server (`http://localhost:5173`) plus FastAPI on `:8000`. For manually verifying UI changes (Genesis tokens render, kanban drag works, etc.) and capturing browser logs during agent runs.

**When to invoke:** before claiming a frontend feature done; for E4 smoke-tests against real LinkedIn / Naukri / Workday URLs.

### `claude-api`
For any code that talks to the Anthropic API — currently unused in V1 (no LLM cover-letter generation; deferred past V1). Will become relevant for E3 if we add LLM-based JD-to-skill matching, or for V2 features like cover-letter rewriting.

**When to invoke:** only when introducing `anthropic` SDK calls. Not needed for V1.

### `simplify`
Reuse / quality / efficiency review of changed code. Catches duplicated logic between `linkedin_agent._fill_inputs` and the universal filler's synonym table.

**When to invoke:** after a Wave-2-scale wiring change touches multiple agent files; before merging a phase.

### `security-review`
Pending-changes security audit. Important because this app stores plaintext platform credentials (LinkedIn / Naukri email + password) and resume PDFs.

**When to invoke:** before pushing changes that touch `db/models.py:Credential`, `api/profile.py`, or any field that handles secrets/PII.

### `loop` and `schedule`
- `loop` — for "keep checking the deploy" / "watch this metric" style polls.
- `schedule` — to dispatch one-time or recurring background agents (e.g. "in 2 weeks, open a cleanup PR for the back-compat `accent` alias once nothing references it").

**When to invoke:** after Phase 1 ships a flagged or temporary shim that needs follow-up. The Genesis `accent` / `danger` aliases in `tailwind.config.ts` are exactly this kind of temporary back-compat.

## Skills NOT relevant to V1

- `mcp-builder` — we don't expose MCP servers; defer.
- `init` — repo already has `CLAUDE.md`.
- `keybindings-help` / `update-config` / `fewer-permission-prompts` — Claude Code harness config, not project work.
- `statusline-setup` — UI for the CLI, not the project.

## How skills compose with subagents

Subagents (see `agents.md`) need their skills declared in the dispatch prompt. For Phase 1:

- **Wave 1B (frontend-designer)** loaded `frontend-design` to migrate Tailwind tokens.
- **Wave 1C (apply-engine)** would have loaded none — pure Playwright code; the universal filler skeleton was in the end written directly.
- **Wave 1A (backend-architect)** loaded none — pure SQLAlchemy edits.

For Phase 2, the E1 onboarding work will pair `frontend-design` + `ui-ux-pro-max`. The E5 scheduler work needs `senior-architect` to pick between APScheduler vs. threading-loop.
