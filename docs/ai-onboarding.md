# AI Onboarding (Concise Context)
**Version:** 1.0 (Nov 30, 2025)  
**Use:** Quick orientation for new assistants. For full detail, see `PROJECT_BLUEPRINT.md` and topic docs in `docs/`.

## Stack & Paths
- **Backend:** FastAPI (Python 3.11) at `apps/backend/` (port 5003).
- **Frontend:** Next.js 15 + React at `apps/frontend/` (port 3000).
- **DB:** SQLite at `apps/backend/data/db/analyzed_tokens.db`.
- **Tools:** AutoHotkey action wheel at `tools/autohotkey/`.
- **Start:** `scripts/start.bat` (Windows) / `scripts/start.sh` (Unix).

## Navigation (UI)
- Sidebar order: Ingestion, Scanned Tokens, Codex, Trash, Settings.
- Settings modal: tabs for Scanning (manual + Solscan), Ingestion (TIP + Performance Scoring), SWAB, Webhooks, System.

## Key Features
- Manual scan / Scanned Tokens.
- TIP (Tier-0 Dexscreener, Tier-1 Helius enrichment, promote).
- SWAB position tracking with webhooks; reconciliation as fallback.
- Live credits bar with persisted operation log.
- Performance Scoring: rule-based token categorization (Prime/Monitor/Cull) with configurable weights.

## Important Endpoints
- Ingest: `/api/ingest/settings`, `/api/ingest/run-tier0`, `/api/ingest/run-tier1`, `/api/ingest/promote`, `/api/ingest/refresh-hot`, `/api/ingest/queue`.
- SWAB: `/api/swab/settings`, `/api/swab/check`, `/api/swab/update-pnl`, `/api/swab/reconcile-all`.
- Scoring: `/api/tokens/score`, `/api/tokens/{address}/performance`, `/api/ingest/control-cohort`.
- Credits/Stats: `/api/stats/credits/today`, `/api/stats/credits/transactions?limit=5`, `/api/stats/credits/operation-log`, `/api/tokens/latest`.
- Webhooks: `/webhooks/*` (create/list/delete, callback at `/webhooks/callback`).

## Critical Notes
- Do not commit `apps/backend/config.json` or DB files.
- Webhooks needed for accurate SWAB sells; fallback reconciliation is best-effort.
- Ingestion and checks can be long-running—run them as background jobs (see `docs/ingest-async-queue-plan.md`).

## Reference Docs
- `PROJECT_BLUEPRINT.md` (full state, v2.4).
- `docs/ingestion-overhaul-plan.md`, `docs/ingest-async-queue-plan.md`.
- `docs/live-credits-bar-plan.md`, `docs/master-control-plan.md`, `docs/swab-check-progress-plan.md`.
