# PRD — Content Approval Agent (GOVERN)

## Original Problem Statement
Marketing approval chain has three failure points:
1. **Upstream delay** — Product sends briefs late (no forcing function)
2. **Middle bottleneck** — Malaysia product team deprioritizes routine content
3. **CEO escalation trap** — Routine content reaches CEO, loses a month

The agent fixes all three: Layer 1 scores + classifies + routes; Layer 2 tracks with nudges/escalation; Layer 3 surfaces bottlenecks.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). JWT auth, bcrypt password hashing.
- **LLM**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via `emergentintegrations` + `EMERGENT_LLM_KEY`.
- **Frontend**: React 19 + React Router 7 + Tailwind + shadcn/ui + Recharts + sonner. Outfit (display) + IBM Plex Sans (body). Swiss & High-Contrast theme.

## User Personas
- Submitter — Marketing rep filing briefs
- Reviewer — Product team in Malaysia
- Marketing Lead — Escalation handler
- CEO — Final tier for innovation + risk

## Core Requirements (Static)
- Score every brief on brand alignment, completeness, classification (routine/innovation), risk flags
- Recommend tier: auto_approve / product_only / ceo_required
- Human can override recommendation
- Track submitted → under_review → approved/revision_requested/escalated → live
- 48h needs_nudge, 72h needs_escalation flags computed live
- Activity timeline per submission
- Analytics dashboard with status/tier/type breakdowns, idle list, avg stage hours, bottleneck reviewers

## What's Been Implemented (2026-02-16)
- ✅ JWT auth (register/login/me) with 4 roles
- ✅ Claude Sonnet 4.5 scoring endpoint with JSON extraction
- ✅ Submissions CRUD + 5 transition endpoints (approve, revision, escalate, mark-live, nudge)
- ✅ Auto-approve path skips approval chain when agent recommends and human confirms
- ✅ Analytics aggregation (stage durations, avg approval time, bottleneck reviewers, idle breakdown)
- ✅ Frontend: Login/Register, Overview, New Submission with agent-first flow, Queue with filters + 48h/72h badges, Submission Detail with timeline + action panel, Analytics with 4 Recharts panels + idle table
- ✅ 4 seed accounts (submitter@govern.app, reviewer@govern.app, lead@govern.app, ceo@govern.app)
- ✅ 22/22 backend tests passing

## Prioritized Backlog
**P1**
- Phase 3: Microsoft Teams webhook integration (push status updates + nudges to Teams channels)
- Automated nudge/escalation cron (currently flagged in UI; needs scheduled job)
- Submitter-scoped views (currently sees all org)
- State-machine guards on transitions (prevent re-approval of live items)
- Role guard on /escalate and /mark-live endpoints

**P2**
- Email notifications (SendGrid/Resend) on tier change and nudges
- Brand pillar config UI so org can encode their own scoring criteria
- Export analytics to CSV
- Pagination on submissions and analytics

**P3**
- Multi-org tenancy
- SLA dashboards per content type
- Reviewer load balancing
