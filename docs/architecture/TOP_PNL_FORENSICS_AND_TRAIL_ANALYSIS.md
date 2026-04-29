# Top PnL Forensics and Trail Analysis

## Purpose

This document captures a proposed expansion of the Housekeeper and Investigator roles beyond the current Full Scan workflow.

The core idea is:

- top-PnL leaderboard outliers are not automatically "good traders"
- they are forensic leads
- the system should explain what kind of event created that PnL, whether it was natural or coordinated, and where the trail went next

This is a handoff note for the main AI working on Meridinate.

## Problem Statement

The current Intel pipeline is optimized mainly for:

- trust / avoid / watch classification
- denylist discovery
- convergence / deployer / migration investigation

That is useful, but it leaves a separate high-value question under-served:

- what exactly are the top-PnL wallets on the leaderboard?

For many leaderboard outliers, raw PnL is not enough.

A wallet with:

- huge total PnL
- only 2 or 3 tokens traded
- low realized PnL
- a 0-second average entry
- deployer or cluster tags

should not be assumed to be a trader worth copying.

It may instead be:

- a single-home-run outlier
- an unrealized mark-to-market mirage
- a deployer or team-linked wallet
- a setup beneficiary
- a wash-amplified or coordinated participant

The right question is not only:

- is this wallet trustworthy?

It is also:

- what kind of win created this result?
- what kind of chart was the winning token?
- was the price action natural, supported, looped, washed, or self-bought?
- did the trail end here, or did the capital migrate somewhere else?

## Core Thesis

Housekeeper and Investigator should support a new Intel capability built around leaderboard forensics.

The split should be:

- Housekeeper = casefile builder
- Investigator = casefile interpreter

This is a better use of the two-agent system than forcing Investigator to rediscover all the raw facts from scratch.

## Proposed New Workflows

### 1. Top PnL Forensics

Input:

- top leaderboard outliers
- recently active profitable wallets
- wallets with unusually concentrated PnL

Goal:

- explain why a wallet is top-PnL

Output classifications:

- `repeatable_operator`
- `single_home_run`
- `open_position_mirage`
- `deployer_or_team_linked`
- `coordinated_setup_beneficiary`
- `wash_amplified`
- `unclear`

Key questions:

- how much of the wallet's total PnL is realized?
- is the profit concentrated in one trade or spread across many?
- is the wallet still holding the winning token?
- was the entry timing abnormal?
- does the wallet overlap with deployer-linked buyers, clusters, or toxic-flow infrastructure?
- is this a repeatable operator or a one-off event?

### 2. Best Trade Autopsy

Input:

- each top wallet's best trade

Goal:

- classify the chart and wallet behavior behind the biggest win

Key questions:

- what type of chart was this token?
- did the wallet enter near creation or at a normal early-entry point?
- was the chart organic or manipulated?
- did the wallet exit before peak, after peak, or not at all?
- was the PnL real and realized or mostly still open?
- were there related wallets or a shared funding pattern on the token?

### 3. Trail Continuation Analysis

Input:

- cold wallets with large historical wins
- wallets whose big win has gone inactive
- recipient wallets from migration / funding traces

Goal:

- answer whether the trail ended or moved

Output classifications:

- `trail_continues`
- `cold_migrated`
- `recipient_now_active`
- `trail_ended`
- `unknown`

Key questions:

- where did the SOL or proceeds go?
- did a recipient wallet later become active in early-buyer flow?
- was this a simple cold-storage move, an operational rotation, or a new active identity?
- should the recipient be watched as a continuation of the original trader?

### 4. Chart Nature Audit

Input:

- tokens tied to top-PnL wallets

Goal:

- classify price action itself, not just the wallet

Output taxonomy:

- `organic_breakout`
- `team_supported_markup`
- `wash_amplified`
- `deployer_self_buy_setup`
- `low_float_squeeze`
- `exit_liquidity_pump`
- `migration_driven_continuation`
- `unclear`

This is the right layer for answering questions like:

- was this natural?
- was this a setup?
- was this a wash?

## Expanded Role for Housekeeper

Housekeeper should not only verify wallet reliability for allowlist use.

For top-PnL forensics, it should build a structured casefile for each target wallet before Investigator reasons about it.

### Housekeeper Should Verify

- realized vs unrealized PnL share
- profit concentration in best trade
- still-holding vs exited state
- entry abnormality
- deployer / team / cluster / sniper contamination
- funding-data completeness
- whether the wallet's result is based on real PnL or estimated/stale marks
- whether the wallet is active, cold, or recently reactivated

### Suggested Housekeeper Casefile Fields

- `profit_concentration`
- `best_trade_share`
- `realized_share`
- `repeatability_score`
- `entry_abnormality`
- `position_state`
- `trail_status`
- `forensics_ready`
- `chart_targets`

### Suggested Position / Trail Fields

- `position_state = open | partial | exited`
- `trail_status = active | cold | migrated | unknown`

### Suggested Reliability Distinction

A wallet can be:

- reliable enough to analyze
- but not trustworthy enough to copy

That distinction matters even more for leaderboard forensics than it does for allowlist work.

## Expanded Role for Investigator

Once Housekeeper has built the casefile, Investigator should interpret it.

Investigator should answer:

- what kind of actor is this wallet?
- what kind of chart created the PnL?
- was the move natural or coordinated?
- was the PnL extracted cleanly or does it overstate real edge?
- did the trail end here or continue elsewhere?
- should this wallet be copied, watched, ignored, or treated as infrastructure?

## Existing Data Meridinate Can Already Use

Meridinate already has much of the raw material needed for this:

- `market_cap_usd`
- `market_cap_usd_current`
- `market_cap_ath`
- `market_cap_ath_timestamp`
- follow-up trajectory data
- `still_holding`
- `last_sell_timestamp`
- `exit_detected_at`
- funding traces from `funded_by_json`
- deployer-linked buyer evidence
- Meteora / stealth-sell signals

This means the feature is not conceptually blocked by missing data.

It mainly needs:

- better casefile assembly
- better mode separation
- better interpretation prompts

## What Housekeeper Should Derive for Token / Chart Forensics

For each token tied to a top-PnL wallet, Housekeeper should derive structured fields such as:

- `ath_multiple`
- `time_to_ath`
- `time_from_entry_to_ath`
- `did_wallet_exit_before_peak`
- `did_wallet_exit_into_strength`
- `post_peak_collapse_severity`
- `recovery_count`
- `holding_vs_distribution_pattern`

These derived fields are more useful for Investigator than raw columns alone.

## Suggested New Output Classifications

### Wallet-Level

- `repeatable_operator`
- `single_home_run`
- `likely_setup_beneficiary`
- `deployer_or_team_linked`
- `open_position_not_realized`
- `cold_migrated`
- `trail_ended`
- `trail_continues`

### Token / Chart-Level

- `organic`
- `team_supported`
- `wash_amplified`
- `self_buy_setup`
- `extraction_pattern`
- `unclear`

These labels would make leaderboard interpretation much more useful than raw PnL sorting alone.

## Why This Matters

Right now, the leaderboard can mix very different species of wallet:

- actual repeatable operators
- single-trade outliers
- coordinated or setup beneficiaries
- open-position mirages

Without a forensic layer, those all look superficially similar if they have large PnL.

That is dangerous for:

- copying
- allowlist discovery
- trader sourcing
- bot design

## Recommendation

Do not force this into the generic Full Scan only.

Add dedicated Intel modes built around leaderboard forensics:

- `Top PnL Forensics`
- `Best Trade Autopsy`
- `Trail Continuation Analysis`
- `Chart Nature Audit`

These should be first-class investigative workflows, not just side comments inside general scans.

## Proposed Working Split

### Housekeeper

- prepares the forensic packet
- verifies the PnL is real enough to analyze
- derives position / chart / trail fields
- flags contamination and missing data

### Investigator

- interprets the packet
- classifies wallet and chart type
- explains whether the move was natural, supported, washed, or set up
- explains whether the trail continues
- recommends `copy / watch / ignore / investigate`

## Bottom Line

Housekeeper and Investigator should not only answer:

- `trust / avoid / watch`

They should also answer:

- `what kind of win was this?`
- `what kind of chart produced it?`
- `where did the trail go next?`

That is the missing forensic layer for turning Meridinate's top-PnL leaderboard into actual intelligence rather than a list of suspiciously large numbers.
