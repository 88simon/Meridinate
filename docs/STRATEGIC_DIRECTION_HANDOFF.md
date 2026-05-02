# Strategic Direction Handoff

**Date:** May 2, 2026
**Supersedes:** April 30 version (kept in git history if needed)
**Purpose:** Single source of truth for the next session picking up Meridinate work. Read this first.

---

## TL;DR for the next AI session

**Where we are:** Meridinate is feature-complete enough for Phase 1 (data accumulation). Intel Agent now has the full feedback loop wired (Reclassify → Override Analyst → rules injected into next run's prompt). Wallet Shadow tracks live trades zero-credit. Wallet Leaderboard shows funding-chain terminals (CEX label). The hung-scan problem is fixed at the source. Tier 1-3 perf work is done; the app no longer drains CPU/GPU when Simon switches to BG3 or his trading terminal.

**What Simon needs to do:** Run Intel Agent regularly, click Track on most recommendations (default-to-shadow is the right bias in Phase 1), label tokens FAKE/REAL on the leaderboard, and let data accumulate for 2-4 weeks.

**What to NOT build:** New analysis features, Hermes Agent, multiplexed polling endpoints, new dashboards. Phase 1 is observation, not construction.

**What's next when Simon asks:**
- Tier 4 modularization (per-file refactor sessions for the 1k+ LOC files)
- Phase 2 pattern discovery queries (write *after* 2-4 weeks of Wallet Shadow data)
- Shadow Analyst agent (AI summarization of accumulated trade data) — also Phase 2

---

## The Core Problem (unchanged)

Simon is building toward an automated Solana memecoin trading bot. The reframe that anchors everything:

**Profitable bots are built by measuring markets carefully and exploiting patterns that show up consistently in the data.** You instrument first, patterns emerge, then you exploit them. The question is not "what's the secret?" — it's "what does the data reveal when 30+ profitable bots are tracked for 2-4 weeks?"

This shifts work into four phases:
- **Phase 1 (NOW): Data Accumulation** — track wallets, label tokens, let the dataset grow
- **Phase 2: Pattern Discovery** — statistical queries on accumulated data, build a Shadow Analyst agent
- **Phase 3: Filter Building + Backtesting** — translate patterns into bot entry logic
- **Phase 4: Execution Layer** — `solana-py` buy/sell, Hermes Agent for autonomous orchestration

---

## Current Position (as of May 2, 2026)

### What Meridinate has

**Pipeline:** Discovery → CLOBr enrichment → Helius analysis → MC Tracker → Position Tracker → Wallet Intelligence → Analytics → Intel Agents (Housekeeper + Investigator).

**Token analysis tools:** Token Leaderboard with rug labels (FAKE/REAL), Quick DD for ad-hoc due diligence, LP Trust Analyzer, Rug Score Detector (7 signals).

**Wallet tracking:**
- **Wallet Shadow** (renamed from Command Center, sidebar item now lives above the partition next to Intel/Bot Probe) — live WebSocket trade capture, zero credits
- Three tables: `wallet_shadow_targets`, `wallet_shadow_trades`, `wallet_shadow_preceding_buyers`, `wallet_shadow_convergences`
- Bot Probe — historical deep-dive (~hundreds of credits per wallet)
- Wallet Intelligence Report (WIR) with inline rename + Promote-to-Allowlist + Queue-Bot-Probe buttons
- Wallet nametags — global context (`WalletNametagsProvider`), one nametag per address, displayed everywhere

**Funding analysis:**
- Multi-hop funding tracer with exchange/protocol terminal detection (Helius identity API)
- Forward funding trace for sybil discovery
- **NEW: "Funded By" column on Wallet Leaderboard** — shows the labeled CEX (Coinbase 12, Binance, etc.) at the chain terminal, or the full untruncated address if opaque. Backfilled lazily 25 wallets at a time on each page render.

**Intel Agent (Housekeeper + Investigator):**
- Bot behavior profiler classifies wallets as Sniper/Scalper/Accumulator/Runner/Spray Bot
- Small-sample tentative tier (3-10 tokens) with `strategy_confidence` field — wallets no longer fall into "Unknown"
- Crash Trader / Profitable Scalper category — high rug exposure + high realized PnL routes to `monitor_wallet`, NOT denylist
- Pessimistic denylist: requires rug exposure AND one of (clustered, deployer-linked, flat PnL, sybil)
- Default-to-shadow rule: any uncertain wallet → `monitor_wallet`
- Housekeeper trust annotations spliced inline into investigation leads
- Saved transcripts replay in the report viewer (via `dialogue_json` column)

**Recommendation system:**
- Card simplified to **Track / Toxic / Skip** (was 5 actions × 7 reasons)
- Track auto-approves if Intel suggested `monitor_wallet`, otherwise reclassifies + fires Override Analyst
- Toxic requires explicit deny type (Deployer-linked / Sybil-cluster / Other)
- Skip is a true no-op (no signal, no rule, no tag change)
- "NEW" badge marks recommendations from the latest report
- Reclassify → Override Analyst (Sonnet 4 via existing Anthropic Console key) extracts a structured rule from operator override + wallet snapshot, persists to `intel_agent_rules`, injects into next Investigator run's system prompt
- Allowlist approval auto-shadows (one click adds to allowlist + Wallet Shadow targets)

**Codex panel:**
- Five category chips: Starred / Allowlist / Denylist / Shadowing / Watching
- Endpoint: `GET /api/codex/by-category` returns wallets grouped by tracking category with nametags hydrated
- Defensive fallback to `/api/starred` so Starred wallets always populate even if the new endpoint 500s

**Performance + reliability (Tier 1-3 of the optimization deep dive):**
- Per-token deadline (90s) on the auto-scan + heartbeat staleness detection (10 min) — solves the 7-hour hang
- `POST /api/ingest/scan-progress/reset` for manual stuck-state clearing
- 9 polling sites guarded with `document.hidden` — no background polling when tab is hidden
- Global CSS rule pauses all animations + transitions while `data-tab-hidden="true"`
- `TabVisibilityWatcher` mounted in dashboard wrapper toggles the attribute
- WIR + TIR lazy-loaded via `dynamic()` — smaller initial bundle
- Bot-tracker live feed defensively client-capped at 100 trades
- SQLite WAL + busy_timeout + 64MB cache_size + connect timeout via PRAGMAs in `get_db_connection()`
- Wallet Shadow's preceding-buyer capture moved to a 4-worker `ThreadPoolExecutor` (was unbounded `threading.Thread`)
- FollowUp tracker now evicts stopped tokens older than 24h
- Crime-coin analysis uses shared `get_db_connection()` and collapses 2 wallet_tags queries into 1
- `reload=True` gated behind `MERIDINATE_RELOAD` env var
- Backend uvicorn access log filter suppresses 2xx on 13 known polling routes (errors still log)

### What's still missing

- Critical mass of tracked wallets (currently ~3-10, target 30-50)
- Accumulated trade data on those wallets (need 2-4 weeks)
- Pattern discovery queries (write AFTER data accumulates)
- Shadow Analyst agent (AI summarization of accumulated shadow data)
- Execution capability (`solana-py` buy/sell)
- Backtest framework (needed for Phase 3)
- Tier 4 modularization (six 1k+ LOC files: tokens-table.tsx 2157, token-details-modal.tsx 1382, discovery-section.tsx 1210, wallet-intelligence-panel.tsx 1002, helius_api.py ~2k, ingest_tasks.py ~1.2k)

---

## Decisions made in the May 1-2 session (in chronological order)

These are the load-bearing decisions. If something looks weird in the code, this is probably why.

### 1. Override loop is AI-first, not prose-first

The original Reclassify form asked the operator to write airtight 3-paragraph prose ("which signal Intel got wrong + numbers + rule"). Simon pushed back: too high-friction, defeats the purpose.

**Decision:** Operator picks a category from a dropdown (~3 sec), backend AI extracts the rule from the wallet snapshot. The new `OVERRIDE_CATEGORIES` constant lives in `services/override_analyst.py` and is the source of truth for the dropdown.

### 2. Card simplification is the right shape

The Reclassify form (5 action types × 7 reasons) was the wrong shape for Phase 1. Most decisions are "shadow this so we can watch it." The right primitives are Track / Toxic / Skip.

**Decision:** Allowlist promotion + Bot Probe queueing leave the rec card and live on the WIR — they're post-observation decisions, not triage. Backend endpoints `POST /api/wallets/{addr}/promote-to-allowlist` and `POST /api/wallets/{addr}/queue-bot-probe` synthesize Intel-style recommendation rows for audit trail consistency.

### 3. Crash Trader is a real category

The 64hP97-style wallet (98% rug exposure, $47K+ realized PnL) is not toxic flow — it's a profitable scalper. Intel was conflating "touched bad tokens" with "is bad."

**Decision:** New `profitable_scalper_candidates` field in the Investigator's structured output. Compiled to `monitor_wallet` recs by the deterministic compilation in `routers/intel.py`. Pessimistic denylist: bare "high_rug_exposure" type alone is downgraded to `monitor_wallet` automatically. Default-to-shadow when uncertain.

### 4. The hung scan is fixed at the source, not patched

A scan ran for 7 hours stuck on token 5/8 ("xAI Voice Assistants"). One blocked Helius call inside `analyze_token()` froze the whole scan loop.

**Decision:** Per-token wall-clock deadline via `ThreadPoolExecutor.submit().result(timeout=90)`. Orphaned thread keeps running but the main scan loop continues. Heartbeat field in `_scan_progress` + auto-clear in `get_scan_progress()` after 10 min of staleness — UI never lies about "running" forever again.

### 5. Background drain on other apps is unacceptable

Simon noticed Meridinate consumed CPU/GPU even when in another tab — bled into BG3 + his trading terminal.

**Decision:** Tier 1 of the perf deep dive done in full. `document.hidden` guards on every polling site, CSS animation pause when tab hidden, status-bar 1-second tick stops too. Net effect: when the tab is hidden, the frontend is effectively dormant.

### 6. Tier 4 (modularization) is per-session, not bulk

Splitting tokens-table.tsx (2,157 LOC) properly is a multi-hour focused refactor. Doing 6 of them in one session = sloppy work + regressions.

**Decision:** Tier 4 happens one file at a time when Simon explicitly asks. Each session reads the file fresh, designs the split with full attention, validates carefully.

---

## Critical reframes (what to push back on)

### Don't push "understand first"
Simon sometimes falls into "I need to understand profitable bots before I build." Push back. The understanding emerges from observed data, not from theory.

### Don't add features when the bottleneck is data
Simon will be tempted to build more analysis tools. Almost always the right answer is "we already have what we need; the bottleneck is more data on more wallets." Be skeptical of new-feature requests in Phase 1.

### Don't multiplex polling for a perceived problem
Simon asked about consolidating 5 polling endpoints into one multiplexed call. That's good engineering but doesn't actually solve a real problem (HTTP traffic isn't the bottleneck; log noise was, and the access-log filter handles that). Defer until measurably needed.

### Don't make Claude Code a hard dependency
The Override Analyst uses Simon's Anthropic Console API key, not the Claude Code session. That pattern is intentional — the system needs to function when Claude Code isn't open.

---

## Open Questions / Pending Work

| # | Item | Status |
|---|------|--------|
| 1 | **Tier 4 modularization** — split the six 1k+ LOC files | Designed in deep-dive; needs per-file sessions |
| 2 | **Pattern discovery queries** | Wait for 2-4 weeks of Wallet Shadow data |
| 3 | **Shadow Analyst agent** | Design pending; build when data exists |
| 4 | **Backtest framework** | Phase 3, not designed |
| 5 | **Execution layer (`solana-py`)** | Phase 4 |
| 6 | **Hermes Agent integration** | Phase 4 (deferred indefinitely — agreed with Simon Apr 30) |
| 7 | **Helius RPC retry-with-backoff** | Flagged in scan deep-dive, not built. Lower priority than Tier 4. |

---

## Notes on Working with Simon

- **Non-technical vibecoder.** Explain concepts clearly but not condescendingly.
- **Wants to consult before implementing larger features.** Present the conceptual plan first; build only after he says yes.
- **Ambiguous language often signals real uncertainty.** Don't agree blindly — push back when his framing is off.
- **Active in Discord with experienced bot operators** (catfish, catcharge, CatneSs, zushi). Their methods inform direction.
- **Anthropic Console subscription** for Intel Agent + Override Analyst. Sonnet 4 model via `CURRENT_API_SETTINGS["intelModel"]`. Both keys in env: `ANTHROPIC_API_KEY` (Investigator + Override Analyst) and `ANTHROPIC_HOUSEKEEPER_KEY` (Housekeeper).
- **Runs Meridinate on home Windows 11 PC.** Backend on port 5003, frontend on port 3000.
- **Uses PumpFun tokens primarily** (pumpswap on DexScreener).
- **Restart workflow:** Simon restarts the backend manually after backend changes. `MERIDINATE_RELOAD` is opt-in for hot-reload during dev — default is now off.

---

## Where everything lives (quick reference)

| Concern | File |
|---|---|
| Investigator system prompt + structured schema | `apps/backend/src/meridinate/services/intel_agent.py` |
| Housekeeper agent | `apps/backend/src/meridinate/services/housekeeper_agent.py` |
| Intel precompute (leads + bot profiles + allowlist candidates) | `apps/backend/src/meridinate/services/intel_precompute.py` |
| Override Analyst (Reclassify → rule extraction) | `apps/backend/src/meridinate/services/override_analyst.py` |
| Recommendation executor (action handlers + reclassify) | `apps/backend/src/meridinate/services/recommendation_executor.py` |
| Recommendation REST endpoints | `apps/backend/src/meridinate/routers/recommendations.py` |
| Intel pipeline runner (background thread) | `apps/backend/src/meridinate/routers/intel.py` |
| Auto-scan with per-token deadline + heartbeat | `apps/backend/src/meridinate/tasks/ingest_tasks.py` |
| Wallet Shadow listener (WebSocket) | `apps/backend/src/meridinate/services/wallet_shadow.py` |
| Funding tracer + terminal persistence | `apps/backend/src/meridinate/services/funding_tracer.py` |
| Wallet Leaderboard query (with terminal JOIN) | `apps/backend/src/meridinate/routers/leaderboard.py` |
| Wallet nametag endpoints + by-category Codex | `apps/backend/src/meridinate/routers/tags.py` |
| Wallet promote-to-allowlist + queue-bot-probe | `apps/backend/src/meridinate/routers/wallets.py` |
| SQLite get_db_connection (with PRAGMAs) | `apps/backend/src/meridinate/analyzed_tokens_db.py:34` |
| FollowUp tracker eviction | `apps/backend/src/meridinate/services/followup_tracker.py:296` |
| Realtime listener crime-coin analysis | `apps/backend/src/meridinate/services/realtime_listener.py:600` |
| Uvicorn access log filter | `apps/backend/src/meridinate/main.py` |
| Wallet nametags context | `apps/frontend/src/contexts/wallet-nametags-context.tsx` |
| Tab visibility watcher | `apps/frontend/src/components/tab-visibility-watcher.tsx` |
| Visibility-aware polling hook (available, not yet adopted) | `apps/frontend/src/hooks/useVisibleInterval.ts` |
| Intel recommendations panel (Track/Toxic/Skip card) | `apps/frontend/src/components/intel-recommendations-panel.tsx` |
| WIR with rename + promote/probe buttons | `apps/frontend/src/components/wallet-intelligence-panel.tsx` |
| TIP (Token Intelligence Panel) | `apps/frontend/src/components/token-intelligence-panel.tsx` |
| Codex panel with category chips | `apps/frontend/src/components/codex-panel.tsx` |
| Wallet Leaderboard with Funded By column | `apps/frontend/src/app/dashboard/wallets/page.tsx` |
| Bot tracker (Wallet Shadow page) | `apps/frontend/src/app/dashboard/bot-tracker/page.tsx` |
| Intel page with saved-transcript replay | `apps/frontend/src/app/dashboard/intel/page.tsx` |

---

## What was deleted in this session

- `docs/architecture/INTEL_RECOMMENDATION_ACTIVATION_AND_NOTIFICATIONS.md` — fully implemented and superseded by Track/Toxic/Skip + Override Analyst loop
- `docs/architecture/INTEL_PIPELINE_OPTIMIZATION_AUDIT.md` — addressed by intel_precompute.py improvements + override loop
- `docs/architecture/HOUSEKEEPER_EXECUTION_AUDIT_AND_SAFETY_GAPS.md` — Housekeeper has SELF-VALIDATING fix tools; safety gaps are addressed
- `docs/progress/token-tags-implementation-summary.md` + `docs/migration/token-tags-migration-guide.md` — Nov 2025 migration, long since live
- `docs/architecture/RESPONSE_TO_*` — historical responses to design proposals that are now built

If you ever need the old text, `git log --all -- docs/` will surface the deletes.
