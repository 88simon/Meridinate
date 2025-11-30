# Token Performance Categorization Guide (Implementer)
Version: 1.0  
Audience: Backend + frontend implementers  
Goal: Add an explainable, credit-aware scoring system that classifies tokens in Scanned Tokens by performance quality, using only current data sources (DexScreener + Helius) and existing ingestion tiers.

## Scope and Constraints
- **Data sources:** DexScreener (free) for price/MC/volume/liquidity; Helius (paid) already used for holders/metadata/SWAB. No new vendors assumed.
- **Pipelines to reuse:** Tier-0/Tier-1 ingestion, hot refresh (`/api/ingest/refresh-hot`), promotion + SWAB webhooks.
- **Naming:** Keep current tier labels (Discovered, Pre-Analyzed, Analyzed (Live), Discarded/Excluded).
- **Non-goals (v1):** No ML model; no on-chain authority/lock verification beyond what DexScreener/Helius expose; no external blacklist feed.

## High-Level Concept
1) **Capture snapshots** of tracked tokens on a cadence (price, MC, volume, liquidity, holder counts, top-holder share, our positions PnL).  
2) **Score** each token with a rule-based, explainable engine (0–100) that maps to buckets: `Prime`, `Monitor`, `Cull`, `Excluded`.  
3) **Act:** show buckets in Scanned Tokens, suggest promotion for `Prime`, keep a control cohort of lower-score tokens for calibration.  
4) **Learn:** compare bucket vs. realized PnL (SWAB) and adjust weights periodically.

## Data Model Changes
- **Table: analyzed_tokens** (add columns):
  - `performance_score` (float, 0–100)
  - `performance_bucket` (text enum: prime|monitor|cull|excluded)
  - `score_explanation` (text/json string of triggered rules)
  - `score_timestamp` (datetime)
- **New table: token_performance_snapshots**
  - `token_address` (pk composite with `captured_at`)
  - `captured_at` (datetime)
  - `price_usd`, `mc_usd`, `volume_24h_usd`, `liquidity_usd`
  - `trade_count_1h`, `trade_count_24h` (if available from DexScreener)
  - `holder_count` (Helius-lite; nullable)
  - `top_holder_share` (0–1; nullable)
  - `our_positions_pnl_usd` (from SWAB; nullable)
  - `lp_locked` (bool/nullable best-effort from existing metadata)
  - `ingest_tier_snapshot` (discovered|pre_analyzed|analyzed)
- **Optional (control cohort tagging):** boolean `is_control_cohort` on `token_ingest_queue` and `analyzed_tokens`.

## Snapshot Capture (reuse existing jobs)
- **Hot refresh path (`/api/ingest/refresh-hot` + scheduler):**
  - For each eligible token (recent Discovered/Pre-Analyzed/Analyzed within `hot_refresh_age_hours` and capped by `hot_refresh_max_tokens`), fetch DexScreener metrics.
  - Write a row to `token_performance_snapshots`.
  - Do not call Helius here unless `ingest_tier` is Pre-Analyzed or Analyzed; if so, include holder_count + top_holder_share using existing Tier-1 enrichment primitives and respect credit budget.
- **Tier-1 enrichment:**
  - After enrichment, write a snapshot row so that holder/top-holder share are captured at first enrichment time.
- **Control cohort:**
  - Daily job picks N random Discovered tokens (e.g., 5–10/day) that fail thresholds, marks `is_control_cohort=true`, and includes them in hot refresh even if below thresholds.

## Scoring Engine (rule-based, explainable)
- **Execution:** Run after each snapshot batch; persists to `analyzed_tokens` (and optionally `token_ingest_queue` mirror fields for Discovered/Pre-Analyzed).
- **Inputs (all already available or nullable):**
  - Price/MC momentum: % change since first snapshot, 30m/2h/24h, and drawdown from local high.
  - Liquidity durability: liquidity vs. first snapshot; LP removed flag; liquidity trend.
  - Volume/participation: 30m/2h/24h volume; trades/hour if present.
  - Holder quality: holder_count growth; top_holder_share; count of high-win-rate wallets from MTEW present (already computed in analysis); whale/insider tags if available.
  - Survival: age_hours, lp_locked flag (best-effort), freeze/mint auth if already in metadata.
  - Outcomes: our_positions_pnl_usd (SWAB) for realized performance feedback.
- **Sample v1 rule set (editable constants):**
  - +15 if MC change 30m ≥ +50%; +10 if 2h ≥ +30%; -10 if drawdown ≥ 35%.
  - +10 if liquidity ≥ first_seen_liquidity * 1.3; -15 if liquidity < first_seen_liquidity * 0.6.
  - +10 if volume_24h_usd ≥ $100k; -10 if < $10k.
  - +12 if ≥3 high-win-rate wallets present; +6 if 1–2; -8 if top_holder_share > 0.45.
  - -10 if age_hours < 1 and lp_locked=false (best-effort).
  - +8 if our_positions_pnl_usd > 0; -8 if < 0 (when available).
- **Bucket thresholds (tuneable constants):**
  - `Prime` ≥ 65, `Monitor` 40–64, `Cull` < 40, `Excluded` explicit flag/blacklist.
- **Explanation:** Store triggered rules and their weights in `score_explanation` (e.g., JSON array) for UI tooltips and auditability.

## API Surface (minimal additions)
- **New (backend):**
  - `POST /api/tokens/score` – recompute scores for a list (ids/addresses) or all; returns updated buckets.
  - `GET /api/tokens/performance/{address}` – recent snapshots + bucket history.
- **Reuse:**
  - `/api/ingest/refresh-hot` triggers snapshot + scoring.
  - `/api/ingest/queue` can include latest bucket/score for Discovered/Pre-Analyzed.
- **Settings (extend existing ingest settings object):**
  - `performance_prime_threshold`, `performance_monitor_threshold`
  - `score_weights` object for the rule constants above
  - `control_cohort_daily_quota`
  - `score_enabled` flag

## Schedulers and Flow
1) **Hot refresh scheduler**: fetch DexScreener, write snapshots, optionally hydrate holder metrics for Pre-Analyzed/Analyzed within budget, then invoke scorer.
2) **Tier-1 enrichment**: after enrichment, write snapshot, invoke scorer.
3) **Control cohort selector (daily)**: mark random low-threshold Discovered tokens as control; include in hot refresh.
4) **Promotion helper**: after scoring, if bucket == Prime and not Analyzed, surface in queue/banner as “ready to promote”; auto-promote can gate on bucket + limit (`auto_promote_max_per_run`).

## Frontend Integration (Scanned Tokens + Ingestion)
- Add columns to Scanned Tokens: `Perf Score`, `Bucket`, `Last Snapshot`, `Reason` (tooltip from `score_explanation`).
- Filters: bucket filter; badge for control cohort; “Promote suggested” pill for Prime not yet Live.
- Ingestion banner: “X Pre-Analyzed tokens scored Prime; ready to promote”.
- Token detail modal/page: small performance panel with recent snapshots chart and last score reason.

## Credit and Performance Guardrails
- Keep holder metrics optional; only fetch via Tier-1 or when tier is Pre-Analyzed/Analyzed and within `tier1_credit_budget_per_run`.
- Snapshot writes should be batched; no extra Helius during Discovered hot refresh.
- Respect `hot_refresh_max_tokens` and age window; reuse existing settings/flags.

## Testing and Validation
- Unit: scorer given synthetic snapshots returns expected scores/buckets and explanations.
- Integration: hot refresh writes snapshots and triggers scoring; Tier-1 path writes holder metrics.
- UI: bucket filters, promote suggestion badge, tooltip text matches `score_explanation`.
- Backfill script (optional): score existing tokens using stored analysis data + a single DexScreener snapshot to seed history.

## Rollout Plan
1) Add schema changes (new table + columns); migrations only, no breaking changes.  
2) Implement snapshot writer in hot refresh and Tier-1 paths.  
3) Implement scorer + settings; wire into refresh/enrichment.  
4) Add control cohort selector job.  
5) Expose API endpoints and surface UI columns/filters/banner.  
6) Backfill scores for existing tokens; monitor credit usage and adjust thresholds/weights.
