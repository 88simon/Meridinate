# Implementation Guide – Frontend/Backend Optimizations
Version: 1.0
Status: COMPLETED (Dec 1, 2025)
Audience: Implementers
Goal: Make targeted improvements with clear file paths and steps (no guesswork). Keep changes modular and durable.

## 1) Split Master Control (Settings) Modal
- Current file: `apps/frontend/src/components/master-control-modal.tsx` (~1300+ lines).
- Create per-tab components (new files):
  - `apps/frontend/src/components/master-control/scanning-tab.tsx`
  - `apps/frontend/src/components/master-control/ingestion-tab.tsx`
  - `apps/frontend/src/components/master-control/swab-tab.tsx`
  - `apps/frontend/src/components/master-control/webhooks-tab.tsx`
  - `apps/frontend/src/components/master-control/system-tab.tsx`
- Create shared primitives:
  - `apps/frontend/src/components/master-control/InfoTooltip.tsx` (reuse existing logic)
  - `apps/frontend/src/components/master-control/NumericStepper.tsx`
  - Optional shared hooks for settings load/save:
    - `apps/frontend/src/hooks/useIngestSettings.ts`
    - `apps/frontend/src/hooks/useScanSettings.ts`
- Refactor `master-control-modal.tsx` to only orchestrate tabs and modal shell; import tab components.
- Acceptance: props/state isolated per tab; no duplicate fetches; existing behavior preserved.

## 2) Scheduler Status Endpoint + Frontend Hook
- Backend: add a consolidated status endpoint returning `next_run_at` and `running` jobs.
  - File: `apps/backend/src/meridinate/routers/ingest.py` (or new `routers/scheduler.py`).
  - Response shape: `{ jobs: [{ name, type, next_run_at, status, started_at }] }` for Tier-0, Tier-1, Hot Refresh, Auto-Promote.
  - Source data: existing scheduler object that already drives ingest jobs; expose its schedule and active tasks.
- Frontend: add a hook and data type.
  - Types: `apps/frontend/src/types/scheduler.ts`
  - Hook: `apps/frontend/src/hooks/useSchedulerStatus.ts` (poll every ~15–30s, abort on unmount).
  - API client: add `getSchedulerStatus()` to `apps/frontend/src/lib/api.ts`.
- Acceptance: one endpoint supplies both next-run countdowns and currently running jobs.

## 3) Shared Ingest Settings Types/Constants
- Define a single source of truth for ingest settings shapes and defaults.
  - Backend: `apps/backend/src/meridinate/models/ingest_settings.py` (Pydantic schema + defaults).
  - Frontend: `apps/frontend/src/types/ingest-settings.ts` imported by ingestion tab/hook.
  - Optional shared constants: `apps/frontend/src/config/ingest-defaults.ts` that mirror backend defaults.
- Ensure `/api/ingest/settings` request/response matches these types; remove ad-hoc defaults in components.

## 4) Persist Scanned Tokens Filters (MTEW Table)
- Files: `apps/frontend/src/app/dashboard/tokens/page.tsx`, `apps/frontend/src/app/dashboard/tokens/tokens-table.tsx` (or wherever MTEW table state lives).
- Add persistence:
  - Store filters in `localStorage` (e.g., key `mtew-filters-v1`) and hydrate on mount.
  - Also reflect filters in URL query (for shareable links) if already supported; otherwise optional.
  - Use a small store (e.g., Zustand or React context) `apps/frontend/src/contexts/TokensFilterContext.tsx` to avoid resets on navigation.
- Acceptance: navigating away and back restores filters exactly; URL state does not break existing behavior.

## 5) Unify “Bypass Caps” / Validation Logic
- Goal: one switch to disable caps in both UI and backend validation for ingestion settings.
- Backend: introduce a flag `bypass_limits` in ingest settings (Pydantic + persistence) and honor it in validation for thresholds/batch/budget sliders.
  - File: `apps/backend/src/meridinate/routers/ingest.py` (settings save logic), and any validation helpers.
- Frontend: wire `bypassLimits` prop to NumericStepper and send `bypass_limits=true` via `/api/ingest/settings`.
  - Files: ingestion tab component + `apps/frontend/src/lib/api.ts` update function.
- Acceptance: when `bypass_limits` is on, UI no longer blocks saves at caps and backend accepts values beyond previous max bounds.

## 6) Integration Tests for Ingestion Settings & Actions
- Backend tests:
  - Location: `apps/backend/tests/` (add `test_ingest_settings.py`, `test_ingest_actions.py`).
  - Cover: settings save/load (including `ingest_enabled`, caps, scoring toggle), Tier-0/1 triggers, promote, refresh-hot, operation logging.
  - Assert: scoring flag persists, caps don’t block saves when `bypass_limits` is true.
- Frontend tests (optional if harnessed): add Playwright/Cypress to ensure settings toggles persist and filters don’t reset.

## 7) DexScreener Config Centralization
- File: `apps/backend/src/meridinate/services/ingest_service.py` (or equivalent).
- Extract DexScreener fetch parameters (window, endpoints, `tier0_max_tokens_per_run`, default interval) into a config module:
  - `apps/backend/src/meridinate/config/ingest_config.py`
- Hook up the new Tier-0 interval setting (`tier0_interval_minutes`) to the scheduler update function so UI changes apply immediately.

## 8) Scheduler Panel UI (Sidebar)
- Files to touch:
  - Sidebar: `apps/frontend/src/components/layout/app-sidebar.tsx` (add Scheduler icon/entry).
  - New panel: `apps/frontend/src/components/scheduler-panel.tsx` (slide-out that reflows layout like Codex panel).
- Behavior:
  - On click, main content shifts to make room (not overlay).
  - Uses `useSchedulerStatus` hook to show countdowns and currently running jobs (type, status, elapsed).
  - Polling cadence matches hook (15–30s) with immediate refresh on open.
- Acceptance: panel shows live next-run and running-job data; layout reflows similarly to Codex panel.

## 9) ToS Column (Type of Scan)
- Files: `apps/frontend/src/app/dashboard/tokens/tokens-table.tsx` (and related column defs).
- Add a column “ToS” with tooltip explaining: “Type of Scan (manual vs ingestion; pre-migration vs post-migration).”
- Data shape:
  - Source: token record should include `ingest_source` (manual|ingestion) and a migration flag from DexScreener (pre_migration|post_migration).
  - If backend doesn’t expose migration flag yet, extend the token API serializer in `apps/backend/src/meridinate/routers/tokens.py` to include it.
- Acceptance: column renders values for all rows; tooltip present; no layout break.

## 10) Settings Modal Resilience During Ingestion
- Ensure the Settings modal does not drop to splash/loading when ingestion jobs are running.
- Files: `apps/frontend/src/components/master-control-modal.tsx` (and new split tabs).
- Fix: keep settings fetched even if ingest endpoints are busy; handle 429/timeout with retry without hiding tabs; avoid blocking UI when ingestion actions run.
- Acceptance: user can open and edit settings while Tier-0/1/Promote/Discard are running.

## 11) Credits Logging for Promotions
- Files:
  - Backend: `apps/backend/src/meridinate/routers/ingest.py` and/or `analysis.py` to ensure promotion actions call `record_operation()` with correct credit usage and context.
  - Frontend: `apps/frontend/src/hooks/useStatusBarData.ts` to ensure recent operations include promotions triggered via scan settings.
- Acceptance: promotions show in API Credits Today → Recent Operations with correct credits and labels.

## Rollout Order (recommended)
1) Shared types/config (items 3, 7), then caps/bypass flag (5).  
2) Split modal + settings resilience (1, 10).  
3) Scheduler endpoint + panel UI (2, 8).  
4) Filter persistence (4) and ToS column (9).  
5) Credits logging checks and tests (11, 6).  

## Notes
- Keep ASCII; avoid altering gitignored secrets/DB files.
- After backend changes, rerun relevant schedulers to ensure updated intervals take effect.
- Validate UI with existing lint/test commands in `apps/frontend/package.json`; backend with `pytest` in `apps/backend/tests`.
