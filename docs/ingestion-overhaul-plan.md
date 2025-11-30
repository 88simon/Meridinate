# Goal
Automate a lightweight “migrated tokens” intake and promotion pipeline to reduce survivorship bias and keep Helius credits under control. Preserve the existing manual scan/analysis flow; add a tiered, budgeted path with UI controls for thresholds and promotions.

# Summary
- Tier-0 (free): Ingest recent migrated tokens from Dexscreener into a queue, store basic metrics (MC/volume/age), no Helius calls.
- Tier-1 (gated): Enrich only tokens that pass thresholds; call minimal Helius endpoints (holders/metadata) under a per-run credit budget.
- Tier-2: Promote selected tokens to the existing full analysis pipeline (MTEW/SWAB). Register webhooks for SWAB on promotion.
- UI: Add an Ingestion page to view/manage queue, thresholds, budgets, and manual triggers.
- Safeguards: Feature flags, batch sizes, credit caps; keep all tokens (including duds) with status to avoid survivorship bias.

# Data Model (new)
## Table: token_ingest_queue
- token_address (pk)
- token_name, token_symbol
- first_seen_at (datetime), source (e.g., “dexscreener”)
- tier enum: ingested | enriched | analyzed | discarded
- status: pending | completed | failed
- ingested_at, enriched_at, analyzed_at, discarded_at
- last_mc_usd, last_volume_usd, last_liquidity, age_hours (snapshots from Dexscreener)
- Optional: ingest_notes, last_error

## Existing analyzed_tokens (additive fields)
- ingest_source (nullable)
- ingest_tier (nullable)

# Config/Settings
Expose via API and UI:
- thresholds: mc_min, volume_min, liquidity_min, age_max_hours
- tier1_batch_size
- tier1_credit_budget_per_run
- tier0_max_tokens_per_run
- flags: ingest_enabled, enrich_enabled, auto_promote_enabled

# API Endpoints (new)
- GET/POST `/api/ingest/settings` – view/update thresholds, budgets, flags.
- POST `/api/ingest/run-tier0` – trigger Dexscreener ingestion now.
- POST `/api/ingest/run-tier1` – trigger enrichment now (honors budget).
- GET `/api/ingest/queue` – list tokens by tier/status with stats.
- POST `/api/ingest/promote` – promote selected tokens to full analysis.
- POST `/api/ingest/discard` – mark tokens discarded.

# Scheduler Jobs (feature-flagged)
## Tier-0 ingestion (Dexscreener, free)
- Runs hourly (configurable).
- Fetch recent migrated tokens (24–48h window), cap at tier0_max_tokens_per_run.
- Dedupe against analyzed_tokens + token_ingest_queue.
- Store/update snapshots; set tier=ingested, status=pending.

## Tier-1 enrichment (Helius, budgeted)
- Runs every N hours (configurable).
- Select tokens where tier=ingested and pass thresholds.
- Process up to tier1_batch_size until tier1_credit_budget_per_run is hit.
- Call minimal Helius: top holders + metadata.
- Store enrichment data; set tier=enriched, enriched_at.

## Promotion to full analysis
- Manual or auto (if auto_promote_enabled).
- Promotion calls existing full analysis endpoint; set ingest_tier=analyzed in both tables.
- On promotion, register SWAB webhook for tracked wallets/tokens.

## MC/volume refresh (free)
- Refresh “hot” tokens (recent ingested/enriched) from Dexscreener on a slow cadence; update last_mc_usd/last_volume_usd.
- Cold tokens: refresh on-demand when opened.

# UI (Ingestion page)
- Sections: Ing ested (pending), Enriched (ready to promote), Analyzed/Discarded.
- Controls: Run Tier-0 now, Run Tier-1 now, Promote selected, Discard.
- Settings editor: thresholds/budgets/flags.
- Stats: last run times, counts, credits used in last Tier-1.
- Banner/toast on tokens page showing how many are waiting promotion.

# Safeguards
- Credit guard in Tier-1: track credits used; stop at tier1_credit_budget_per_run.
- Batch size limits; retry/backoff on errors.
- Feature flags to disable any stage quickly.
- Do not alter existing manual scan/analysis flows; promotion uses the same full-analysis endpoint.
- Keep all tokens with status (ingested/enriched/analyzed/discarded) to avoid survivorship bias.

# Implementation Notes
- New migrations only; no schema-breaking changes.
- Use Dexscreener for Tier-0 snapshots and MC/volume refresh (free).
- Use Helius sparingly in Tier-1; cap signatures/pages if you later add history checks.
- Register SWAB webhooks on promotion to keep future PnL accurate.

---

# Implementation Progress (Nov 28, 2025)

## Done
- Data model, settings, all 6 API endpoints, Tier-0/Tier-1 jobs, scheduler, UI page, banner
- **Fixed**: Settings updates now call `update_ingest_scheduler()` so feature flag toggles take effect immediately
- **MC/volume refresh job**: `POST /api/ingest/refresh-hot` endpoint + scheduler job (every 2h when `hot_refresh_enabled=true`)
- **Auto-promote**: Wired into Tier-1 enrichment - runs automatically after enrichment when `auto_promote_enabled=true`; also available via `POST /api/ingest/auto-promote`
- **SWAB webhook registration**: On promote (manual/auto), registers webhooks for all active SWAB wallets via existing WebhookManager
- **Fixed (Nov 28)**: Promotion now runs FULL token analysis:
  - Calls `TokenAnalyzer.analyze_token()` for early bidder detection
  - Saves to `analyzed_tokens` table (with `ingest_source` and `ingest_tier` metadata)
  - Records MTEW positions for win rate tracking
  - Generates and saves analysis files and Axiom export
  - Invalidates caches so new tokens appear in dashboard immediately
- **UI Naming Overhaul (Nov 28)**: Renamed tiers for clarity:
  - `ingested` → **Discovered** (tooltip: "DexScreener snapshot only; no Helius calls yet.")
  - `enriched` → **Pre-Analyzed** (tooltip: "Light Helius enrichment (holders/metadata); not in main dashboard yet.")
  - `analyzed` → **Analyzed (Live)** (tooltip: "Full Meridinate analysis complete; visible in Tokens dashboard and SWAB.")
  - Added "Dashboard" column showing: "Not yet in dashboard", "Needs promotion", "Live", "Excluded"
  - Banner now shows "Pre-Analyzed tokens waiting for promotion"
  - All labels have info icon tooltips explaining the stage

## New Settings Added
- `hot_refresh_enabled` (bool) - Enable hot token MC/volume refresh scheduler
- `hot_refresh_age_hours` (float, default 48) - Max age for hot tokens to refresh
- `hot_refresh_max_tokens` (int, default 100) - Max tokens to refresh per run
- `auto_promote_max_per_run` (int, default 5) - Max tokens to auto-promote per run
- `last_hot_refresh_at` (timestamp) - Last hot refresh run time

## New Endpoints
- `POST /api/ingest/refresh-hot` - Manual trigger for hot token refresh
- `POST /api/ingest/auto-promote` - Manual trigger for auto-promote
