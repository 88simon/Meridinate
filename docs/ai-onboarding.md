# AI Onboarding (Concise Context)
**Version:** 1.6 (Dec 4, 2025)
**Use:** Quick orientation for new assistants. For full detail, see `PROJECT_BLUEPRINT.md` (v2.10) and topic docs in `docs/`.

## Stack & Paths
- **Backend:** FastAPI (Python 3.11) at `apps/backend/` (port 5003).
- **Frontend:** Next.js 15 + React at `apps/frontend/` (port 3000).
- **DB:** SQLite at `apps/backend/data/db/analyzed_tokens.db`.
- **Tools:** AutoHotkey action wheel at `tools/autohotkey/`.
- **Start:** `scripts/start.bat` (Windows) / `scripts/start.sh` (Unix).
- **Shared types:** Backend `models/ingest_settings.py` + frontend `types/ingest-settings.ts` for ingest settings schema.

## Navigation (UI)
- Sidebar order: Ingestion, Scanned Tokens, Codex, Trash, Scheduler, Settings.
- Settings modal: 4-tab hub (Scheduler, Scanning, Webhooks, System). Orchestrator at `master-control-modal.tsx`, tab logic in `components/master-control/*-tab.tsx`.

## Key Features
- Manual scan / Scanned Tokens.
- Discovery pipeline (DexScreener ingestion, direct promotion). Tier-1 deprecated.
- SWAB position tracking with webhooks; reconciliation as fallback.
- Live credits bar with persisted operation log.
- Scheduler Tab: unified settings for Token Discovery Scheduler (thresholds, interval, auto-promote) and Token Health Check Scheduler (MC refresh, drop conditions, SWAB position check). Performance Scoring settings removed.
- Scheduler Panel: slide-out showing jobs with live countdowns and running job elapsed time.
- SWAB-driven MC Refresh: fast-lane (30m) for tokens with SWAB exposure or MC >= $100k; slow-lane (4h) for others. Per-row Fast/Slow badge + global banner.
- Token Labels: auto-generated (auto:SWAB-Tracked, auto:No-Positions, auto:MC>100k, auto:Dormant, auto:Exited) plus manual tags (tag:*). Filter by label in Scanned Tokens.
- Table columns: First Filtered Buy and ToS columns removed; first filtered buy now in View Details modal info grid.
- Frontend SWR caching: Ingestion page, Scheduler tab, Scheduler panel, Codex panel use session storage for instant render with background refresh.

## Important Endpoints
- Ingest: `/api/ingest/settings`, `/api/ingest/run-discovery`, `/api/ingest/run-tier0` (alias), `/api/ingest/run-tier1` (deprecated)`, `/api/ingest/promote`, `/api/ingest/refresh-hot`, `/api/ingest/queue`.
- SWAB: `/api/swab/settings`, `/api/swab/check`, `/api/swab/update-pnl`, `/api/swab/reconcile-all`.
- Scoring: `/api/tokens/score`, `/api/tokens/{address}/performance`, `/api/ingest/control-cohort`.
- Credits/Stats: `/api/stats/credits/today`, `/api/stats/credits/transactions?limit=5`, `/api/stats/credits/operation-log`, `/api/tokens/latest`.
- Scheduler: `/api/stats/scheduler/jobs`.
- Webhooks: `/webhooks/*` (create/list/delete, callback at `/webhooks/callback`).

## Critical Notes
- Do not commit `apps/backend/config.json` or DB files.
- Webhooks needed for accurate SWAB sells; fallback reconciliation is best-effort.
- Ingestion and checks can be long-running—run them as background jobs (see `docs/ingest-async-queue-plan.md`).

## Reference Docs
- `PROJECT_BLUEPRINT.md` (full state, v2.10).
- `docs/ingestion-overhaul-plan.md`, `docs/ingest-async-queue-plan.md`.
- `docs/live-credits-bar-plan.md`, `docs/master-control-plan.md`, `docs/swab-check-progress-plan.md`.
- `docs/swab-driven-refresh-and-labeling-guide.md` (implemented Dec 2025).
- `docs/scheduler-tab-consolidation-guide.md` (implemented Dec 2025).
