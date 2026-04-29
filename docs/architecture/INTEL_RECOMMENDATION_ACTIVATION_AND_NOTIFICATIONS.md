# Intel Recommendation Activation and Notification Workflow

## Purpose

This document captures the desired product behavior for turning Intel Agent recommendations into reviewable, auditable, bot-active system actions inside Meridinate.

It is intended as a handoff specification for the main AI working on Meridinate.

## User Question, Precisely Articulated

How should Meridinate be prepared so that Intel Agent recommendations can be reviewed by Simon, and if Simon agrees with a recommendation after vetting it himself, that recommendation can be activated safely inside the product?

More specifically:

- recommendations should not just exist as report prose
- they should become structured actions that Simon can approve
- approved actions should influence bot filters automatically
- Intel-specific tags and watchlists are acceptable if they are logged properly
- frontend notifications should show both:
  - newly proposed recommendations awaiting approval
  - changes that have already been applied

## Core Answer

Yes, Meridinate should be prepared for this.

The correct model is not to let report prose mutate the system directly. The correct model is:

1. Intel generates structured recommendations
2. Recommendations remain inert while they are in `proposed` state
3. Simon reviews recommendations one action at a time
4. On approval, the action is applied immediately
5. On approval, the action becomes bot-active immediately
6. Every change is logged, attributable, and reversible
7. The frontend notification feed shows both pending and applied Intel actions

This gives automation without allowing raw LLM prose to silently rewrite Meridinate.

## Approved Product Decisions

These decisions were explicitly confirmed by Simon:

- Bot activation should happen immediately on approval
- Approval should happen per action
- Intel recommendations may include removals as well as additions
- The frontend notification feed should show both:
  - proposed actions awaiting approval
  - applied changes already made

These decisions should be treated as hard requirements.

## Required Product Behavior

### Separation of Stages

Meridinate should clearly separate:

- `analysis`
- `proposal`
- `approval`
- `application`
- `bot activation`
- `revert`

Even though approval and bot activation now happen together, they are still logically distinct steps and should be stored separately in the audit trail.

### Recommendation Lifecycle

Each recommendation should support a lifecycle such as:

- `proposed`
- `approved`
- `applied`
- `active_for_bot`
- `failed`
- `reverted`
- `rejected`

Because approval is intended to make the action live immediately, `approved`, `applied`, and `active_for_bot` may occur in the same operation, but they should still be recorded explicitly.

### Per-Action Approval

Approval must happen one action at a time.

This means the UI should present each recommendation as an individually reviewable action with:

- exact target
- exact change
- reason
- confidence
- source report
- expected bot effect

Example:

- `Approve: add wallet 64hP97... to bot denylist`
- `Effect: this wallet will no longer count as positive anti-rug confluence`
- `Source: Intel report #N`
- `Reason: repeated convergence bait-flow behavior and high loss exposure`

### Immediate Bot Activation

When Simon approves an action:

- the system should apply it immediately
- the bot filter layer should begin using it immediately
- the action should generate a notification immediately
- the action should become part of the audit trail immediately

No additional activation step is desired.

### Additions and Removals

The system must support both:

- additions
- removals

This applies to:

- bot allowlist entries
- bot denylist entries
- watchlist entries
- Intel-specific tags
- Intel-specific bot overrides

Because removals are allowed and approval is immediately live, reversibility is mandatory.

## Recommended Action Types

The recommendation system should support explicit, narrow action types rather than raw freeform behavior.

Good initial action types:

- `add_bot_allowlist_wallet`
- `remove_bot_allowlist_wallet`
- `add_bot_denylist_wallet`
- `remove_bot_denylist_wallet`
- `add_watch_wallet`
- `remove_watch_wallet`
- `add_watch_token`
- `remove_watch_token`
- `add_intel_tag`
- `remove_intel_tag`
- `add_nametag`
- `remove_nametag`
- `queue_wallet_pnl_refresh`
- `queue_wallet_funding_refresh`
- `mark_wallet_unreliable_for_intel`
- `unmark_wallet_unreliable_for_intel`

These should be handled by deterministic executors, not by raw LLM-written SQL.

## Important Architectural Constraint

Intel recommendations should be allowed to influence bot filters automatically after approval.

However, Intel should not directly rewrite Meridinate's core ontology or historical truth labels just because a report recommends it.

That means:

- Intel can drive bot-facing override layers
- Intel can create Intel-specific tags
- Intel can create Intel-specific watchlists
- Intel can queue refresh/recompute jobs

But Intel should not casually overwrite core base tags such as:

- `Consistent Winner`
- `Consistent Loser`
- other foundational classification tags

If core truth mutations are needed, that should be a separate, tightly constrained path.

## Suggested System Model

### Recommendation Layer

Intel output should include a structured `recommended_actions` payload.

Each recommendation should contain fields like:

- `action_type`
- `target_type`
- `target_address`
- `payload`
- `reason`
- `confidence`
- `source_report_id`
- `status`
- `expected_bot_effect`

Example:

```json
{
  "action_type": "add_bot_denylist_wallet",
  "target_type": "wallet",
  "target_address": "64hP97Bwr5PubotcTeGgfhkFrGiLVVxT2kVo9M9b4AEz",
  "payload": {
    "list_name": "intel_denylist"
  },
  "reason": "158 appearances, 85% loss rate, convergence bait-flow pattern",
  "confidence": "high",
  "source_report_id": 2,
  "status": "proposed",
  "expected_bot_effect": "wallet will no longer contribute positive anti-rug confluence"
}
```

### Execution Layer

Recommendation application should happen through narrow handlers only.

That means:

- no direct execution from report markdown
- no freeform mutation instructions
- no broad SQL driven by prose

Instead:

- recommendation enters executor
- executor validates target and payload
- executor records before/after state
- executor applies change
- executor marks action as bot-active
- executor creates notification
- executor records audit log

### Bot Override Layer

Bot filter influence should work through an explicit override layer, not by mutating base scoring logic directly.

That means bot decisions should evaluate:

- base Meridinate logic
- plus approved Intel allowlist overrides
- plus approved Intel denylist overrides
- plus approved Intel suppressions

Benefits:

- reversible
- auditable
- separates base intelligence from operator overrides
- easier to explain later why the bot acted

## Logging and Audit Requirements

Every approved action should create a durable audit record.

The log should include:

- recommendation ID
- report ID
- action type
- target
- before state
- after state
- approved by
- approved at
- applied at
- active_for_bot
- revert data
- result

This is not optional.

Because removals are allowed and approval is bot-live immediately, Meridinate must be able to answer:

- what changed
- why it changed
- who approved it
- when it became active
- how to undo it

## Frontend Notification Requirements

The frontend should expose a notification feed that shows both:

- newly proposed Intel recommendations awaiting approval
- already applied Intel changes

This was explicitly requested and should be treated as part of the product requirement.

### Proposed Recommendation Notifications

These notifications should make it clear that action is pending.

They should show:

- action summary
- target
- confidence
- reason
- source report
- approve button
- reject button

### Applied Change Notifications

These notifications should make it clear that a live system change has already happened.

They should show:

- what changed
- what object was affected
- report source
- whether bot filters are now affected
- revert option

### Suggested Notification States

- `proposed`
- `applied`
- `failed`
- `reverted`
- `rejected`

### Suggested Notification Examples

- `Intel proposed 3 new denylist actions`
- `Wallet 64hP97... was added to the bot denylist and is now active`
- `Wallet BPoHE1... was added to Intel allowlist and bot filters were updated`
- `Funding refresh was queued for wallet A2Mwj...`
- `Removal from bot denylist failed due to missing target`
- `Applied Intel action was reverted`

## Safety Rails

These safety rails are required.

### 1. No Prose-Driven Mutation

Report prose must never apply changes directly.

Only structured approved actions may mutate the system.

### 2. Deterministic Executors Only

Application must run through named handlers, not raw freeform logic.

### 3. Reversibility

Every applied action must be reversible.

### 4. Explainability

Every bot-facing change should remain attributable to:

- the Intel report
- the recommendation
- the approval event

### 5. Namespaced Intel Effects

Intel-specific tags and watchlists should be clearly namespaced so they do not silently impersonate foundational system truth.

## What the Main AI Should Preserve

The main AI should preserve this design principle:

Intel recommendations can absolutely influence bot filters automatically after approval, but they should do so through structured, logged, reversible override layers rather than direct mutation of Meridinate's base truth model.

That is the balance between:

- automation
- auditability
- operator control
- future bot safety

## Recommended Minimum Viable Implementation Shape

At minimum, the system should support:

- structured Intel recommendations
- per-action approval UI
- immediate application on approval
- immediate bot activation on approval
- add and remove actions
- audit logs
- frontend notifications for both proposed and applied states
- per-action reversion

## Final Summary

The intended workflow is:

1. Intel produces structured recommendations
2. Recommendations appear in the frontend notification feed as `proposed`
3. Simon reviews each action individually
4. Approval immediately applies the action
5. Approval immediately makes the action bot-active
6. The applied action appears in notifications and audit logs
7. The action can later be reverted if needed

This is the correct preparation model for activating Intel recommendations inside Meridinate while keeping the system controlled, reviewable, and bot-safe.
