# Intel Report Export and AI Handoff Bundles

## Purpose

This document captures the approved idea of making Full Scan report artifacts downloadable so they can be fed back into AI systems more easily for review, debugging, comparison, and iteration.

It is intended as a handoff note for the main AI working on Meridinate.

## User Question, Precisely Articulated

Should Meridinate make Full Scan Report artifacts downloadable, including:

- the final report itself
- the self-dialogue transcript
- enough supporting structure to make it easy to feed the run back into ChatGPT, Claude, or another AI system

## Answer

Yes, this is a good idea.

It is better than relying on:

- screenshots
- copy-pasting fragments
- manually reconstructing a run from partial UI state

If the goal is to review and improve AI behavior, Meridinate should expose downloadable run artifacts.

## Core Recommendation

Meridinate should support an `AI handoff bundle` for each Intel run.

This should not be limited to the final markdown report.

The most useful export is a package of artifacts that captures:

- what the agents saw
- what they said
- what tools they called
- what structured outputs they produced
- what metadata and prompt version shaped the run

## Why This Matters

An exported report bundle makes it much easier to:

- review a run after the fact
- compare runs across prompt or code changes
- debug bad classifications or bad fixes
- feed the exact run back into another AI system
- create high-quality handoff context without screenshots or reconstruction

In practice, this is much more useful than only exporting the final report text.

## Recommended Export Types

Meridinate should ideally support three export modes:

### 1. Human-Readable Report Export

This is the simplest export.

Suggested file:

- `report.md`

Purpose:

- easy reading
- easy sharing
- easy paste into another chat

Contents:

- final report prose
- embedded structured JSON
- report metadata header

### 2. Transcript Export

This captures the self-dialogue and tool-call history.

Suggested files:

- `transcript.md`
- or `transcript.jsonl`

Purpose:

- debugging agent behavior
- reviewing tool use
- identifying hallucinated schema probes or bad fix logic

Contents:

- timestamps
- agent name
- message type
- content
- tool calls
- tool results if available

### 3. AI Handoff Bundle

This is the most important one.

Suggested format:

- a folder export
- or a zip archive
- or a single downloadable bundle assembled server-side

This bundle should contain all artifacts needed to reconstruct the run meaningfully.

## Recommended Bundle Contents

At minimum, each Full Scan bundle should include:

- `report.md`
- `report.json`
- `transcript.md` or `transcript.jsonl`
- `metadata.json`
- `precompute.json`
- `housekeeper.json`
- `investigator.json`

### `report.md`

Human-readable final report.

Should include:

- title
- generation timestamp
- focus
- prose report
- structured JSON block

### `report.json`

Machine-readable representation of the final result.

Should include:

- report id
- focus
- generated at
- duration
- token usage
- tool usage
- full structured output

### `transcript.md` or `transcript.jsonl`

Agent self-dialogue and tool-call timeline.

Should include:

- system steps
- Housekeeper thinking
- Investigator thinking
- tool calls
- fix attempts
- conclusion markers

`jsonl` is especially useful for machine ingestion and filtering.

### `metadata.json`

Critical for reproducibility and comparison.

Should include:

- report id
- focus
- generated at
- duration
- input tokens
- output tokens
- tool calls
- model names
- prompt version or prompt hash
- code version if available
- whether Housekeeper was skipped

### `precompute.json`

Structured precompute inputs.

Should include:

- overview
- convergence leads
- allowlist candidates
- denylist candidates
- deployer watch
- cold wallets
- pending verdicts
- multiplier verification candidates

This matters because AI review is much easier when the reviewer can see the exact leads the agents were given.

### `housekeeper.json`

Machine-readable Housekeeper result.

Should include:

- structured reliability output
- data fixes summary
- unreliable wallets
- verified wallets
- report blockers
- refresh-needed lists

### `investigator.json`

Machine-readable Investigator result.

Should include:

- allowlist candidates
- denylist candidates
- watch-only list
- supporting tokens
- open questions
- confidence
- blockers
- recommended actions

## Preferred Formats

### Strong Recommendation

Support both:

- a human-readable markdown export
- a machine-readable JSON export

This gives the best of both worlds.

### Avoid Making PDF the Primary Format

PDF is not ideal for AI workflows because:

- it is harder to parse cleanly
- it is not convenient for structured replay
- it is overkill for system debugging

PDF can be offered later as a convenience format for humans, but should not be the primary export for AI handoff.

### Avoid Screenshots as a Workflow Primitive

Screenshots are the weakest option because they:

- lose structure
- force OCR or manual reading
- omit hidden fields and metadata
- are harder to search and compare

Screenshots are fine for casual sharing, but not for serious AI iteration.

## Metadata That Should Be Preserved

To make exported bundles genuinely useful for AI review, preserve:

- prompt version or prompt hash
- agent model names
- report id
- focus
- generated timestamp
- tool counts
- token counts
- duration
- whether structured JSON was successfully parsed
- whether any fix actions were rejected or failed

Without this, it becomes harder to tell whether a behavioral change came from:

- prompt edits
- code changes
- data changes
- or random run variance

## Redaction and Safety Requirements

Before export, Meridinate should automatically avoid leaking secrets.

That means the bundle should not contain:

- API keys
- auth tokens
- private config values
- anything sensitive unrelated to the run

If internal prompt text is exported, it should be a deliberate product decision.

There are two possible modes:

- `share-safe export`
- `full internal debug export`

This distinction may be helpful later.

## Suggested UX

Meridinate should expose export actions such as:

- `Download report`
- `Download transcript`
- `Download AI handoff bundle`

These should be available from:

- the latest report view
- report history
- possibly the notification history if exports are tied to applied recommendations

## Suggested Bundle Naming

Use stable names that make sorting easy.

Example:

- `intel-report-2026-04-09-014703-general.zip`

Or folder form:

- `intel-report-2026-04-09-014703-general/`

## What the Main AI Should Optimize For

The export system should optimize for:

- reviewability
- reproducibility
- AI ingestion
- debugging

Not just for presentation.

That means structured artifacts matter as much as polished prose.

## Minimum Viable Export

If only a first version is built, it should include:

- final report markdown
- structured JSON
- transcript
- metadata

That is enough to make future AI review much easier.

## Ideal Future-State Export

The ideal state is an exportable handoff bundle that fully captures a run:

- precompute inputs
- Housekeeper output
- Investigator output
- transcript
- metadata
- recommended actions
- applied/rejected status if action workflow exists

That would make Meridinate much easier to iterate on as an AI-driven system.

## Final Summary

Yes, downloadable Full Scan artifacts are a strong idea.

The best version is not just "download the report."

The best version is:

- a readable report export
- a transcript export
- and an `AI handoff bundle` that packages the full run in both human-readable and machine-readable form

That will make it much easier to feed runs back into ChatGPT, Claude, or the main AI working on Meridinate.
