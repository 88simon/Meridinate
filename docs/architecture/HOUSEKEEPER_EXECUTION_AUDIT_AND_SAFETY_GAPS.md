# Housekeeper Execution Audit and Safety Gaps

## Purpose

This document captures an audit of recent Housekeeper behavior after the Intel pipeline was reframed toward wallet reliability verification and bot-operator reporting.

It is intended as a handoff note for the main AI working on Meridinate.

## Question Being Answered

Is Housekeeper currently being run optimally after the recent prompt and architecture changes?

## Short Answer

No, not yet.

Housekeeper is directionally improved:

- it is starting from wallet reliability rather than only token-verdict cleanup
- it is using scoped write tools instead of freeform write SQL

But it is still not running optimally, and more importantly, it is not yet safe enough to trust fully for automated corrections.

## Main Conclusion

The current Housekeeper behavior has improved at the role level but still has three serious problems:

1. it still wastes effort trying to infer schema and column names
2. it still relies too heavily on ad hoc SQL instead of strong precomputed primitives
3. the scoped write tools appear to trust the model too much and do not independently validate the fix conditions

The third issue is the most important.

## What Improved

Compared with the earlier behavior, the current Housekeeper setup is better in important ways:

- it now frames itself as a wallet reliability verifier
- it uses scoped tools such as:
  - `fix_token_verdict`
  - `fix_multiplier_tag`
  - `update_wallet_tag`
- its prompt now distinguishes:
  - `data_reliable`
  - `trust_quality`
- it outputs structured JSON that downstream Investigator can consume

These changes are correct and should be preserved.

## What Is Still Going Wrong

### 1. Schema and Column Hallucination

Recent traces show Housekeeper trying queries using columns such as:

- `last_appearance`
- `is_resolved`
- `scan_timestamp`
- `created_at`

These are signs that the model is still trying to reconstruct the schema mentally instead of operating from the provided schema and prompt payload.

This is wasteful and lowers reliability.

### 2. Schema-Probing Behavior Still Exists

The traces also show Housekeeper attempting:

- `PRAGMA table_info(...)`
- `SELECT * ... LIMIT 1`

The current code already tries to block this behavior.

That means the problem is no longer "the model is allowed to do this."

The problem is:

- the prompt payload is still not strong enough to remove the model's urge to do it
- the agent is still burning iterations on blocked or unhelpful behavior

### 3. Logically Invalid Fix Reasoning

This is the critical issue.

The recent run included fixes like:

- "Actual multiple is 4.8x which floors to 5x, not 4x"
- "Actual multiple is 5.9x which floors to 6x, not 5x"
- "Current MC is only 32% of scan MC (below 10% threshold)"
- "Current MC is only 36% of scan MC (below 10% threshold)"
- "Current MC is only 51% of scan MC (below 10% threshold)"

These are mathematically wrong:

- floor(4.8) = 4, not 5
- floor(5.9) = 5, not 6
- 32%, 36%, and 51% are not below 10%

This means the model is still capable of issuing wrong corrections with high confidence.

## Why This Matters

Housekeeper is no longer just summarizing data.

It has scoped mutation powers.

That means reasoning errors are not just cosmetic.

They can produce incorrect database changes.

At that point the system stops being "a little noisy" and becomes an integrity risk.

## Code-Level Diagnosis

The current Housekeeper code already contains the right general direction:

- scoped write tools
- schema-probe blocking
- structured output

But the execution model is still too trusting.

The key issue is that the fix executors currently apply the requested change without independently validating the underlying invariant.

Examples:

- `_fix_token_verdict(...)`
- `_fix_multiplier_tag(...)`

These should not simply trust that the model's reasoning is correct.

They should recompute the rule server-side before mutating the database.

## What the Main AI Should Change

### 1. Make Scoped Fix Tools Self-Validating

This is the highest-priority change.

`fix_multiplier_tag` should:

- look up `market_cap_ath`
- look up `market_cap_usd`
- compute the correct integer multiple itself
- reject any request where `new_tag` does not match the recomputed result

`fix_token_verdict` should:

- look up current MC, scan MC, ATH, and any relevant existing verdict tags
- recompute whether the verdict rule is satisfied
- reject the request if the threshold condition is false

In other words:

- Housekeeper may propose the change
- the executor must verify the change

The model should not be the authority on arithmetic thresholds.

### 2. Push More Reliability Computation into Precompute

Housekeeper should receive more typed candidate data and do less ad hoc querying.

Instead of making Housekeeper derive reliability from scratch, precompute should already provide fields such as:

- `real_pnl_count`
- `total_positions`
- `resolved_tokens`
- `unresolved_tokens`
- `real_pnl_coverage`
- `rug_exposure`
- `has_funding_data`
- `is_sniper_bot`
- `last_seen`

That reduces the need for fragile custom queries.

### 3. Reduce Query Surface Area

Housekeeper should be narrow.

Its ideal workflow should be:

1. consume precomputed wallet reliability facts
2. classify reliability
3. flag blockers
4. propose verified fixes

It should not behave like a general-purpose exploratory SQL analyst.

### 4. Strengthen Prompt Prohibitions Further

Even with current blocks, the model still tries schema-probe behaviors.

The prompt should further emphasize:

- do not guess columns
- do not try to rediscover schema
- if the prompt payload lacks a field, mark it as a blocker instead of probing broadly

This should be paired with better precomputed inputs, not relied on alone.

### 5. Track Failed and Rejected Fix Attempts

If validation is added to scoped executors, Meridinate should also log:

- fix proposals made
- fix proposals accepted
- fix proposals rejected because invariant check failed

This creates a feedback loop for prompt tuning.

## What "Optimal" Would Look Like

An optimal Housekeeper run would look more like this:

- very few SQL queries
- no schema discovery attempts
- no guessed columns
- most wallet reliability conclusions derived from prompt payload
- only narrow confirmation queries for missing edge cases
- every write proposal independently validated by the backend before application

In that model:

- Housekeeper becomes a verifier and proposer
- the backend remains the arbiter of correctness

## Final Verdict

Current Housekeeper behavior is:

- better aligned than before
- not query-efficient enough
- still too dependent on model reasoning for factual corrections
- not yet safe enough to trust for unattended data mutation

The biggest change needed now is not another round of prompt tweaking.

The biggest change needed is:

- move invariant checking into the scoped fix executors

Until that happens, Housekeeper should be treated as a useful assistant for proposing fixes, but not yet a sufficiently trustworthy authority for arithmetic or threshold-based corrections.
