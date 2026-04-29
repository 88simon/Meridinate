# Intel Agent Bot-Operator Alignment

## Purpose

This document reframes Meridinate's Intel pipeline around the actual operating goal:

- Build a stronger `good trader` allowlist for anti-rug confluence
- Build a stronger `toxic-flow` / adversarial / bot-cluster denylist
- Produce reports that help a future bot decide `trust / avoid / watch`

The current pipeline already contains many of the right signals, but it is still optimized more for an interesting human intelligence report than a bot-operator report.

## Core Thesis

The main mismatch is this:

- Housekeeper is mostly validating token-level hygiene
- Investigator is mostly producing narrative intelligence
- Precompute is mostly surfacing interesting winners

For the `catfish`-style use case, the pipeline should instead do this:

- Housekeeper verifies `wallet / report reliability`
- Investigator classifies `allowlist candidate / denylist candidate / unclear`
- Precompute feeds both `good trader discovery` and `toxic-flow discovery`

The shortest summary:

- Housekeeper should become a verifier of wallet/report reliability
- Investigator should become a classifier for `trust / avoid / watch`
- The pipeline should emit partly machine-readable outputs, not just markdown prose

## Why This Matters

Based on the Discord intelligence and bot strategy notes, the real problem is not generic alpha discovery. It is:

- finding more unknown but trustworthy traders to use as anti-rug confirmation
- identifying coordinated flow designed to bait bots
- understanding when convergence is bullish versus adversarial
- turning Meridinate into an intelligence layer a bot can consume

That means the system should answer:

- Is this wallet useful as a future allowlist signal?
- Is this wallet or cluster part of toxic flow that should be filtered out?
- Does this token look validated by good traders, or engineered to extract bots?

## Current Mismatch in the Codebase

### Housekeeper

Current state:

- `apps/backend/src/meridinate/services/housekeeper_agent.py`
- Prompt is centered on multiplier fixes, stale verdicts, and general data integrity
- Prompt payload mostly contains multiplier verification and pending verdict data
- Output is prose, not structured reliability metadata
- Write access is broad and freeform through `update_database`

Why this is insufficient:

- It improves leaderboard hygiene
- It does not sufficiently verify whether wallet-based conclusions are safe to trust in a bot-oriented report

### Investigator

Current state:

- `apps/backend/src/meridinate/services/intel_agent.py`
- Prompt is framed around "interesting patterns" and "actionable intelligence"
- Primary goal is to "find truly successful wallets and trace where they went"
- Output format encourages narrative sections instead of operator decisions
- It reasons over generic SQL and cached funding data rather than deterministic system primitives

Why this is insufficient:

- It still blends `copy this`, `watch this`, and `this might be coordinated`
- It does not force the model to classify a wallet or cluster as trustworthy, adversarial, or unresolved

### Precompute

Current state:

- `apps/backend/src/meridinate/services/intel_precompute.py`
- Lead generation is biased toward convergence, deployers, cold wallets, and Meteora
- This mostly finds interesting winners and suspicious token stories

Why this is insufficient:

- It does not create parallel lead sets for:
  - good trader discovery
  - toxic-flow recurrence
  - denylist building
  - allowlist confidence scoring

## Housekeeper Improvements

### Reframe the Role

Housekeeper should no longer be thought of as only a token-verdict janitor.

It should become the agent that verifies:

- whether a candidate wallet is trustworthy enough to reason about
- whether key evidence is stale, estimated, or incomplete
- whether a report is safe for downstream bot/operator usage

### High-Value Checks Housekeeper Should Run

Before Investigator reasons about a wallet, Housekeeper should verify:

- `real vs estimated PnL`
- `Sniper Bot contamination`
- `rug exposure`
- `stale / inactive wallet status`
- `funding cache completeness`
- `resolved sample size`
- `unresolved token share`
- `whether wallet quality is recency-supported or based on stale history`

### Better Write Model

Current `update_database` is too broad for this workflow.

Instead of one generic write tool, prefer constrained operations such as:

- `fix_token_verdict`
- `fix_multiplier_tag`
- `remove_bad_wallet_tag`
- `mark_wallet_unreliable`
- `queue_funding_refresh`
- `queue_wallet_recompute`

This gives:

- tighter safety
- easier auditability
- clearer downstream reasoning

### Structured Output

Housekeeper should emit machine-readable verification artifacts, not just prose.

Suggested structured fields:

- `wallet_quality_warnings`
- `unreliable_candidates`
- `requires_refresh`
- `safe_to_reason_about`
- `real_pnl_coverage`
- `resolved_sample_size`
- `report_blockers`

Right now Investigator only receives a truncated text summary. That loses the exact reliability flags it should use.

## Investigator Improvements

### Reframe the Role

Investigator should stop acting like a general memecoin analyst and instead act like a bot-operator classifier.

Its job is not just to explain what is interesting.

Its job is to decide:

- `allowlist candidate`
- `denylist / toxic-flow candidate`
- `watch-only`
- `unclear`

### Hard Classification Buckets

Every major finding should end in one of these buckets:

- `allowlist candidate`
- `denylist candidate`
- `watch-only`
- `unclear`

Without this, the current reports drift into ambiguity:

- "this wallet is good"
- "this cluster is coordinated"
- "copy this token"

Those are not the same conclusion.

### Force Specific Bot Questions

Instead of soft prompts like "assess if the convergence is organic," the agent should be forced to answer:

- Does this cluster validate a token as likely non-rug?
- Does this cluster look like adversarial bait flow?
- Should these wallets be tracked as trusted traders?
- Should these wallets be filtered out?
- Is this signal usable as anti-rug confluence?
- What would disqualify it?

### Better Report Format

Move away from hype or narrative-first labels such as:

- `alpha king`
- `copy play`
- `coordinated partner`

Prefer operator decisions such as:

- `add to watchlist`
- `do not whitelist yet`
- `flag as likely toxic-flow`
- `monitor for repeat co-entry`
- `use as anti-rug confluence only if 2+ known good traders also appear`

### Claim Typing

Require each major statement to be labeled as:

- `observed`
- `inference`
- `action`

This prevents the report from collapsing facts, hypotheses, and decisions into the same sentence.

### Query Discipline

Investigator should use a tighter query budget and query purpose:

- one confirmation query for allowlist candidates
- one adversarial query for denylist candidates
- one disconfirming query before making a strong recommendation

That encourages targeted reasoning instead of broad narrative expansion.

## Precompute and Pipeline Improvements

### Parallel Lead Sets

Precompute should not only find interesting winners.

It should create separate lead sets for:

- `good trader discovery`
- `toxic-flow discovery`
- `wallet migration / identity rollover`
- `recurrent suspicious clusters`
- `deployer-linked buyer groups`
- `future follow targets`

### Suggested Good-Trader Leads

Examples:

- wallets with high resolved win quality
- low rug overlap
- low cluster contamination
- recent profitable activity
- repeated presence on non-crash charts
- evidence of selective participation rather than spray-and-pray buying

### Suggested Toxic-Flow Leads

Examples:

- repeated same-funder clusters across launches
- fresh-funded clusters near creation
- deployer-linked buyer groups
- repeated co-entry groups on future crash charts
- high same-amount uniformity
- repeated suspicious launch-window behavior

### Reuse Existing Deterministic Logic

Meridinate already has deterministic evidence logic that the agents should consume directly:

- `apps/backend/src/meridinate/services/realtime_listener.py`
- `apps/backend/src/meridinate/services/funding_cluster_detector.py`

These are already the right evidence vocabulary:

- bundled launch behavior
- fresh buyers
- shared funders
- deployer-linked buyers
- time-clustered micro-funding
- fresh funding near creation
- smart-buyer counter-signals

The LLM should not have to rediscover these patterns from scratch.

## Prompting Improvements

### Investigator Prompt

The Investigator prompt should explicitly say:

- You are producing a bot-operator report, not a generic intelligence report
- Your goal is to expand allowlists and denylists
- Convergence is not automatically bullish
- Coordinated behavior can be either team launch support or adversarial bait flow
- Do not recommend a token buy unless the evidence also clears it as not likely adversarial flow
- Do not issue strong conclusions without disconfirming evidence

### Housekeeper Prompt

The Housekeeper prompt should explicitly say:

- Your role is to verify whether wallet-based conclusions are safe to trust
- Flag low-confidence candidate wallets before Investigator uses them
- Distinguish between:
  - missing data
  - stale data
  - estimated data
  - contaminated data
- Report structured reliability verdicts, not just fixes

### Output Contract

Both agents should output structured JSON in addition to prose.

Suggested Investigator fields:

- `candidate_good_wallets`
- `candidate_bad_wallets`
- `watch_only_wallets`
- `supporting_tokens`
- `confidence`
- `recommended_action`
- `open_questions`

Suggested Housekeeper fields:

- `verified_wallets`
- `unreliable_wallets`
- `refresh_needed`
- `report_blockers`
- `data_quality_notes`

## Infrastructure Improvements

### Persist More Real-Time Evidence

This is one of the most important gaps.

`DetectedToken` currently computes many bot-relevant fields during the real-time watch window, including:

- `crime_risk_score`
- `fresh_buyer_pct`
- `buyers_sharing_funder`
- `deployer_linked_to_buyer`
- `buy_amount_uniformity`
- `mc_at_30s`
- `unique_buyers_30s`

But `webhook_detections` only persists a reduced summary.

That means Meridinate is currently losing exactly the evidence the agents should later cite and learn from.

### Persist Follow-Up Trajectory as First-Class Metrics

Right now follow-up trajectory mostly lands in a JSON blob.

Promote important outcome fields into first-class columns:

- `peak_mc`
- `peak_minutes`
- `final_mc`
- `tracking_duration_minutes`
- `stop_reason`
- `max_drawdown_after_30s`
- `time_to_first_2x`
- `time_to_first_50pct_drawdown`

This will improve:

- analytics
- agent evidence quality
- future ML
- bot threshold tuning

### Add Deterministic Helper Tools for Agents

The agents should not rely only on generic SQL.

Add tools that answer core workflow questions directly:

- `classify_wallet_candidate`
- `get_wallet_outcome_breakdown`
- `get_cluster_repeat_history`
- `get_token_adversarial_signals`
- `compare_signal_outcomes`
- `get_wallet_reliability_profile`

This makes the LLM reason over stronger primitives.

### Narrow Housekeeper Writes

As noted above, broad freeform write access is not ideal.

Constrained operations are safer and easier to inspect.

## Missing Metrics Worth Capturing

This is the most important system-level section.

Meridinate already captures a lot of useful token and wallet data, but it is still missing several metrics that matter directly for bot-quality intelligence.

### 1. Signal Combination Outcomes

You already track conviction accuracy at a high level.

What is still missing is outcome by signal combination:

- `bundled + fresh + shared funder`
- `shared funder without smart buyers`
- `winning deployer + cluster overlap`
- `smart buyers present + no deployer link`
- `fresh-funded cluster + high amount uniformity`

This is critical for understanding which combinations are truly predictive.

### 2. Wallet Trust Quality

Add wallet-level trust metrics such as:

- resolved sample size
- unresolved sample size
- unresolved share
- rug exposure rate
- stale exposure rate
- recency-weighted win rate
- recency-weighted expectancy
- estimated-PnL share
- cluster-contaminated trade share

This is more useful than raw PnL alone.

### 3. Adversarial Recurrence

Track recurrence of suspicious actors and patterns:

- repeated same-funder groups
- repeated co-entry groups
- repeated deployer-linked buyer groups
- repeated suspicious clusters on later rug outcomes
- recurrence of fresh-funded launch clusters

This is the basis of a denylist score.

### 4. Good Trader Usefulness

Measure whether a wallet is actually useful as anti-rug confirmation:

- when this wallet appears early, what is the downstream win rate?
- how does that change when no toxic-flow signals are present?
- how selective is this wallet?
- does it show up on too many low-quality launches to be useful?

This is closer to catfish's actual problem than wallet PnL alone.

### 5. Toxic-Flow Persistence

Track how suspicious launch-window patterns correlate with bad outcomes:

- cluster size
- same-amount coefficient of variation
- near-creation funding
- hop-depth pattern
- deployer-link frequency
- crash-chart recurrence

This helps distinguish:

- legitimate momentum launches
- coordinated team support
- adversarial bait flow

### 6. Coverage / Confidence Metrics

Agents should know when they are reasoning over incomplete data.

Capture:

- funding-cache completeness
- percentage of candidate wallets using real PnL
- unresolved token share
- number of linked verdicts supporting a wallet claim
- age of last meaningful signal

Without this, the reports can sound overly certain.

### 7. Trajectory Quality Metrics

The follow-up tracker already collects useful raw data.

Derive:

- `time_to_first_2x`
- `time_to_peak`
- `time_to_first_major_drawdown`
- `max_drawdown_after_peak`
- `recovery_probability_after_dump`
- `survival time above key MC thresholds`

These are useful for:

- future execution tuning
- bot exits
- better token-quality scoring

### 8. Regime Metrics

Track signal performance by context:

- MC band
- launchpad / DEX
- time of day
- weekday
- market regime

Catfish explicitly notes different behavior at different MC ranges. Meridinate should measure that directly.

### 9. Future Execution Metrics

Once execution is wired in, add:

- detection-to-decision latency
- decision-to-send latency
- fill quality
- slippage by signal class
- adverse selection by signal class

This is the bridge from Meridinate intelligence to actual trading edge.

## Recommended Output Shape for Reports

For a bot-operator workflow, prefer this structure:

1. `Allowlist candidates`
2. `Denylist / toxic-flow candidates`
3. `Watch-only candidates`
4. `Supporting evidence`
5. `Confidence / blockers`
6. `Recommended action`

Optional human-readable prose can still exist, but the structured artifact should be primary.

## Recommended Rollout Order

### Phase 1: Low-Risk, High-Leverage

- tighten Housekeeper and Investigator prompts
- add structured output contracts
- change report framing to `trust / avoid / watch`
- expand precompute into allowlist and denylist lead sets

### Phase 2: Better Persistence

- persist full crime-coin / watch-window evidence
- promote key follow-up trajectory metrics into columns
- add wallet reliability metadata

### Phase 3: Better Deterministic Primitives

- build helper tools for wallet/cluster classification
- expose deterministic signal summaries to the agents
- reduce reliance on generic SQL for core decisions

### Phase 4: Better Analytics / ML

- add signal-combination outcome tracking
- add wallet trust quality metrics
- add adversarial recurrence metrics
- add regime-aware performance metrics

## Final Summary

The main improvement is not just "make the report smarter."

It is this:

- persist the right evidence
- verify reliability before reasoning
- classify wallets and clusters in bot-operator terms
- measure whether signals actually help build allowlists and denylists

If Meridinate does that, the Intel pipeline stops being a general narrative analyst and becomes a usable intelligence layer for a future bot.
