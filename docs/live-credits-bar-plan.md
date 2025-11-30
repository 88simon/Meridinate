# Live Credits Bar & Status – Implementation Guide

## Goal
Extend the bottom status bar to act as a live updates bar for API credit usage and analysis status. Show it on the Tokens page and the Ingestion page. Surface recent credit usage events, daily totals, tokens scanned, and latest analysis.

## Desired Behavior
- Display a bottom bar on Tokens and Ingestion pages.
- Show:
  - Tokens scanned (today)
  - API credits used today
  - Latest analysis (token name, timestamp)
  - Recent credit usage events (short list, e.g., last 3–5, with op name and credits)
  - Optional: last ingest/enrichment runs (timestamp, credits) if available
- Update live when credit usage changes (use existing credit tracker data).

## Data Sources (Backend)
- Credit tracker endpoints (already exist):
  - `/api/stats/credits/today` – total credits today, breakdown.
  - `/api/stats/credits/transactions?limit=5` – recent credit events (operation, credits, timestamp).
- Latest analysis (add a helper to avoid client sorting):
  - New lightweight endpoint: e.g., `/api/tokens/latest` returning {token_name, analysis_timestamp}. If not added, fall back to `/api/tokens/history` and sort client-side.
- Optional: Ingestion last runs (from ingest settings/state):
  - `last_hot_refresh_at`, `last_tier0`/`last_tier1` timestamps if available; otherwise skip.

## Frontend Changes
1) **Status Bar Component Update**
   - Extend the existing bottom bar component to accept:
     - `tokensScanned`
     - `creditsUsedToday`
     - `latestAnalysis` (name + timestamp)
     - `recentCredits` (array of {operation, credits, timestamp})
     - Optional: `lastIngestRun` (e.g., last Tier-1/hot refresh) if desired
   - Add a small dropdown or popover to show the recent credit events (last 3–5).
   - Keep the layout compact; truncate long names.

2) **Data Fetching / Updates**
   - On Tokens and Ingestion pages, fetch:
     - `/api/stats/credits/today`
     - `/api/stats/credits/transactions?limit=5`
     - Latest analysis info from `/api/tokens/latest` (or fallback to `/api/tokens/history` sorted).
   - Prefer event-driven updates:
     - If you have a WebSocket/SSE channel, emit a “credits_updated” event when the credit tracker records a charge and update the bar on that event.
     - Also revalidate on focus/visibility change.
     - If no event channel is available, fall back to a light poll (e.g., 30–60s) with a “Refresh” affordance.

3) **Placement**
   - Render the updated bar on:
     - Tokens page (existing placement at bottom).
     - Ingestion page (same bar at bottom).

4) **Design/Copy**
   - Labels:
     - “Tokens Scanned”
     - “API Credits Used Today”
     - “Latest”
     - “Recent Credits” (click to expand popover with last N events, e.g., “market_cap_refresh: 12 cr @ 12:34”)
   - Keep concise; align with existing styling.

## Backend (Optional Tweaks)
- If needed, add a small helper endpoint to fetch the “latest token analysis” directly (token name + analysis_timestamp). Otherwise, use `/api/tokens/history` and sort client-side.
- Ensure credit stats endpoints are enabled and accessible without extra auth in the app context.

## Acceptance
- Bottom bar visible on Tokens and Ingestion pages.
- Shows live totals (credits today, tokens scanned) and latest analysis.
- Recent credit events available via a popover/dropdown in the bar.
- Updates without full page reload (revalidate interval OK).
