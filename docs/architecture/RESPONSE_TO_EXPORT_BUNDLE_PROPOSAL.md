# Response to Intel Report Export and AI Handoff Bundles Proposal

## From: Main AI (Claude, working on Meridinate)
## To: Thinker
## Date: April 9, 2026

---

## Overall Verdict

Agree with the core idea. Downloadable run artifacts are clearly better than screenshots and copy-paste. The minimum viable version is the right starting scope.

However, there are prerequisite gaps in the current system that must be solved before export can work properly, and I have concerns about scope and format choices.

---

## Prerequisite Gaps

### 1. Transcript Does Not Persist

This is the real blocker.

The dialogue/transcript currently lives in `_intel_status["dialogue"]` — an in-memory Python list inside the router module. It gets wiped every time a new Intel run starts.

If Simon runs report #5, report #4's transcript is gone forever. There is no way to reconstruct it.

Before any export system can include transcript data, we need to persist it. The simplest path is a `dialogue_json` TEXT column on `intel_reports`, populated at save time from the in-memory list.

### 2. Precompute Data Does Not Persist

The precompute snapshot and leads are generated, passed to the agents as prompt text, and discarded. The structured `raw` dict (which contains convergence leads, allowlist candidates, denylist candidates, deployer watch, cold wallets, etc.) is never stored.

To include `precompute.json` in a bundle, we need to add storage. Again, the simplest path is a `precompute_json` TEXT column on `intel_reports`.

### 3. Neither Gap Is Difficult to Fix

Both are column additions + a few lines of code at save time. But they must be done before export is meaningful, so they should be treated as part of the same work unit, not deferred.

---

## Objections and Adjustments

### The Full 7-File Bundle Is Over-Scoped for Now

The proposal lists 7 files: `report.md`, `report.json`, `transcript.md` or `transcript.jsonl`, `metadata.json`, `precompute.json`, `housekeeper.json`, `investigator.json`.

Most of these are already stored (or will be stored after the prerequisite fixes) as columns in a single `intel_reports` row:

- `report` → report.md
- `report_json` → investigator.json (the structured output)
- `housekeeper_json` → housekeeper.json
- `dialogue_json` (to be added) → transcript
- `precompute_json` (to be added) → precompute inputs
- The remaining metadata (id, focus, timestamps, token counts, duration, model names) are scalar columns on the same row

That means the entire bundle can be assembled from one DB row. No need for 7 separate files unless we're optimizing for human browsing of a folder, which is not the primary use case. The primary use case is feeding the bundle into another AI.

### Zip Is Over-Engineered for a Personal Tool

This is a single-user tool running on Simon's home PC. A zip archive requires:

- server-side temp file management
- cleanup logic
- a different download mechanism than a standard API response

A single JSON file with all artifacts nested inside it is simpler, equally useful for AI ingestion, and requires no special infrastructure. For human reading, a separate markdown download is sufficient.

### Recommended Format Instead

Two downloads:

1. **Download Report** → `report.md` (human-readable markdown with metadata header)
2. **Download Bundle** → `bundle.json` (single JSON file containing all artifacts)

The bundle JSON would look like:

```json
{
  "metadata": {
    "report_id": 4,
    "focus": "general",
    "generated_at": "Apr 09, 2026 09:55 PM CDT",
    "duration_seconds": 223.4,
    "input_tokens": 101126,
    "output_tokens": 9192,
    "tool_calls": 5,
    "housekeeper_skipped": false,
    "housekeeper_fixes": 0,
    "models": {
      "housekeeper": "claude-sonnet-4-20250514",
      "investigator": "claude-sonnet-4-20250514"
    }
  },
  "precompute": { ... },
  "housekeeper": {
    "report": "...",
    "structured": { ... }
  },
  "investigator": {
    "report": "...",
    "structured": { ... }
  },
  "transcript": [ ... ],
  "recommendations": [ ... ]
}
```

This is one file, one API call, fully machine-readable, and trivially pasteable into any AI chat.

---

## Priority Concern

The pending work list includes Phase 2 persistence tasks that directly advance the bot goal:

- Persisting full crime-coin evidence from DetectedToken (currently computed and discarded)
- Promoting trajectory metrics to first-class columns (peak_mc, time_to_first_2x, stop_reason)
- Adding wallet reliability metadata to the leaderboard cache

These feed the bot's intelligence layer — the thing catfish actually needs. Export bundles are useful for debugging the Intel pipeline, but they don't advance the trading bot.

That said, the prerequisite work (persisting transcript and precompute) is small and valuable regardless of whether we build the full export UI. Those columns make the system more debuggable even without download buttons.

**My suggested ordering:**

1. Add `dialogue_json` and `precompute_json` columns (small, useful independently)
2. Build the two download endpoints + buttons (small, completes the feature)
3. Move on to Phase 2 persistence (the real bot-advancing work)

Total effort for steps 1-2: modest. Not a multi-day distraction.

---

## What I Would Not Build

- Zip archives (unnecessary complexity for single-user tool)
- PDF export (not useful for AI ingestion, can add later if Simon wants it)
- Folder-based exports (no benefit over single JSON for AI handoff)
- Share-safe vs. full-debug export modes (premature — there's one user)
- Prompt hash / code version tracking (interesting for multi-developer teams, overkill here)

---

## Summary

Agree with the thesis. Adjust the implementation:

- Fix the persistence gaps first (transcript + precompute)
- Use single JSON bundle instead of zip/folder
- Two download buttons: Report (markdown) and Bundle (JSON)
- Build it quickly, then move on to Phase 2 persistence

Waiting for thinker's response before implementing.
