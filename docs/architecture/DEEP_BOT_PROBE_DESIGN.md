# Deep Bot Probe — Full Design Specification

## From: Main AI (Claude, working on Meridinate)
## To: Thinker
## Date: April 10, 2026

---

## Context

Simon has identified two high-value bot wallets for reverse engineering:

1. **omego** (`omegoMAe1AMY5MFKQQr3JwXVy8F4eCvmBAfcpo8XAfq`) — a bot our Intel pipeline mistakenly denylisted as "toxic flow" because 83% of the tokens it appeared on ended as verified losses. GMGN shows it's actually profitable every single day for months: $68.5K in February, $101.7K in March, $14.4K/week in April. 44% win rate by trade. Zero losing days.

2. **catfish** (`HK3J9zTFz3qBTNtcja3v9cZmSRfGEM3upXwK6GBuKHrT`) — Simon's friend from Discord, a known profitable bot operator making $3-9K/day with 43% win rate. We have partial PnL data (16/42 tokens computed).

### Why We Misclassified Omego

Our denylist rule: "wallets appearing on 70%+ verified-loss tokens = toxic flow." That rule catches rug infrastructure but also catches every high-frequency bot, because most PumpFun tokens crash regardless of who buys them. A speed bot that buys 156 tokens, exits fast on all of them, and profits on 44% will appear on 129 crash charts while being deeply profitable. We measured "did the token succeed?" instead of "did the trade succeed?"

### What We're Missing

Meridinate has **zero sell data** for omego. All 155 positions show `total_sold_usd: 0.0`, `sell_count: 0`, `pnl_source: 'estimated'`. PnL v2 was never computed for this wallet. Without sell transactions, our leaderboard shows $0 PnL and our Investigator classifies purely on token-level outcomes — a completely wrong picture.

Catfish has partial data: 16/42 tokens with real PnL. Those samples show hold times of 134s to 24,000s, entry sizes $130-$2,100, and consistent small profits ($15-$231 per trade). Enough to see the pattern, not enough to profile the strategy.

### The Goal

Build a probing system that fully reverse-engineers these bots: strategy, edge source, infrastructure, timing, sizing, token selection, exit behavior, daily consistency. Produce a dossier complete enough to inform the design of Simon's own trading bot.

### Budget

Simon has authorized up to 675,000 Helius credits (50% of 1.35M remaining) for this probe. The estimated cost is ~14,000 credits — roughly 1% of the authorized budget. Even at maximum depth, this is well within tolerance.

---

## Current Data Infrastructure

### What PnL v2 Already Does

`pnl_calculator_v2.py` computes real PnL per wallet-token pair:

1. `getTokenAccountsByOwner` → finds the wallet's token account for a specific mint (~10 credits)
2. `getSignaturesForAddress` on that token account → gets transaction signatures (~1 credit)
3. `getTransaction` on each signature → parses buy/sell amounts (~1 credit each)

**Current limitation:** `max_signatures=50`. For a high-frequency bot, some tokens might have more than 50 transactions (multiple buys, DCA in, partial sells). The probe should increase this.

**What it produces per token:**
- `total_bought_sol`, `total_sold_sol`
- `buy_count`, `sell_count`
- `realized_pnl_sol`
- `still_holding`, `current_balance`
- `first_buy_timestamp`, `last_sell_timestamp`
- `tip_detected` (Nozomi/Jito)
- `transactions[]` — array of individual buy/sell records with timestamps and amounts

### What PnL v2 Does NOT Do

- Does not discover tokens the wallet traded outside Meridinate's scanned set
- Does not compute hold durations per trade
- Does not track entry timing relative to token creation
- Does not profile strategy patterns across trades
- Does not compare bots against each other
- Does not store the full transaction array (only aggregates)
- Caps at 50 signatures per token account

---

## Proposed Architecture: The Deep Bot Probe

### New Service: `bot_probe.py`

A dedicated service that goes far beyond PnL v2. Not a modification of the existing calculator — a new purpose-built system for bot investigation.

### Phase 1: Full Transaction History

**Goal:** Capture every single trade each bot made on every token we know about.

**Approach:**
- Run PnL v2 logic but with `max_signatures=200` (not 50)
- Store the full `transactions[]` array, not just aggregates
- For each transaction, record:
  - `signature` (tx hash)
  - `direction` (buy/sell)
  - `sol_amount`
  - `token_amount`
  - `timestamp` (Unix + ISO)
  - `block_slot` (if available from parsed tx)
  - `tip_type` (nozomi/jito/none per transaction, not just per token)

**Per-trade derived fields** (computed in Python, zero credits):
- `entry_seconds_after_creation` — how many seconds after the token was created did this buy happen? Requires joining with `analyzed_tokens.analysis_timestamp` or creation event data.
- `hold_duration_seconds` — time between buy and corresponding sell
- `pnl_sol` — per-trade profit/loss (not just per-token aggregate)
- `pnl_multiple` — how many X on this specific trade
- `exit_vs_ath` — did the bot sell before, at, or after the token's ATH?

**Credit cost:**
- Omego (156 tokens): ~4,700 - 7,000 credits
- Catfish (26 remaining tokens): ~800 - 1,500 credits

**Storage:** New table `bot_probe_transactions` storing every individual trade. This is the raw evidence layer everything else builds on.

### Phase 2: Token Discovery — The Unknown Trades

**Goal:** Find tokens these bots traded that Meridinate never scanned.

**Why this matters:** Meridinate scans tokens from DexScreener every 15 minutes with specific filters (MC, volume, liquidity thresholds). These bots trade tokens from PumpFun within seconds of creation — many of which never hit our filters because they die before reaching the MC threshold. The bot's *full* trading universe is larger than our overlap.

**Approach:**
1. `getSignaturesForAddress` on the wallet's main SOL account (not token accounts) — last 500-1000 signatures
2. `getTransaction` on each — parse out all token mints involved in transfers
3. Cross-reference against `analyzed_tokens` — identify tokens we don't have
4. For unknown tokens: we now know the bot traded them but we don't have MC/outcome data. Record the mint address, timestamp, and direction.

**What this tells us:**
- True tokens-per-day count (not just the ones that overlap with our pipeline)
- Selectivity rate: "the bot saw N tokens created, entered M of them" (if we have RTTF data for comparison)
- Whether the bot trades tokens that never migrate from PumpFun (die on bonding curve)

**Credit cost:** ~500 credits per wallet

**Note for thinker:** This phase has a cost-accuracy tradeoff. Getting the last 500 main-wallet transactions catches recent activity well. Going to 1000+ catches more history but costs proportionally more. Given the budget authorization, even 2000 transactions (2000 credits per wallet) is trivial.

### Phase 3: Bot Profile Computation

**Goal:** From the raw transaction data, compute a complete strategy fingerprint.

**Cost:** Zero credits. Pure Python computation over stored data.

**Strategy Profile fields:**

```
=== PERFORMANCE ===
total_trades: int
total_tokens_traded: int
win_rate_by_trade: float       (% of trades with positive PnL)
win_rate_by_token: float       (% of tokens with net positive PnL)
total_realized_pnl_sol: float
avg_pnl_per_trade_sol: float
avg_pnl_per_win_sol: float
avg_pnl_per_loss_sol: float
expectancy_per_trade_sol: float  (avg_win * win_rate - avg_loss * loss_rate)
profit_factor: float           (gross_profits / gross_losses)
best_trade_sol: float
worst_trade_sol: float
daily_pnl_series: [{date, pnl_sol, trades, wins}]
daily_pnl_consistency: float   (% of days profitable)
max_drawdown_day_sol: float
longest_winning_streak_days: int
longest_losing_streak_days: int

=== ENTRY BEHAVIOR ===
avg_entry_seconds_after_creation: float
median_entry_seconds: float
entry_timing_distribution: {
  first_block (<2s): N%,
  lightning (2-10s): N%,
  fast (10-60s): N%,
  early (1-5min): N%,
  normal (5-30min): N%,
  late (>30min): N%
}
entries_per_day_avg: float
entries_per_day_distribution: [{date, count}]
time_of_day_distribution: {
  hour_0: N, hour_1: N, ... hour_23: N
}
day_of_week_distribution: {
  mon: N, tue: N, ... sun: N
}

=== EXIT BEHAVIOR ===
avg_hold_seconds_winners: float
avg_hold_seconds_losers: float
median_hold_seconds: float
hold_distribution: {
  flash (<30s): N%,
  quick (30s-2min): N%,
  short (2-10min): N%,
  medium (10min-1hr): N%,
  long (1hr+): N%
}
exit_before_ath_rate: float    (% of sells that happened before token peaked)
avg_exit_multiple: float       (avg sell_price / buy_price for winners)
stop_loss_estimate: float      (typical loss % when cutting a loser)
take_profit_estimate: float    (typical gain % when taking profit)

=== POSITION SIZING ===
avg_position_size_sol: float
median_position_size_sol: float
position_size_stddev: float
min_position_sol: float
max_position_sol: float
size_vs_mc_correlation: float  (does it size up for higher MC tokens?)
size_vs_time_correlation: float (does it size differently by time of day?)

=== TOKEN SELECTION ===
mc_at_entry_distribution: {min, p25, median, p75, max}
launchpad_breakdown: {pumpfun: N%, pumpswap: N%, raydium: N%}
tokens_with_meteora: N%
tokens_from_known_deployers: N%
overlap_with_meridinate_wins: N  (tokens bot traded that we marked verified-win)
overlap_with_meridinate_losses: N
selectivity_estimate: float    (if calculable: entries / tokens available)

=== INFRASTRUCTURE ===
uses_nozomi: bool (+ percentage of trades)
uses_jito: bool (+ percentage of trades)
nozomi_rate: float
jito_rate: float
standard_rate: float
estimated_priority_fee_sol: float  (if detectable from tx data)
```

### Phase 4: Comparative Analysis — Omego vs. Catfish

**Goal:** Side-by-side comparison of both bot strategies to identify what makes each one tick and where they differ.

**Cost:** Zero credits. Computation over Phase 3 outputs.

**Comparison dimensions:**
- Speed: Who enters faster? Entry timing distributions overlaid.
- Selectivity: Who trades more tokens per day? Who skips more?
- Sizing: Who bets bigger? More consistent or more variable?
- Hold time: Who exits faster on winners? On losers?
- Win rate: By trade, by token, by MC band.
- Expectancy: PnL per trade, profit factor.
- Infrastructure: Same tip system or different?
- Token overlap: How many tokens did both bots trade? On overlapping tokens, who performed better?
- Time patterns: Same hours? Same days? Or different schedules?
- Risk management: Who cuts losses faster? Who lets winners run longer?

**Output format:** Structured comparison JSON + human-readable report suitable for Intel Agent rendering.

### Phase 5 (Optional): Expanded Wallet Discovery

**Goal:** Find other bots in the ecosystem with similar profiles.

**Approach:** Using the strategy fingerprint from Phase 3, query the database for wallets with similar characteristics:
- Similar entry timing
- Similar token count
- Similar infrastructure (Nozomi/Jito tags)
- Overlapping token selections

This is speculative and depends on having enough wallets with real PnL data. Defer unless Phases 1-4 produce actionable results.

---

## Storage Design

### New Table: `bot_probe_transactions`

```sql
CREATE TABLE bot_probe_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_address TEXT NOT NULL,
    token_address TEXT NOT NULL,
    token_name TEXT,
    signature TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'buy' or 'sell'
    sol_amount REAL,
    token_amount REAL,
    timestamp TEXT,
    block_slot INTEGER,
    tip_type TEXT,  -- 'nozomi', 'jito', or null
    entry_seconds_after_creation REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_bpt_wallet ON bot_probe_transactions(wallet_address);
CREATE INDEX idx_bpt_token ON bot_probe_transactions(token_address);
```

### New Table: `bot_probe_profiles`

```sql
CREATE TABLE bot_probe_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_address TEXT NOT NULL UNIQUE,
    profile_json TEXT NOT NULL,  -- full strategy profile
    comparison_json TEXT,        -- filled when compared with another wallet
    total_trades INTEGER,
    win_rate REAL,
    expectancy_sol REAL,
    avg_hold_seconds REAL,
    infrastructure TEXT,         -- 'nozomi', 'jito', 'standard', 'mixed'
    computed_at TEXT,
    credits_used INTEGER
);
```

### New Table: `bot_probe_unknown_tokens`

```sql
CREATE TABLE bot_probe_unknown_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_address TEXT NOT NULL,
    token_mint TEXT NOT NULL,
    first_seen_timestamp TEXT,
    direction TEXT,
    in_meridinate_db INTEGER DEFAULT 0
);
```

---

## Integration With Existing Systems

### Intel Agent: New "Reverse Engineer" Focus Mode

After the probe data is collected and profiles computed, add a new Intel focus mode:

- **Focus: "reverse-engineer"**
- Housekeeper verifies probe data quality (complete transactions? gaps? suspicious patterns?)
- Investigator classifies the strategy archetype and produces the dossier
- Output includes actionable recommendations for bot design

### Denylist Rule Fix

The omego misclassification exposes a systemic flaw. The fix:

**Current rule:**
> Wallets on 70%+ verified-loss tokens → denylist candidate

**Proposed rule:**
> Wallets on 70%+ verified-loss tokens AND (no real PnL data OR negative realized PnL) → denylist candidate
> Wallets on 70%+ verified-loss tokens BUT positive realized PnL from helius_enhanced data → flag as "investigate as potential profitable bot" instead

This requires PnL v2 data to work correctly. Without sell data, the system cannot distinguish toxic flow from speed bots.

### Overlap Analysis: Bot vs. Meridinate Scores

For every token both a probed bot and Meridinate analyzed:
- Did the bot enter? At what timing?
- Did the bot profit?
- What was Meridinate's conviction/composite score?
- What was the token verdict?

This answers: "When omego enters a token that scores >70 composite AND <30% fresh wallets, it wins X% of the time." That's directly actionable for bot filter design.

---

## Credit Budget

**Authorized:** 675,000 credits (50% of 1.35M remaining)

**Estimated usage:**

| Phase | Omego | Catfish | Total |
|-------|-------|---------|-------|
| Phase 1: Full tx history | ~7,000 | ~1,500 | ~8,500 |
| Phase 2: Token discovery | ~1,000 | ~1,000 | ~2,000 |
| Phase 3: Profile computation | 0 | 0 | 0 |
| Phase 4: Comparison | 0 | 0 | 0 |
| **Total** | **~8,000** | **~2,500** | **~10,500** |

Usage: ~1.6% of authorized budget. Even with 10x overruns, it's under 16%.

The budget headroom means we can afford to be thorough rather than conservative: higher `max_signatures`, more main-wallet transaction history, deeper funding chain traces if interesting patterns emerge.

---

## Execution Plan

1. Build `bot_probe.py` service with Phase 1 + Phase 2 data collection
2. Build `bot_profile_builder.py` for Phase 3 computation
3. Run probe on omego first (larger dataset, higher value case study)
4. Run probe on catfish second
5. Run Phase 4 comparison
6. Fix the denylist rule to prevent future misclassifications
7. Add "reverse-engineer" Intel focus mode for future wallet investigations
8. Write findings doc for Simon

---

## Questions for the Thinker

1. Are there signals in the raw transaction data that the profile spec above is missing? Particularly around execution quality (slippage, fill rate, failed transactions).

2. Should the probe attempt to estimate the bot's *rejection rate* — how many tokens it saw but chose NOT to enter? This is hard without real-time data but might be estimable from RTTF detection timestamps vs. the bot's entry timestamps.

3. Is there value in probing the bot's *funding chain* more deeply? The funder of omego (`abc1LFfHbjZDCYS6Zrqqb5MLQHTvrr5PYuGKFw1vYuQ`) is unnamed — tracing where that wallet gets funded, and what other bots it funds, could reveal an operator network.

4. Should the Phase 4 comparison include a "what would happen if you combined both strategies" section? For example, "enter with omego's speed but use catfish's sizing and exit rules."

5. Any concerns about the storage design or the integration approach with the existing Intel pipeline?
