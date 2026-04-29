# Bot Reverse Engineering Intel Mode

## From: Main AI (Claude, working on Meridinate)
## To: Thinker + Simon
## Date: April 10, 2026

---

## The Case Study

Wallet `omegoMAe1AMY5MFKQQr3JwXVy8F4eCvmBAfcpo8XAfq` was classified by our Intel pipeline as:

- **Denylist: toxic flow** — 84% loss rate, appearing in convergence alerts

But GMGN shows:

- **$711K total PnL**, +1.52%
- **$14.4K/week realized**, 44.46% win rate
- **Profitable every single day** for months (Feb: $68.5K, Mar: $101.7K, Apr on pace for similar)
- **Zero losing days** across the entire screenshot range

This is one of the most successful bots in the ecosystem. And we put it on the denylist.

## Why the Classification Was Wrong

Our classification was based on a true but misleading fact: 129 out of 156 tokens this wallet appeared on as an early buyer ended up as verified losses. That's 83% — hence "toxic flow."

But "appeared on a losing token" is not the same as "lost money on that token." A speed bot that:

1. Buys early on many tokens
2. Sells within seconds to minutes
3. Takes small profits on ~44% of trades
4. Cuts losses quickly on the other ~56%

...will appear on tons of crash charts (because most meme tokens crash) while being deeply profitable on every single day. The win *rate* by token outcome is 15% in our data. The win *rate* by trade execution is 44% per GMGN. The difference is that our system measures "did the token succeed?" while GMGN measures "did the trade succeed?"

## Why We Have Zero Sell Data

This is the root cause. Our database shows:

- 155 positions, **0 with real PnL** (`helius_enhanced`)
- All positions: `total_sold_usd: 0.0`, `sell_count: 0`
- Every position is `pnl_source: 'estimated'`

PnL v2 was never computed for this wallet. Our system only auto-computes PnL for "recurring wallets" — wallets that appear in 3+ tokens from our auto-scan pipeline. This wallet qualifies (156 appearances), but the PnL backfill either hasn't reached it or skipped it.

Without sell data, our leaderboard shows `$0 PnL` and the Investigator classifies purely based on token-level outcomes, which paints a completely wrong picture.

## What PnL v2 Would Give Us

PnL v2 (`pnl_calculator_v2.py`) works by:

1. `getTokenAccountsByOwner` — finds the wallet's token account for a specific mint (~10 credits)
2. `getSignaturesForAddress` on that token account — gets all transactions for this wallet+token pair (~1 credit)
3. For each signature, `getTransaction` — parses buy/sell amounts (~1 credit each)

**Cost per token:** ~10 + 1 + N credits, where N = number of transactions (typically 1-20)

**For this wallet (156 tokens):** roughly 156 * 21 = ~3,276 credits. That's a meaningful spend but one-time.

**What we'd get per token:**
- `total_bought_sol`, `total_sold_sol`
- `buy_count`, `sell_count`
- `realized_pnl_sol` (actual profit/loss)
- `still_holding` (boolean)
- `first_buy_timestamp`, `last_sell_timestamp`
- `tip_detected` (Nozomi/Jito infrastructure)
- Full transaction list with timestamps

This transforms the wallet from "appeared on 156 tokens, 83% lost" to "traded 156 tokens, 44% won, $X realized per trade, avg hold time Y seconds."

## The Proposed Intel Mode: Bot Reverse Engineering

### Goal

Given a known-profitable bot wallet, answer:

1. **What is the strategy?** Speed, timing, selectivity, size, hold duration
2. **What does it trade?** Token types, MC ranges, time of day, launchpad preference
3. **How does it enter?** First-block sniper, early minutes, or delayed entry? Consistent sizing or variable?
4. **How does it exit?** Quick flip on profit, stop-loss on loss, time-based? What's the avg hold?
5. **What infrastructure does it use?** Nozomi tips, Jito bundles, advanced nonce?
6. **Where does it overlap with us?** Which of our analyzed tokens did it trade? What were its outcomes on those specific tokens?
7. **What signals predict its success?** When this bot enters a token that later wins, what was different about that token vs. the losses?

### Prerequisites

**This mode REQUIRES real PnL data.** Without sell transactions, we can't answer any of the questions above. The system must:

1. Check if the target wallet has PnL v2 coverage
2. If not, either:
   a. Run PnL v2 computation as a pre-step (expensive but one-time), or
   b. Refuse to run forensics and tell the user to run PnL backfill first

Option (a) is better UX but costs credits. Option (b) is safer but adds friction.

### Proposed Architecture

#### Pre-computation: Bot Profile Builder

For a target wallet with real PnL data, compute:

```
Strategy Profile:
  - total_trades: 156
  - win_rate_by_trade: 0.44  (not by token outcome)
  - avg_profit_per_win_sol: X
  - avg_loss_per_loss_sol: Y
  - expectancy_per_trade_sol: Z
  - avg_hold_seconds_winners: A
  - avg_hold_seconds_losers: B
  - avg_position_size_sol: C
  - position_size_variance: D
  - daily_pnl_consistency: E  (std dev of daily PnL)
  - max_drawdown_day: F

Entry Profile:
  - avg_entry_seconds_after_creation: G
  - entry_timing_distribution: [<10s: N%, 10-60s: N%, 1-5m: N%, 5-15m: N%, >15m: N%]
  - first_block_entry_rate: H%
  - uses_nozomi: bool
  - uses_jito: bool

Exit Profile:
  - avg_hold_winners: I seconds
  - avg_hold_losers: J seconds
  - exit_before_peak_rate: K%  (sold before token ATH)
  - stop_loss_behavior: L  (at what % loss does it typically exit?)
  - take_profit_behavior: M  (at what multiple does it typically sell?)

Token Selection Profile:
  - mc_range_at_entry: [min, median, max]
  - launchpad_preference: {pumpfun: N%, pumpswap: N%}
  - time_of_day_distribution: {0-6: N%, 6-12: N%, 12-18: N%, 18-24: N%}
  - tokens_per_day: avg N
  - selectivity: buys N% of tokens it sees (if we can estimate from our pipeline)
```

#### Housekeeper Role: Data Verification

Before the Investigator analyzes, Housekeeper should verify:

- Is PnL v2 data available and sufficient? (coverage threshold)
- Are the sell transactions real or are there gaps?
- Is the wallet still active? (last trade timestamp)
- Are there signs of wash trading in the transaction data? (sells back to self)
- Is the funding source identified?

#### Investigator Role: Strategy Classification

The Investigator classifies the bot into a strategy archetype:

- `speed_sniper`: enters first block, exits within seconds/minutes
- `momentum_rider`: enters early, holds through initial pump, exits on trend
- `selective_value`: enters fewer tokens but holds longer, higher win rate
- `spray_and_pray`: enters many tokens with small size, relies on home runs
- `copy_trader`: enters shortly after known good wallets
- `market_maker`: provides liquidity, profits from spread (unlikely for PF tokens)
- `unclear`: not enough data or mixed signals

And answers the key operator questions:

- **Replicability:** Can this strategy be copied? What would you need?
- **Edge source:** Is the edge from speed, selection, or information?
- **Infrastructure requirements:** What tip/bundle/nonce setup does this bot use?
- **Vulnerability:** What market conditions would break this strategy?

### Overlap Analysis: "Omego vs. Meridinate"

This is uniquely valuable because we have both the bot's trade data AND our own token analysis:

For every token both omego and Meridinate analyzed:
- Did omego buy it?
- Did omego profit on it?
- What was our conviction score / composite score?
- What was our verdict (win/loss)?
- Was there a signal combination that predicted omego's success?

This would tell us: "When omego enters a token that scores >70 on our composite AND has <30% fresh wallet concentration, it wins 62% of the time" — that's directly actionable for bot filter design.

### Comparison Mode: "Bot vs. Bot"

If Simon identifies multiple profitable bots, the system should support comparing them:

- Strategy archetype differences
- Win rate / expectancy comparison
- Entry timing comparison
- Infrastructure differences
- Token overlap (do they trade the same tokens? who enters first?)
- Performance in different MC bands

This would answer catfish's implicit question: "What separates a $3K/day bot from a $9K/day bot?"

## Data We Already Have vs. What We Need

### Already Have
- Token appearances (early_buyer_wallets)
- Token outcomes (verified-win/loss)
- Token metadata (MC, ATH, deployer, scores)
- Funding source
- Wallet tags
- Convergence data

### Need (via PnL v2)
- Per-trade buy/sell amounts and timestamps
- Per-trade hold duration
- Per-trade realized PnL
- Tip infrastructure detection (Nozomi/Jito)
- Transaction-level detail

### Would Be Nice (future)
- Block-level entry timing (which block did it buy in?)
- Entry price vs. 1-minute VWAP (to measure execution quality)
- Slippage estimation

## Immediate Concern: The Denylist Misclassification

The omego case exposes a systemic flaw in our denylist logic. Our current rule is:

> Wallets appearing on 70%+ verified-loss tokens = denylist candidate

This catches actual toxic flow (coordinated rug wallets) but also catches every high-frequency bot that trades many tokens, because most PumpFun tokens fail regardless of who buys them.

**The fix is not to remove the rule.** The fix is to add a qualifier:

> Wallets appearing on 70%+ verified-loss tokens **AND with zero or negative realized PnL** = denylist candidate
> Wallets appearing on 70%+ verified-loss tokens **BUT with positive realized PnL from real data** = investigate as potential profitable bot

This requires PnL v2 data to work. Without it, we can't distinguish "toxic flow that buys rugs" from "speed bot that buys everything and exits fast."

## Recommended Implementation Order

1. **Immediate:** Run PnL v2 on `omegoMAe1AMY5MFKQQr3JwXVy8F4eCvmBAfcpo8XAfq` as a manual test. This costs ~3,300 credits but gives us ground truth to validate the entire approach.

2. **Short-term:** Add a "reverse engineering" qualifier to the denylist precompute — check if high-appearance wallets have real PnL before classifying them as toxic flow.

3. **Medium-term:** Build the Bot Reverse Engineering Intel mode with the full profile builder, Housekeeper verification, and Investigator classification.

4. **Longer-term:** Overlap analysis (bot trades vs. Meridinate scores) and bot comparison mode.

## Cost Estimate

- PnL v2 for omego (156 tokens): ~3,300 Helius credits
- PnL v2 for each additional bot wallet: ~21 credits per token they traded
- Running the Intel mode itself: same as forensics (~$0.15-0.50 depending on model)

## Bottom Line

We accidentally denylisted one of the most profitable bots in the ecosystem because we measured "token outcomes" instead of "trade outcomes." The fix requires real PnL data, which we have the infrastructure to compute but haven't run on this wallet.

The broader opportunity is a Bot Reverse Engineering mode that answers: "What makes this bot work, and can we learn from it?" That's directly aligned with the goal of building Simon's own trading bot — learning from the best operators in the ecosystem is the fastest path to a viable strategy.
