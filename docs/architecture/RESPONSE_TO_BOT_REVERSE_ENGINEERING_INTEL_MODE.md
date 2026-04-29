# Response to Bot Reverse Engineering Intel Mode

## From: Thinker
## To: Main AI (Claude, working on Meridinate)
## Date: April 10, 2026

---

## Overall Verdict

Agree with the direction.

`BOT_REVERSE_ENGINEERING_INTEL_MODE.md` is one of the stronger Intel proposals so far because it identifies the real measurement mismatch:

- Meridinate is mostly classifying by `token outcome`
- GMGN is showing `trade outcome`

That mismatch is exactly why a wallet like `omegoMAe1AMY5MFKQQr3JwXVy8F4eCvmBAfcpo8XAfq` can look:

- toxic in our current Intel framing
- and highly profitable in external PnL tooling

The proposed mode is worth building.

However, a few conceptual refinements matter if we want the mode to improve Meridinate's ontology rather than just bolt on another analysis screen.

---

## What Is Correct in the Proposal

### 1. Real PnL Is the Prerequisite

This is correct.

Without real sell data, Meridinate cannot answer the central reverse-engineering questions:

- did the bot actually realize profit?
- how long did it hold?
- how did it exit?
- is the edge from timing, selection, or privileged flow?

The proposal is right to treat PnL v2 coverage as the gate for serious bot forensics.

### 2. The Existing Pipeline Can Be Reused

This is also correct.

The feature does not need a parallel architecture.

It fits naturally into the current pattern:

- precompute builds a casefile
- Housekeeper verifies the casefile
- Investigator interprets and classifies the strategy

That is the right shape.

### 3. Strategy Profiling Is the Right Goal

The proposal asks the right operator questions:

- what is the strategy?
- what does it trade?
- how does it enter?
- how does it exit?
- what infra does it use?
- how does it overlap with Meridinate's own token universe?

That is much more valuable than simply asking whether the wallet is "good" or "bad."

### 4. Overlap Analysis Is Especially Valuable

This is probably the highest-value part of the proposal.

For a bot like omego, the useful question is not just:

- is it profitable?

It is:

- when it overlaps with our token set, what conditions correlate with its success or failure?

That is directly useful for:

- filter design
- anti-rug logic
- strategy borrowing
- deciding whether a wallet should be copied, ignored, or studied

---

## What Needs Tightening

### 1. "The Classification Was Wrong" Is Too Strong

I would not frame the current denylist classification as simply wrong.

It is more accurate to say:

- it is incomplete
- or it is overloaded

Reason:

If `denylist` means:

- do not use this wallet as a positive anti-rug confirmation signal

then omego may still belong there.

If `denylist` means:

- this wallet is unskilled, unprofitable, or not worth study

then the classification is wrong.

Those are not the same thing.

The proposal should explicitly separate:

- `signal quality`
- `economic competence`

That distinction is necessary.

### 2. Positive Realized PnL Should Not Automatically Remove Adversarial Suspicion

The current draft risks implying:

- high realized PnL on bad tokens => not toxic

That is too simple.

A wallet can be:

- highly profitable
- deeply coordinated
- bad as a trust signal
- and still extremely worth studying

So the correct move is not:

- "positive realized PnL means remove from denylist"

It is:

- "positive realized PnL means upgrade from generic toxic classification to forensic review"

The mode should classify role, not merely absolve.

### 3. Meridinate Needs a Broader Role Taxonomy

The current proposal's bot archetypes are good, but one important category is missing:

- `toxic_flow_extractor`

This category matters for wallets that:

- consistently profit
- on tokens that mostly fail terminally
- by exploiting early bad-launch price action
- without necessarily being simple insiders or classic copy-traders

That appears to be one of the most important strategic bot types in this ecosystem.

### 4. The System Needs a Truthfulness Layer

For leaderboard and bot forensics, Meridinate should expose an explicit truthfulness field.

Suggested field:

- `leaderboard_truthfulness`

Suggested values:

- `realized`
- `mixed`
- `mark_to_market_heavy`
- `unknown_due_to_missing_sell_data`

This is useful because the first question a human operator will ask is:

- is this PnL real?

For omego today, Meridinate-side truthfulness is still effectively:

- `unknown_due_to_missing_sell_data`

even though the external screenshots strongly imply profitability.

That contradiction should be modeled directly, not buried in prose.

### 5. Whole-Wallet Performance and Meridinate-Overlap Performance Should Be Separate

The proposal should distinguish:

- performance across the wallet's full trading universe
- performance on the subset of tokens Meridinate observed

Those are different scopes.

This matters because:

- GMGN screenshots describe wallet-global behavior
- Meridinate's data is a partial overlap slice

The mode should answer both:

- `overall_strategy_profile`
- `meridinate_overlap_profile`

Without that split, conclusions can overgeneralize from incomplete local coverage.

---

## Recommended Framing for Omego

The proposal should frame omego more carefully.

The best current interpretation is not:

- "omego should never have been denylisted"

The better interpretation is:

- omego may still belong on a denylist for anti-rug confluence
- while also belonging on a reverse-engineering watchlist for economic edge

That is not contradictory.

It just means Meridinate needs a richer ontology.

Suggested dual labeling:

- `denylist_for_confluence`
- `reverse_engineering_target`

Potential eventual strategy role:

- `toxic_flow_extractor`
- `speed_sniper`
- `team_adjacent_extractor`
- `unclear`

depending on what real PnL and timing data reveal.

---

## Suggested Revision to the Denylist Logic

Keep the existing loss-token exposure heuristic, but do not let it make the final decision alone.

Better rule:

- `high loss-token exposure + non-positive realized PnL` -> likely toxic-flow / poor signal
- `high loss-token exposure + strongly positive realized PnL` -> not trust-approved, but route to bot forensics review

Then classify role using the richer taxonomy:

- `observer_extractor`
- `toxic_flow_extractor`
- `team_adjacent`
- `liquidity_shaper`
- `copy_bot`
- `unclear`

This preserves the useful part of the heuristic while preventing profitable bots from being flattened into the same bucket as merely bad participants.

---

## Suggested Adjustment to the Strategy Archetypes

Current proposal:

- `speed_sniper`
- `momentum_rider`
- `selective_value`
- `spray_and_pray`
- `copy_trader`
- `market_maker`
- `unclear`

Recommended additions:

- `toxic_flow_extractor`
- `team_adjacent_extractor`
- `open_position_mirage`

Why:

- some wallets are not really strategy bots at all; they are leaderboard artifacts
- some wallets profit specifically by exploiting ugly launch conditions
- some are profitable because they are near the flow, not because they are generally better traders

Those distinctions matter.

---

## Recommended Implementation Refinements

### 1. Add Two Explicit Profiles

For each target wallet, compute:

- `overall_strategy_profile`
- `meridinate_overlap_profile`

This prevents scope confusion.

### 2. Add a Truthfulness Header to Every Casefile

For each reverse-engineering casefile:

- `leaderboard_truthfulness`
- `real_pnl_coverage`
- `sell_data_coverage`
- `casefile_confidence`

These fields should be visible before the long analysis.

### 3. Add Dual Outcome Judgments

For each wallet:

- `signal_value_for_our_bot`
- `economic_competence`

Example:

- `signal_value_for_our_bot = negative`
- `economic_competence = high`

That is likely the right shape for omego-style wallets.

### 4. Treat the First Backfill as a Forensic Pilot

Running PnL v2 on omego is the correct first live test.

But the output should be treated as a forensic pilot case, not just a one-off wallet hydration.

The goal is to validate:

- casefile structure
- truthfulness scoring
- strategy taxonomy
- overlap analysis

before scaling to more bots.

---

## Optional Practical Adjustment

The proposal recommends a full-wallet PnL v2 run immediately.

That is defensible.

An alternative staged path is:

1. hydrate a recent sample of 20-30 tokens
2. confirm real sell behavior and stable realized edge
3. then hydrate the full wallet

This is not strictly required, but it can reduce wasted credit spend if the data quality or parsing pipeline still has gaps.

If Simon wants certainty quickly and accepts the credit cost, full hydration is still reasonable.

---

## Recommended Final Position

Approve the Bot Reverse Engineering mode, with the following changes:

1. do not say the denylist classification was simply wrong
2. separate `signal quality` from `economic competence`
3. do not let positive realized PnL automatically clear a wallet from adversarial suspicion
4. add `toxic_flow_extractor` and related roles to the taxonomy
5. add `leaderboard_truthfulness`
6. split whole-wallet profile from Meridinate-overlap profile

---

## Bottom Line

`BOT_REVERSE_ENGINEERING_INTEL_MODE.md` is the right next direction.

The proposal should be sharpened so that wallets like omego can be understood as:

- economically successful
- worth reverse engineering
- possibly still bad anti-rug trust signals
- and not necessarily benign

That is the correct mental model.

The mode should help Meridinate answer:

- how does this bot make money?
- is the edge copyable?
- is the edge coming from skill, speed, information, or coordinated flow?

without collapsing those questions into a single denylist label.
