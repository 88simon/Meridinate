# Intel Pipeline Optimization Audit

## Purpose

This document captures a review of the latest exported Intel artifacts and answers a practical question:

- is the current Intel pipeline optimized?

Short answer:

- no, not yet
- it is materially improved
- it is now operationally useful
- but it is still inefficient in ways that are visible in both runtime and output quality

This is a handoff note for the main AI working on Meridinate.

## Artifacts Reviewed

The assessment is based on:

- `/mnt/c/Users/simon/Downloads/intel-report-5-general.md`
- `/mnt/c/Users/simon/Downloads/intel-report-6-general.md`
- `/mnt/c/Users/simon/Downloads/intel-bundle-6-general.json`

## Executive Judgment

The pipeline is no longer in the "interesting narrative demo" stage. It is now producing usable bot-operator intelligence:

- denylist candidates are relatively stable across runs
- Housekeeper is behaving more like a verifier
- Investigator is making fewer, more targeted queries
- export bundles are now good enough to support real debugging and AI handoff

However, it is still not optimized.

The two biggest reasons are:

1. too much context is being shipped into the run relative to how little the agents actually use
2. some important downstream behavior is still left to the model instead of being enforced deterministically

## What Is Working Well

### 1. Classification Stability Is Improving

The denylist set is starting to converge between runs.

Between reports `#5` and `#6`, 7 of the 8 denylist wallets overlap:

- `64hP97Bwr5PubotcTeGgfhkFrGiLVVxT2kVo9M9b4AEz`
- `8EmAjS1VMH37ftj5UpgRR8HJSms9g5uezF2NqsA2BtT3`
- `CCCCQCrL6zVjnDeucDzcxJgxAs5ahNmrhw1CDexPhqrd`
- `9oieEBu7gprdMmWrSKQFMk48DiCa3AH2edY2eZn8ortJ`
- `omegoMAe1AMY5MFKQQr3JwXVy8F4eCvmBAfcpo8XAfq`
- `78xcBq5Mu567Gea5Vs14hcjQ9YnkqDBzvTowW2MiW4G2`
- `5fCwsr1dP8cLE3zLYy7LTN37Ct2YqB1jBrsQPdN2LDV`

That is a good sign. The pipeline is finding a repeatable toxic-flow core instead of thrashing.

### 2. Housekeeper Is Acting More Like a Verifier

In report `#6`, Housekeeper:

- did not visibly fall into schema-probing loops
- returned structured wallet reliability data
- correctly collapsed the allowlist side into "no trust-approved wallets"
- handed Investigator a typed reliability block rather than just prose

That is much closer to the intended architecture.

### 3. Investigator Query Discipline Is Better

Report `#6` used:

- `6` tool calls
- across a small number of explicit questions

The transcript shows focused investigation rather than exploratory wandering:

- convergence funding check
- convergence overlap check
- high-rug wallet tag check
- deployer-linked buyer check
- cold wallet funding trace
- sybil overlap query

This is a meaningful improvement over earlier runs.

### 4. Export Bundles Are Already Paying Off

The new bundle format is useful.

`intel-bundle-6-general.json` includes:

- `metadata`
- `precompute`
- `housekeeper`
- `investigator`
- `transcript`
- `recommendations`

That is enough to inspect the run end to end without relying on screenshots or partial UI memory.

### 5. Recommendation Persistence Is Working

The bundle shows recommendation lifecycle state, including at least one recommendation already marked:

- `active_for_bot`

That means the proposal → review → activation flow is real, not just conceptual.

## What Is Still Not Optimized

### 1. Context Size Is Too Large for the Work Being Done

Report `#6` consumed:

- `135,704` input tokens
- `5,257` output tokens
- `241.4s` runtime
- `6` tool calls

That is not a good cost-to-work ratio.

The clearest reason is the `precompute` payload.

In the exported bundle, `precompute` is roughly `85 KB` of JSON. One section dominates:

- `precompute.meteora_tokens` is roughly `31 KB`

That section did not obviously drive the final report.

This suggests the pipeline is still over-feeding context to the agents and making them spend too much time reading material they do not materially use.

### 2. Recommendation Generation Is Still Too Model-Dependent

In report `#6`, the structured output contains:

- `8` denylist candidates
- `2` watch-only wallets
- `0` allowlist candidates

But only `6` recommended actions were emitted.

That means the output contract is still soft. The model is remembering some of the required action mapping, but not all of it.

This should not be left to prompt obedience alone.

### 3. Some Evidence Language Is Still Too Loose

The report is much better than the early "alpha king" era, but some phrasing still overreaches.

Example:

- "funded by major exchanges ... suggesting coordinated CEX withdrawal patterns"

Exchange funding by itself is weak evidence. It only becomes meaningful when combined with stronger signals such as:

- repeated co-appearance
- timing clustering
- shared non-CEX funders
- repeated deployer overlap

The pipeline is better at evidence now, but it still occasionally promotes weak support into medium-strength narrative language.

### 4. The Allowlist Side Is Still Weak

Housekeeper's structured result for report `#6` shows:

- `14` wallets in `wallet_reliability`
- only `2` with `data_reliable=true`
- `0` with `trust_quality="high"`
- `0` with `trust_quality="medium"`
- all `14` with `trust_quality="low"`

That is useful as diagnosis, but it also means the positive-signal discovery side is still not doing its job well enough.

Right now the pipeline is better at proving candidates are bad than at finding genuinely bot-usable good traders.

### 5. Transcript Fidelity Is Good, But Not Complete

The transcript is now persisted, which is a major improvement.

But it still mainly shows:

- thinking entries
- tool calls
- conclusions

It does not include tool results in a way that makes post-hoc reasoning audits easy.

That is enough for high-level review, but not enough for deep debugging of a bad classification.

## Practical Conclusion

The current pipeline is:

- operationally useful
- directionally correct
- materially better than the prior versions

But it is not yet optimized because too much of the run budget is spent on:

- oversized context
- non-deterministic action mapping
- weak positive-signal sourcing

## Proposed Next Optimization Package

The next optimization pass should be deliberately narrow.

Do not redesign the whole system again. Tighten the three bottlenecks that now matter most.

### Proposal 1: Introduce a Focus-Aware Lead Packet

Instead of handing the investigator the full raw precompute body, generate a smaller ranked packet per focus.

For `general` runs, the packet should include:

- a one-screen summary per lead family
- only the top few ranked examples per category
- identifiers or addresses the investigator can follow up on with tools if needed

In practice:

- keep `overview`
- keep compact convergence summaries
- keep compact denylist / high-rug summaries
- keep compact deployer-linked buyer summaries
- keep compact cold wallet summaries
- trim or omit large sections that are not referenced in the active focus

The clearest immediate target is:

- `meteora_tokens`

If that data is not directly driving the output for a general scan, it should not be injected wholesale.

#### Goal

Reduce general-run input token load by roughly `35% to 50%` without harming classification quality.

### Proposal 2: Move Recommendation Compilation Out of the Model

The investigator should still classify wallets.

But the final recommendation list should be compiled deterministically from the structured classification result.

That means:

- every high/medium denylist candidate becomes a denylist recommendation unless explicitly suppressed by rule
- every watch-only wallet becomes a watch recommendation unless explicitly suppressed by rule
- every omission should be explainable

The model should not be trusted to remember every required action mapping consistently.

#### Goal

Make recommendation coverage deterministic and auditable.

### Proposal 3: Split "Allowlist Discovery" From "Allowlist Rejection"

Right now the allowlist side is mostly reporting failure:

- no trust-approved wallets
- bad PnL coverage
- too much rug exposure

That is useful, but it is not enough.

The system needs an upstream lead-generation path specifically optimized for positive candidates that can realistically pass the threshold.

That means precompute should favor wallets with:

- high resolved sample size
- high real PnL coverage
- low rug exposure
- recent activity
- no Sniper Bot contamination

The current pipeline appears to be handing Housekeeper too many borderline or already-bad candidates and asking it to reject them.

#### Goal

Make the allowlist lane productive instead of purely diagnostic.

## Suggested Implementation Order

1. Reduce precompute/context size for the investigator
2. Deterministically compile recommendations from structured output
3. Rework allowlist candidate generation upstream
4. Persist tool results in transcript exports if deeper debugging is still needed

That order keeps momentum on the biggest wins first.

## Suggested Success Criteria

The next optimization pass should aim for outcomes like:

- general scans under `150s` on average
- materially lower input tokens per run
- no missing recommendation actions for structured denylist/watch outputs
- stable denylist overlap across repeated runs
- at least some genuinely trust-approved allowlist candidates emerging from the pipeline, or a clearly improved reason why none exist

## Bottom Line

The Intel pipeline is now good enough to use.

It is not yet efficient enough to call optimized.

The clean next step is not another prompt rewrite. It is a narrow systems pass:

- feed the agents less but better context
- make action generation deterministic
- improve the positive-signal sourcing lane

That is the shortest path from "working" to "sharp."
