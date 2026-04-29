# Response to Deep Bot Probe Design

## From: Thinker
## To: Main AI (Claude, working on Meridinate)
## Date: April 10, 2026

---

## Overall Verdict

Agree with the direction.

`DEEP_BOT_PROBE_DESIGN.md` is a strong design document. It is the most complete end-to-end proposal so far for moving Meridinate from:

- token-outcome inference

to:

- trade-truth forensics

That is the correct direction for probing wallets like:

- `omegoMAe1AMY5MFKQQr3JwXVy8F4eCvmBAfcpo8XAfq`
- `HK3J9zTFz3qBTNtcja3v9cZmSRfGEM3upXwK6GBuKHrT`

The phased plan is sensible, the budget is realistic, and the integration intent is good.

However, the design still needs a tightening pass in a few important places:

- uncertainty vs toxicity
- accounting semantics
- token birth-time semantics
- transaction discovery hygiene
- job/coverage/versioning mechanics

---

## What Is Strong in the Current Design

### 1. It Identifies the Correct Root Problem

The doc correctly identifies the central measurement mismatch:

- Meridinate currently reasons mostly from `token outcome`
- profitable bots must be understood through `trade outcome`

That is the right conceptual starting point.

### 2. It Reuses Existing Infrastructure Sensibly

The design is grounded in what Meridinate already has:

- token-account scoped PnL computation
- tip detection
- wallet / token overlap data
- Housekeeper → Investigator workflow

That is good engineering. It avoids creating an unrelated parallel system.

### 3. The Phase Breakdown Is Strong

The phases are well ordered:

1. full transaction history
2. unknown-token discovery
3. profile computation
4. bot-vs-bot comparison

This is a coherent build sequence.

### 4. Overlap Analysis Remains One of the Highest-Value Ideas

This part is especially good.

For every token both a bot and Meridinate observed, asking:

- did the bot enter?
- did it profit?
- what did Meridinate score the token?
- what did the token ultimately do?

is exactly the kind of cross-system analysis that can improve Simon's own bot.

This section should be preserved almost exactly.

---

## What Needs Tightening

## 1. Missing Real PnL Data Is Not the Same as Toxicity

This is the most important conceptual correction.

The design currently proposes:

- high loss-token exposure AND `(no real PnL data OR negative realized PnL)` -> denylist candidate

I would not treat `no real PnL data` as a denylist condition.

That should map to uncertainty, not toxicity.

Better distinction:

- `negative signal for confluence`
- `economically unknown`
- `requires_probe`

Suggested interpretation:

- missing sell data means `unverified_for_confluence`
- negative realized PnL on bad-token exposure supports `likely bad signal`
- strong positive realized PnL on bad-token exposure supports `profitable but not necessarily benign`

The ontology needs to reflect that missing truth is not proof of adversarial behavior.

## 2. Positive Realized PnL Should Not Automatically Clear Adversarial Suspicion

The current design risks oversimplifying the opposite direction too:

- positive realized PnL on bad tokens -> investigate as profitable bot

That is directionally correct, but still incomplete.

A wallet can be:

- highly profitable
- deeply coordinated
- bad as an anti-rug trust signal
- worth reverse engineering

all at once.

So the system needs separate judgments for:

- `signal_value_for_our_bot`
- `economic_competence`

That distinction is crucial for wallets like omego.

Suggested outcome framing:

- `signal_value_for_our_bot = negative | neutral | positive | unknown`
- `economic_competence = high | medium | low | unknown`

Then add a role classification on top.

## 3. The Design Needs Explicit Cost-Basis Semantics

This is the biggest technical gap in the current spec.

The doc proposes:

- per-trade PnL
- hold duration per trade
- exit vs ATH

Those are useful, but they are not trivial if the bot uses:

- multiple buys
- multiple sells
- partial exits
- re-entry into the same token
- overlapping inventory

The design should explicitly choose a position-accounting method.

At minimum, the spec should define whether PnL and trade segmentation use:

- FIFO
- average cost
- or segmented round-trips

Without that, the resulting profile can look precise while hiding ambiguous assumptions.

This should be specified before implementation.

## 4. Entry Timing Must Use Real Token Birth Semantics

The design mentions:

- `entry_seconds_after_creation`

That is correct as a goal, but the source matters.

This should not be computed from:

- `analysis_timestamp`

because that is a Meridinate observation time, not token birth.

The design should prefer:

- token creation event time
- earliest on-chain tradable timestamp
- or explicit creation-event data already available in Meridinate

If no trustworthy birth signal exists, the system should say so and downgrade confidence.

## 5. Unknown-Token Discovery Needs Noise Controls

The Phase 2 idea is good, but the spec should define what counts as a trade.

Main-wallet token discovery will otherwise pick up noise such as:

- airdrops
- dust
- passive transfers
- unrelated token movements

The discovery step should include heuristics for identifying actual trading activity, such as:

- swap-like transaction patterns
- associated SOL or stablecoin flow
- DEX program involvement
- nontrivial amount thresholds

Otherwise the "unknown token universe" will become noisy quickly.

## 6. The Probe Should Be Job-Based and Resumable

I agree with a dedicated probe system.

But I would not treat it as a monolithic one-shot service only.

It should have job semantics:

- `probe_run_id`
- wallet target
- phase
- status
- started / completed timestamps
- credits used
- coverage metrics
- resumable progress

This matters because large wallets and deeper transaction scans will eventually produce:

- long runtimes
- retries
- partial results
- reruns under improved parsers

Without job structure, the system will become difficult to trust operationally.

## 7. The Storage Model Needs Versioning and Coverage Metadata

The proposed tables are a good start:

- `bot_probe_transactions`
- `bot_probe_profiles`
- `bot_probe_unknown_tokens`

But they need a bit more structure.

Recommended additions:

- `probe_run_id`
- `parser_version`
- `coverage_json`
- `source_confidence`
- `raw_count_metrics`

Example coverage fields:

- `known_tokens_probed`
- `known_tokens_total`
- `unknown_tokens_discovered`
- `transactions_fetched`
- `transactions_parsed`
- `sell_coverage_rate`
- `birth_time_coverage_rate`

This will matter a lot when comparing runs over time.

---

## Recommended Ontology Additions

The design would benefit from a slightly richer vocabulary.

### 1. Add `leaderboard_truthfulness`

Suggested values:

- `realized`
- `mixed`
- `mark_to_market_heavy`
- `unknown_due_to_missing_sell_data`

This helps answer the first human question quickly:

- is this leaderboard result real?

### 2. Split Profiles by Scope

For each bot, compute:

- `overall_strategy_profile`
- `meridinate_overlap_profile`

Why:

- wallet-global behavior and Meridinate-overlap behavior are not the same scope
- GMGN or wallet-global profitability may not map cleanly to the subset of tokens Meridinate saw

### 3. Add Missing Strategy Roles

The proposed archetypes are good, but they need at least one more category:

- `toxic_flow_extractor`

Potential additions:

- `team_adjacent_extractor`
- `open_position_mirage`

These roles are useful because some wallets are:

- profitable
- but profitable specifically on ugly, low-quality, or coordinated launches

That is not the same as classical discretionary skill.

---

## Answers to the Design Questions

### Q1. Are signals missing from the profile?

Yes.

Most important additions:

- explicit accounting methodology
- partial-exit handling
- re-entry segmentation
- transaction coverage completeness
- execution quality if derivable
- failed / retried transaction burst patterns if observable
- inventory overlap across simultaneous positions

The design should not skip these.

### Q2. Should the probe estimate rejection rate?

Potentially yes, but only with very careful scoping.

You cannot know true "tokens seen but skipped" from wallet history alone.

What you can estimate is:

- rejection relative to Meridinate-observed tokens
- rejection relative to RTTF-detected tokens in a given window

That should be labeled explicitly as an estimate, not global truth.

### Q3. Is deeper funding-chain probing valuable?

Yes, but after trade-truth.

The order should be:

1. verify profitability and execution profile
2. classify the strategy
3. then deepen the operator-network / funding-chain analysis

Trade truth should come first.

### Q4. Should comparison include "combined strategies" synthesis?

Low priority.

Interesting later, but not essential to the first useful version.

The first goal is understanding, not synthesis.

### Q5. Concerns about storage / integration?

Yes:

- resumability
- versioning
- coverage metrics
- explicit accounting logic

The integration direction itself is good.

---

## Recommended Final Position

Approve the Deep Bot Probe direction, with the following refinements:

1. treat missing real PnL as uncertainty, not toxicity
2. separate `signal_value_for_our_bot` from `economic_competence`
3. define explicit position-accounting semantics before implementation
4. use real token birth signals, not scan timestamps, for entry timing
5. add trade-discovery heuristics for unknown-token discovery
6. make the probe job-based, resumable, and coverage-aware
7. add `leaderboard_truthfulness`
8. split `overall_strategy_profile` from `meridinate_overlap_profile`
9. add roles like `toxic_flow_extractor`

---

## Bottom Line

`DEEP_BOT_PROBE_DESIGN.md` is the right next design direction.

It should be framed as:

- a forensic truth pipeline for profitable bots

not just:

- a bigger PnL backfill

That distinction matters.

The probe's job is not only to say whether a bot makes money.

Its job is to tell Meridinate:

- how the money is made
- whether the edge is copyable
- whether the bot is benign, coordinated, or exploitative
- and whether it should be used as a signal, ignored, or studied

That is the right destination.
