# Master Control Redesign – Guidance for Implementation

**Status: IMPLEMENTED (Nov 28, 2025)**

See `apps/frontend/src/components/master-control-modal.tsx` for the full implementation.

---

## Goal
Replace the generic “Settings” with a modular “Master Control” hub that clearly covers both manual scanning and TIP (ingestion) controls. Improve readability with better naming, grouping, and tooltips so users understand each control’s effect.

## High-Level Changes
- Rename the nav entry/icon from “Settings” to **Master Control** (add tooltip: “Central controls for scanning, ingestion, and tracking”).
- Replace “API Settings” with **Scanning & Ingestion Settings** (or “Analysis & Intake Settings”).
- Break the settings UI into clear sections/tabs with concise descriptions and tooltips.

## Suggested UI Structure (tabs/sections)
1) **Scanning & Ingestion**
   - Manual scan settings (existing API settings): walletCount, transactionLimit, minUsdFilter, etc.
   - TIP settings (ingest settings): thresholds (mc_min, volume_min, liquidity_min, age_max_hours), batch sizes, credit budgets, flags (ingest_enabled, enrich_enabled, auto_promote_enabled, hot_refresh_enabled), max promotions per run, hot refresh params.
   - Tooltip: “Controls manual scans and automated intake (TIP): thresholds, budgets, and feature flags.”

2) **Webhooks & Tracking**
   - Show SWAB webhook status/last hit if available.
   - Controls to register/delete/list webhooks (using existing webhook endpoints).
   - Tooltip: “Manage webhooks for real-time SWAB tracking.”

3) **Alerts & UI**
   - Toggles for banners/notifications (e.g., ingest banner on tokens page, toast preferences if present).
   - Tooltip: “Control UI indicators and notifications.”

4) **System & Schedules**
   - Feature flags: ingest_enabled, enrich_enabled, auto_promote_enabled, hot_refresh_enabled.
   - Scheduler info: last run times for Tier-0/Tier-1/hot refresh, credit budgets.
   - Tooltip: “Scheduler controls, budgets, and feature flags.”

## Backend Context (already available)
- Ingest settings endpoints: `/api/ingest/settings` (GET/POST).
- Ingest actions: run-tier0, run-tier1, promote, discard, refresh-hot, auto-promote.
- Webhooks: create/list/delete via `/webhooks/*`.
- Manual scan settings currently come from the existing API settings (manual analysis flow).

## Implementation Steps
1) **Nav/Label Updates**
   - Rename “Settings” nav item/icon to **Master Control** with tooltip.
   - Update any shortcuts/tooltips accordingly.

2) **Settings Page Layout**
   - Convert the current settings UI into the tabbed layout above.
   - Load/save manual scan settings as before; load/save ingest settings via `/api/ingest/settings`.
   - Show current values and allow edits with concise helper text and tooltips.

3) **Tooltips/Copy**
   - Add short descriptions per section and for key toggles:
     - Scanning & Ingestion: “Manual scan limits and TIP thresholds/budgets.”
     - Webhooks & Tracking: “Manage real-time tracking hooks for SWAB.”
     - Alerts & UI: “Control banners and notifications.”
     - System & Schedules: “Scheduler flags, last run times, budgets.”

4) **Optional Status Indicators**
   - Display last run timestamps for Tier-0/Tier-1/hot refresh.
   - Show counts of enriched tokens awaiting promotion (or link to Ingestion page).
   - Show webhook status (if available) or a simple “not configured” message.

## Notes
- Do not remove existing functionality; this is a UX reorganization with clearer names and grouping.
- Keep settings persistence the same: manual scan settings via existing API settings; ingest settings via `/api/ingest/settings`.
- Keep feature flags visible and actionable; ensure toggling flags updates schedulers (already implemented).

## Clarifications (if needed)
- If a different label is preferred for the main tab, acceptable alternatives: “Analysis & Intake Settings.”
- If webhook status endpoints are not available, omit status and keep only controls to create/list/delete.
