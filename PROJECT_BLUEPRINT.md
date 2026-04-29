# Meridinate - Project Blueprint

**Updated:** April 28, 2026
**User:** Simon (non-technical background, vibecoder)
**Purpose:** Solana token intelligence platform with AI-powered analysis, Meteora stealth-sell detection, automated wallet/token investigation, and an evolving bot-operator intelligence layer

---

## What is Meridinate?

Meridinate is a comprehensive Solana token intelligence platform. It scans newly launched tokens, identifies early buyers, tracks wallets across multiple tokens, builds leaderboards, detects coordinated rug patterns (bundling, Meteora stealth-selling, sybil clusters), and uses AI agents to investigate the data and produce actionable intelligence reports. The approved direction for the Intel layer is to evolve those reports into structured bot-operator intelligence: trust/avoid/watch classification, allowlist and denylist discovery, and reviewable recommendations that can become bot-active after user approval.

**Core Pipeline (8 Stages + AI Layer):**
0. Real-Time Detection (Helius WebSocket) — detects PumpFun token creation instantly, scores conviction
0.5. Follow-Up Tracker — monitors MC trajectory for noteworthy tokens via DexScreener (free)
1. Token Discovery (DexScreener) — polls for migrated tokens every 15 min, applies pipeline filters
1.5. CLOBr Enrichment (optional, toggle in Settings) — fetches liquidity score for mature tokens during MC Tracker cycle, market depth for position-tracked tokens. Zero Helius credits. 12 req/min, 100K calls/month on Premium.
2. Token Analysis (Helius) — fetches early buyers, deployer, metadata, top holders (~30-80 credits)
3. MC Tracker (DexScreener) — age-decay polling, auto-verdicts (win/loss), win/loss tier labels
4. Token Scorer — momentum + smart money + risk scores (0-100 each) + fresh/bundle/stealth metrics
5. Position Tracker (Helius) — monitors wallet holdings, detects buys/sells, computes real PnL
6. Wallet Intelligence — funding trees, clusters, deployer profiling, tip detection (Nozomi/Jito)
7. Analytics — 40+ feature extraction, trajectory data, conviction accuracy, Meteora LP analysis
8. AI Intel Agents — Housekeeper (wallet reliability verification) + Investigator (bot-operator classification: allowlist/denylist/watch) + structured recommendations + forensics mode

---

## Architecture

### Stack
- **Backend:** FastAPI (Python 3.11) on port 5003
- **Frontend:** Next.js 15 (production build) on port 3000
- **Database:** SQLite (single file at `apps/backend/data/db/analyzed_tokens.db`)
- **APIs:** Helius (Solana data, paid credits), DexScreener (market data, free), PumpFun (token metadata, free), CLOBr (liquidity scores + market depth, paid Premium)
- **Real-Time:** Helius Enhanced WebSocket for PumpFun token creation streaming

### Pages
| Page | URL | Purpose |
|------|-----|---------|
| Wallet Leaderboard | `/dashboard/wallets` (HOME) | Full-DB wallet search with faceted filters, pagination, tag/tier filtering, leaderboard cache |
| Token Leaderboard | `/dashboard/token-leaderboard` | Full-DB token search with scoring, Meteora detection, bundle/stealth columns, TIR side panel |
| Command Center | `/dashboard/bot-tracker` | Combined RTTF token births + Bot Tracker live trade feed + intelligence panels (positions, heat map, signals, alerts, convergence) + pipeline controls |
| Intel Agent | `/dashboard/intel` | Bot-operator intelligence: Housekeeper (wallet reliability) + Investigator (allowlist/denylist/watch classification) + per-action recommendations + Forensics mode + export bundles |
| Bot Probe | `/dashboard/bot-probe` | Deep bot reverse engineering: full transaction history, FIFO round-trips, strategy profiling, bot comparison |
| Wallet Profile | `/dashboard/wallets/[address]` | Per-wallet drill-down with per-token PnL and external links |
| Codex | Sidebar panel | Starred wallets and tokens (favorites hub) with nametags |
| Tag Reference | Sidebar panel | Context-aware reference guide (wallet tags / token signals / RTTF labels) |
| Quick DD | `/dashboard/quick-dd` | Paste any token for instant full-pipeline due diligence with progress tracking |
| Rug Analysis | `/dashboard/rug-analysis` | AI-powered exploration of fake chart patterns using manually labeled training data |
| Settings | Modal from sidebar | Pipeline + Analysis + Intel tabs with real-time credit estimates |

### Intelligence Panels (slide-out, accessible from any page)
| Panel | Width | Purpose |
|-------|-------|---------|
| WIR (Wallet Intelligence Report) | 600px | Wallet profile, funding tree, PnL, token trades. Opens from any wallet address click |
| TIR (Token Intelligence Report) | 750px | Token scores, risk signals, Meteora analysis, tracked wallets, early buyers. Opens from token row click |

PanelStack system manages all slide-out panels (WIR, TIR, Codex) with shared backdrop and automatic left-to-right stacking. First panel opened sits at right edge, subsequent panels dock to its left. Click outside all panels to close everything. Click same address twice to toggle closed.

### Global Status Bar (always visible, top of every page)
- Next Token Discovery (countdown + last run credits) — click to pause/resume + "Run Now" button (triggers auto-scan immediately)
- Scan progress bar (shows current/total tokens + credits during active scan)
- Real-Time WebSocket status (ON/OFF + detection counts)
- Follow-Up Tracker (active tracking count + DexScreener rate)
- Next Token Price & Verdict Check (countdown + credits) — click to pause/resume
- Next Wallet Position Check (countdown + position stats) — click to pause/resume
- Tokens Being Polled (tier breakdown on hover)
- Helius Credits Today (used/budget + per-job breakdown)
- CLOBr enrichment status (ON/OFF + calls today, when enabled)
- Tokens Scanned Today counter in bottom status bar
- Paused pipelines show yellow "PAUSED" instead of countdown
- 3 scheduler jobs total: Token Discovery, MC Tracker, Position Checker (Tier-1 removed)

---

## Automated Systems

### Stage 0: Real-Time Token Detection (Helius WebSocket)
Streams PumpFun token creation events in real-time. Zero credits for detection.
- Conviction scoring from deployer history, safety checks, wallet tags
- Crime coin detection: 60-second watch window analyzes bundling, fresh buyers, funding convergence
- Market viability check at window close (DexScreener MC vs configurable threshold)
- Noteworthy tokens saved to `webhook_detections` table
- Labels: HIGH CONVICTION, WATCHING, WEAK, REJECTED
- Cross-links with auto-scan when same token is analyzed later

### Stage 0.5: Follow-Up Tracker (DexScreener, free)
Monitors MC trajectory for noteworthy tokens after watch window closes.
- Adaptive observation: extends on uptrend, cuts on flatline/crash
- Stores trajectory as `[{timestamp, mc, minutes_since_creation}]`
- Updates conviction labels as MC changes
- Configurable: duration (30 min - 8 hours), check interval (30s - 10 min)
- Rate limit awareness: tracks DexScreener calls/min, warns at 50/min

### Stage 1: Token Discovery (DexScreener, every 15 min)
Discovers tokens from DexScreener, applies pipeline filters, immediately runs Helius analysis.
- Configurable filters: launchpad, address suffix, MC, volume, liquidity, age, keywords, socials
- Cross-references with webhook detections (no longer skips rejected tokens)
- PumpFun API call after scan for cashback status + true ATH
- WebSocket notification on completion

### Stage 2: Token Analysis (Helius, ~30-80 credits per token)
Full on-chain analysis of each discovered token.
- Metadata: name, symbol, mint/freeze authority
- Deployer extraction from feePayer (Solana spec), cross-referenced with PumpFun creator
- Early buyer detection: up to 100 wallets spending $50+ in first 500 transactions
- Top holders: largest 20 holders with supply percentages
- Creation timeline: CREATE → ADD_LIQUIDITY → FIRST_BUY events

### Stage 3: MC Tracker (DexScreener, every 2 min, free)
Decay-based market cap polling. Newer tokens checked more frequently.
- Age intervals: 0-1h=2min, 1-6h=5min, 6-24h=15min, 1-3d=1h, 3-7d=4h, 7d+=12h
- ATH estimation from 5-minute price change data
- Auto-verdicts: verified-win (ATH >= 3x + break-even), verified-loss (90%+ drop, dead, stale 14d)
- Win multiplier labels: win:3x through win:100x
- MC trajectory metrics: volatility (coefficient of variation), recovery count
- Retirement rules: dead/finalized/stale tokens stop polling

### Stage 4: Token Scorer (Helius, 0-3 credits per token)
Three scores per token, all 0-100:
- **Momentum**: MC growth, ATH proximity, liquidity health
- **Smart Money**: Consistent Winner, Sniper (not Sniper Bot), High Value wallet counts
- **Risk**: Mint authority, freeze authority, holder concentration, holder velocity, deployer holding, early buyer overlap
- **Composite**: Weighted average (default 40/35/25) — adjustable in UI
- Holder distribution refreshed hourly (top1%, top10%, holder count)
- Derived signals: holder velocity, deployer still holding, early buyer/holder overlap

### Stage 5: Position Tracker (Helius, ~10 credits per check, every 5 min)
Monitors recurring wallet positions across all tokens.
- Detects balance changes via Helius `getTokenAccountsByOwner`
- Finds actual buy/sell transactions when balance changes
- Smart money flow computation (bullish/bearish/neutral per token)
- Hold duration stats (avg hold time, quick flip %, diamond hands %)
- Entry timing scores (Lightning Buyer tag for <60s entries across 3+ tokens)

### Stage 6: Wallet Intelligence (database, zero credits)
- **Funding trees**: 1-hop (direct funder) and 3-hop (deep trace) via Helius
- **Cluster detection**: wallets sharing a common funder
- **Fresh wallet detection**: tiered (Fresh <1h, <24h, <3d, <7d)
- **Wallet correlation matrix**: co-appearance across 3+ tokens
- **Deployer network**: deployers sharing funding source
- **Deployer profiling**: Serial Deployer, Winning/Rug/High-Value Deployer
- **Sniper Bot detection**: avg entry <30s across 5+ tokens, 80%+ under 60s

### Stage 7: Analytics & ML (database, zero credits)
- **Feature extractor**: 40+ features per token for ML classification
- **MC trajectory**: stored as last 20 readings, volatility + recovery metrics
- **Cross-system metrics**: webhook conviction vs actual outcome, time-to-migration
- **Conviction accuracy dashboard**: report card comparing birth predictions to verdicts
- **Token lifecycle records**: complete birth → trajectory → analysis → verdict story

### Real PnL Calculation v2 (~21 credits per wallet-token pair)
- Per-token-account approach: `getTokenAccountsByOwner` → `getSignaturesForAddress` on token account → parse buy/sell
- Computes actual SOL spent/received from real blockchain transactions
- No estimates anywhere — all read points filter for `pnl_source = 'helius_enhanced'`
- Wallets without real PnL show $0, not fabricated numbers
- Auto-computes for new recurring wallets after each auto-scan cycle
- Position tracker triggers v2 recompute after balance change detection
- SOL price from CoinGecko (reliable), dust filter skips trades < 0.01 SOL
- PnL Backfill Manager: start/stop/progress UI on Command Center page
- Recomputes behavioral tags (Consistent Winner/Loser) from real PnL data

---

## Tag System

### Wallet Tags (3 Tiers)
| Tier | Tags | Source |
|------|------|--------|
| 1 (Auto) | Exchange, Protocol, Cluster, Fresh (<1h/24h/3d/7d), High Value, Low Value, Active Trader, Holder, Deployer, Serial Deployer, Winning Deployer, Rug Deployer, High-Value Deployer, Correlated Wallet, Deployer Network, Sniper Bot | Helius / auto-detection |
| 2 (Computed) | Consistent Winner, Consistent Loser, Diversified, Sniper, Lightning Buyer | Meridinate behavioral analysis |
| 3 (Manual) | Insider, KOL, Watchlist | User-assigned |

### Token Labels
| Category | Labels |
|----------|--------|
| Source | auto:Manual, auto:TIP |
| Positions | auto:Position-Tracked, auto:No-Positions, auto:Exited |
| Performance | auto:Mooning, auto:Climbing, auto:Stable, auto:Declining, auto:Dead, auto:ATH |
| Signals | signal:Smart-Money, signal:Cluster-Alert, signal:Insider-Heavy, signal:Bot-Heavy, signal:Whale-Backed, signal:Smart-Bullish, signal:Smart-Bearish |
| Win Multiplier | win:3x, win:5x, win:10x, win:25x, win:50x, win:100x |
| Status | auto:Discarded |

### Token Verdict System
- **verified-win**: ATH >= 3x AND current >= 1x, OR ATH >= 1.5x AND current >= 1.5x
- **verified-loss**: 90%+ loss (6h gate), 70%+ loss (72h gate), dead (<$1k after 24h), stale (14d no verdict)
- Tier 3 (manual) verdicts never overwritten by auto-verdicts
- Win multiplier tags computed alongside verdict (win:3x through win:100x)

---

## Key Database Tables (15+ total)

| Table | Purpose |
|-------|---------|
| `analyzed_tokens` | All scanned tokens with MC data, scores, verdicts, deployer, creation events, analytics signals |
| `early_buyer_wallets` | Wallet-token relationships from analysis (up to 100 per token) |
| `mtew_token_positions` | Position tracking + real PnL (pnl_source: 'helius_enhanced' or 'estimated') |
| `wallet_enrichment_cache` | Cached Helius funded-by, identity data |
| `wallet_tags` | 3-tier wallet tag system |
| `wallet_nametags` | User-assigned wallet names |
| `token_tags` | Auto-verdicts + manual verdicts + win multipliers |
| `token_ingest_queue` | Discovery queue |
| `webhook_detections` | Real-time token detection records with conviction scores and trajectory data |
| `intel_reports` | Persisted Housekeeper + Investigator reports for historical review and comparison |
| `swab_settings` | Position tracker configuration |
| `multi_token_wallet_metadata` | Recurring wallet tracking metadata |
| `credit_transactions` | Helius API credit tracking |
| `operation_log` | High-level operation history |
| `analysis_runs` | Per-token analysis run history |
| `quick_dd_runs` | Quick DD run history with full report JSON |
| `rug_analysis_reports` | AI rug analysis reports |

---

## Key Backend Files

| File | Purpose |
|------|---------|
| `tasks/ingest_tasks.py` | Auto-scan, deployer tagging, sniper bot detection, auto PnL computation |
| `tasks/mc_tracker.py` | Decay-based MC polling, auto-verdicts, win multipliers, MC trajectory |
| `tasks/token_scorer.py` | 3-score system with holder refresh and derived signals |
| `tasks/position_tracker.py` | Position monitoring, smart money flow, hold duration, entry timing |
| `tasks/wallet_analyzer.py` | Wallet correlation matrix, deployer network detection |
| `tasks/feature_extractor.py` | 40+ ML feature extraction pipeline |
| `services/realtime_listener.py` | Helius WebSocket for PumpFun token creation + conviction scoring + crime coin detection |
| `services/followup_tracker.py` | Adaptive MC trajectory tracking post-watch-window |
| `services/pnl_calculator_v2.py` | Real PnL via per-token-account signatures (~21 credits/pair) |
| `services/pnl_backfill_manager.py` | Managed PnL backfill with start/stop/progress tracking |
| `services/dexscreener_service.py` | DexScreener API client (free) |
| `services/pumpfun_service.py` | PumpFun API (cashback, ATH, creator) |
| `services/funding_tracer.py` | Multi-hop funding chain tracer |
| `services/intel_precompute.py` | Intel lead generation, allowlist/denylist candidates, forensic casefiles, focus-aware context trimming |
| `services/housekeeper_agent.py` | Wallet reliability verifier with scoped write tools, self-validating fix executors, data-reliable vs trust-quality split |
| `services/intel_agent.py` | Bot-operator classifier: allowlist/denylist/watch/unclear with evidence discipline, forensics mode, recommended actions |
| `services/recommendation_executor.py` | Intel recommendation lifecycle: propose → approve → apply → revert with audit logging |
| `services/bot_probe.py` | Deep bot probe: full transaction collection, FIFO round-trips, unknown token discovery |
| `services/bot_profile_builder.py` | Strategy profiling: performance, entry/exit behavior, sizing, infrastructure, behavioral patterns, comparison |
| `services/wallet_shadow.py` | Real-time wallet tracking via WebSocket, preceding buyer capture, convergence detection |
| `routers/recommendations.py` | Intel recommendation approval/rejection/reversion endpoints |
| `routers/bot_probe.py` | Bot probe run/status/profile/compare endpoints |
| `routers/wallet_shadow.py` | Wallet shadow tracking/feed/signals/convergence/pipeline control endpoints |
| `routers/tokens.py` | Token endpoints, verdicts, top holders, ML features, sniper bot detection |
| `routers/wallets.py` | Wallet endpoints, enrichment, funding trace, deployer profiles, PnL computation |
| `routers/leaderboard.py` | Wallet + Token leaderboards with real PnL |
| `routers/ingest.py` | Auto-scan trigger, settings, realtime listener control, lifecycle, accuracy |
| `routers/intel.py` | Intel run/status/report endpoints and persistence |
| `routers/stats.py` | Status bar endpoint, credit stats, scheduler jobs |
| `routers/quick_dd.py` | Quick DD run/progress/history endpoints |
| `routers/rug_analysis.py` | Rug analysis run/reports endpoints |
| `services/clobr_service.py` | CLOBr API client with rate limiting and caching |
| `services/quick_dd.py` | On-demand parallel DD pipeline |
| `services/lp_trust_analyzer.py` | Fast LP creator trust assessment |
| `services/rug_detector.py` | 7-signal fake chart detection |
| `services/rug_analysis_agent.py` | AI-powered rug pattern exploration |
| `scheduler.py` | APScheduler job management |
| `helius_api.py` | Helius API client (RPC, Enhanced, Wallet API) |

---

## Key Frontend Files

| File | Purpose |
|------|---------|
| `app/dashboard/wallets/page.tsx` | Wallet Leaderboard (home) with deployer panel |
| `app/dashboard/wallets/[address]/page.tsx` | Wallet profile with real PnL, GMGN/Solscan links |
| `app/dashboard/token-leaderboard/page.tsx` | Token Leaderboard with signals column and creation dates |
| `app/dashboard/bot-tracker/page.tsx` | Command Center: RTTF + Bot Tracker + intelligence panels + pipeline controls |
| `app/dashboard/bot-probe/page.tsx` | Bot Probe: transaction probing, strategy profiles, bot comparison |
| `app/dashboard/intel/page.tsx` | Intel Agent: run/view reports, recommendations panel, export bundles |
| `app/dashboard/tokens/page.tsx` | Redirects to Command Center |
| `app/dashboard/tokens/tokens-table.tsx` | Token table with shared TokenAddressCell component |
| `app/dashboard/tokens/token-details-modal.tsx` | Detail modal: creation timeline, analytics signals, lifecycle |
| `components/layout/global-status-bar.tsx` | Always-visible status bar with all timers and indicators |
| `components/layout/header.tsx` | Top header with status bar row |
| `components/realtime-token-feed.tsx` | Real-time feed with crime coin analysis and lifecycle panel |
| `components/realtime-history-panel.tsx` | Audit view of persisted webhook detections |
| `components/conviction-accuracy.tsx` | Accuracy report card for conviction scoring |
| `components/lifecycle-panel.tsx` | Birth → trajectory → analysis → verdict view |
| `components/funding-tree-panel.tsx` | Cluster funding tree visualization |
| `components/deployer-panel.tsx` | Deployer profile with deployed tokens and win rate |
| `components/token-address-cell.tsx` | Shared address display with GMGN icon + copy |
| `components/wallet-tag-labels.tsx` | Wallet tag rendering with click handlers |
| `lib/wallet-tags.ts` | 3-tier wallet tag constants and styling |
| `types/token.ts` | Token type extensions, label system, win badge styling |
| `app/dashboard/quick-dd/page.tsx` | Quick DD: paste-and-analyze with progress + history |
| `app/dashboard/rug-analysis/page.tsx` | Rug analysis: label stats, run agent, view reports |
| `components/layout/panel-stack.tsx` | Shared slide-out panel orchestrator (WIR, TIR, Codex) |
| `hooks/useStatusBarData.ts` | Status bar data polling with event-driven revalidation |
| `hooks/useAnalysisNotifications.ts` | WebSocket notifications + DOM event dispatching |

---

## Event-Driven Revalidation

All pages auto-refresh via DOM events when background jobs complete:

| Event | Fired by | Listened by |
|-------|----------|-------------|
| `meridinate:scan-complete` | WebSocket notification | Command Center, Token Leaderboard, StatusBar |
| `meridinate:mc-refresh-complete` | WebSocket notification | Token Leaderboard, Wallet Leaderboard, StatusBar |
| `meridinate:position-check-complete` | WebSocket notification | Wallet Leaderboard, StatusBar |
| `meridinate:settings-changed` | Settings save, manual triggers | Global Status Bar, StatusBar |
| `meridinate:realtime-token` | WebSocket notification | Command Center (RTTF panel) |

---

## How to Start

```bash
scripts/start.bat    # Starts backend (port 5003) + frontend build + production server (port 3000)
```

Or manually:
```bash
cd apps/backend && .venv/Scripts/python -m meridinate.main    # Backend
cd apps/frontend && npx next build && npx next start           # Frontend (production)
cd apps/frontend && npx next dev                                # Frontend (development)
```

---

## New Systems (April 2026)

### Meteora Stealth-Sell Detection
Detects when PumpFun tokens have Meteora DLMM pools created for hidden exits.
- Phase 1: DexScreener detects Meteora pool existence (free)
- Phase 2: Helius RPC scans token transactions for Meteora program involvement, parses LP add/remove events
- Phase 3: Links LP actors to deployer/insiders via funding chains, cluster overlap, coordinated funding analysis
- Signals: `has_meteora_pool`, `meteora_creator_linked`, `meteora-stealth-sell` token tag
- Risk score: +10 for pool existence, +35 if insider-linked
- Key files: `services/meteora_detector.py`, `services/funding_cluster_detector.py`

### Tip Infrastructure Detection
Detects wallets using automated transaction infrastructure.
- 17 Nozomi tip addresses (Temporal priority landing)
- 8 Jito tip payment accounts (bundle inclusion)
- Tags: `Automated (Nozomi)`, `Bundled (Jito)`
- Detection runs during PnL v2 transaction parsing, zero extra credits
- Key file: `services/tip_detector.py`

### Bundle & Stealth Holder Detection
- Same-block clustering: 3+ wallets buying at exact same second = coordinated bundle
- Stealth holders: top holders with suspiciously small buys (holds 1%+ supply, spent <$200)
- Stored per token: `bundle_cluster_count`, `bundle_cluster_size`, `stealth_holder_count`, `stealth_holder_pct`

### Wallet Leaderboard Cache
Pre-computed wallet statistics for instant filtered queries.
- 3 tables: `wallet_leaderboard_cache`, `wallet_leaderboard_tags`, `wallet_leaderboard_tiers`
- Rebuilt after MC tracker and position checker jobs (~1.7s for 7K wallets)
- All filtering server-side via SQL JOINs: tags, tiers, hold time, home runs, starred
- API response: <11ms per query

### Starring System (Favorites)
- `starred_items` table: star any wallet or token
- StarButton component on all wallet/token surfaces
- Codex panel shows all starred items with nametags
- `starred_only` filter on both leaderboard APIs

### AI Intel Agents
Two-agent pipeline for bot-operator intelligence.
- **Pre-computation layer**: Python, zero cost, generates snapshot + allowlist/denylist leads + forensic casefiles. Focus-aware context trimming.
- **Housekeeper Agent** (separate API key): Wallet reliability verifier. Scoped write tools (`fix_token_verdict`, `fix_multiplier_tag`, `update_wallet_tag`) with self-validating server-side invariant checks. Splits data-reliable from trust-quality. Structured JSON output.
- **Investigator Agent**: Bot-operator classifier. Classifies wallets as allowlist/denylist/watch-only/unclear with evidence discipline. Forensics mode for top-PnL casefile analysis. Emits recommended_actions for downstream approval.
- Focus modes: general, convergence, deployer, migrations, starred, forensics
- Structured JSON output contracts on both agents, stored alongside prose
- Reports persisted to `intel_reports` with `report_json`, `housekeeper_json`, `dialogue_json`, `precompute_json`
- Deterministic recommendation compilation ensures every classification produces an action
- Export bundles: `report.md` + `bundle.json` (full AI handoff package)
- Key files: `services/intel_precompute.py`, `services/housekeeper_agent.py`, `services/intel_agent.py`

Reference docs:
- `docs/architecture/INTEL_AGENT_BOT_OPERATOR_ALIGNMENT.md`
- `docs/architecture/INTEL_RECOMMENDATION_ACTIVATION_AND_NOTIFICATIONS.md`

Key files:
- `services/intel_precompute.py`
- `services/housekeeper_agent.py`
- `services/intel_agent.py`
- `routers/intel.py`

### Loss Tier System
Granular loss categorization (mirrors win multipliers):
- `loss:rug` — 95%+ drop within 1 hour
- `loss:90` — 90%+ loss
- `loss:70` — 70-90% loss
- `loss:dead` — MC < $1K
- `loss:stale` — No verdict after 14 days

### Fresh Wallet Metrics (per token)
- `fresh_wallet_pct` — % of early buyers that were fresh wallets
- `fresh_at_deploy_count/total` — fresh wallets entering within 60s of creation
- `controlled_supply_score` — 0-100 combining fresh@deploy + cluster overlap + supply concentration
- `fresh_supply_pct` — % of supply held by fresh wallets

### Intel Recommendation Activation System
Structured proposal → review → approval workflow for Intel Agent recommendations.
- `intel_recommendations` table: lifecycle (proposed → approved → active_for_bot → reverted)
- `intel_audit_log` table: immutable audit trail
- `intel_bot_allowlist` / `intel_bot_denylist` tables: bot override layer
- 11 deterministic action handlers in `services/recommendation_executor.py`
- Per-action approve/reject/revert UI in Intel Agent sidebar
- Deterministic compilation: ensures every denylist/watch classification produces a recommendation

### Deep Bot Probe
Reverse-engineering system for profiling profitable Solana trading bots.
- Full transaction history collection with FIFO round-trip matching and cost basis tracking
- Unknown token discovery (tokens the bot traded outside Meridinate's scan set)
- Strategy profiling: win rate, expectancy, entry timing, exit behavior, position sizing, infrastructure
- Behavioral analysis: add-to-winner rate, partial takes, re-entry rate, multi-buy/sell patterns
- Bot-vs-bot comparison
- Key files: `services/bot_probe.py`, `services/bot_profile_builder.py`, `routers/bot_probe.py`
- Tables: `bot_probe_runs`, `bot_probe_transactions`, `bot_probe_round_trips`, `bot_probe_token_aggregates`, `bot_probe_profiles`

### Wallet Shadow (Real-Time Bot Tracker)
Zero-credit real-time wallet monitoring via Helius Enhanced WebSocket.
- Tracks multiple wallets simultaneously, captures every trade as it happens
- Pre/post token balance diffing (works for ALL DEX types including PumpSwap)
- Preceding buyer capture: on every BUY, identifies who bought before the tracked bot
- Signal wallet frequency analysis: discovers the bot's private allowlist over time
- Cross-bot convergence detection: flags when 2+ tracked wallets enter the same token
- Copy/follow alerts, sizing anomaly detection, token heat map, open positions dashboard
- Pipeline pause/resume: click-to-toggle in global status bar, PAUSED state visible on all pages
- Key files: `services/wallet_shadow.py`, `routers/wallet_shadow.py`
- Tables: `wallet_shadow_targets`, `wallet_shadow_trades`, `wallet_shadow_preceding_buyers`, `wallet_shadow_convergences`

### Command Center (Combined RTTF + Bot Tracker)
Unified real-time monitoring page at `/dashboard/bot-tracker`.
- Left panel: RTTF token birth feed with conviction scoring, crime coin analysis, watch windows
- Center panel: Bot trade feed with wallet filters, speed column, infrastructure badges
- Right panel: Intelligence stack (positions, token heat, alerts, convergence) + wallet management
- Bottom panel (toggleable): Conviction Accuracy dashboard or expanded Signal Wallets grid
- Replaces old `/dashboard/tokens` RTTF page (redirects automatically)

### CLOBr Integration
Score enrichment during MC Tracker cycle (not at discovery — tokens too new for CLOBr).
- Market depth for position-tracked tokens (support, resistance, S/R ratio)
- Toggle + warning threshold in Settings
- Status bar indicator
- Key file: `services/clobr_service.py`
- Columns: `clobr_score`, `clobr_support_usd`, `clobr_resistance_usd`, `clobr_sr_ratio`, `clobr_updated_at`

### Quick DD (On-Demand Due Diligence)
Paste any token address for instant full-pipeline analysis.
- Parallel pipeline: DexScreener + CLOBr + PumpFun (free) → Helius analysis → LP Trust + deployer trace
- Results persist to `quick_dd_runs` table with history view
- Progress indicator with 5-step pipeline visualization
- Key files: `services/quick_dd.py`, `routers/quick_dd.py`

### LP Trust Analyzer
Fast pool creator identification by querying pool address directly (2-3 credits vs 100+ for old Meteora scanner).
- Supports Meteora DLMM, Raydium CLMM, Raydium Constant Product, Orca Whirlpool
- Cross-references LP creators against deployer via funding trace
- Produces Liquidity Trust Score (0-100): percentage of liquidity NOT controlled by deployer
- Key file: `services/lp_trust_analyzer.py`
- Columns: `lp_trust_score`, `lp_trust_json`

### Rug Score Detector
7-signal fake chart detection formula (0-100, higher = more likely fake).
- Signals: vol/liq ratio, tx density, deployer dust funding, deployer funder unknown, small early buys, Meteora ghost pool, low pool count
- Computed automatically during auto-scan and Quick DD (zero extra credits)
- Key file: `services/rug_detector.py`
- Columns: `rug_score`, `rug_score_json`

### Rug Labeling & Analysis
Manual FAKE/REAL/UNSURE labels on Token Leaderboard via dropdown.
- AI analysis agent explores labeled data to discover new detection patterns
- Agent has database query tools, early buyer stats, deployer profiling
- Suggests weight/threshold adjustments to rug score formula
- Key files: `services/rug_analysis_agent.py`, `routers/rug_analysis.py`
- Tables: `rug_analysis_reports`
- Columns: `rug_label`, `rug_label_at`

### Forward Funding Trace
Traces where a wallet SENT money (forward hops), complementing existing backward trace.
- Reveals sybil distribution networks (single funder → multiple buyer wallets)
- Cross-references discovered wallets against token database for cluster detection
- Max 2 hops, 10 recipients per hop, cached permanently
- Key file: `services/funding_tracer.py` (trace_forward_chain function)
- WIR Funding Tree panel now has "Trace Back" / "Trace Forward" toggle

---

## API Keys & Configuration

- `apps/backend/config.json` — Helius API keys + Anthropic API keys + CLOBr API key (NEVER commit)
- `apps/backend/ingest_settings.json` — Pipeline filter settings + real-time detection settings
- `apps/backend/api_settings.json` — Analysis settings (wallet count=100, transaction limit=10000, etc.)
