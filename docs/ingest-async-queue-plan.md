# Ingestion Async/Non-Blocking Execution – Implementation Guide

## Goal
Prevent ingestion actions (Tier-0/Tier-1/Promote) from blocking the API/UI. Move long-running work off the request thread, make it safe to navigate away, and keep the UI responsive.

## Current Problem
- Tier-0/Tier-1/Promote run synchronously in the request handler, doing multiple external calls + DB writes (SQLite). With a single Uvicorn worker, this can block other requests, causing pages (including the Ingestion page) to hang while a run is in progress.

## Strategy
- Make ingestion actions fire-and-forget: enqueue the job and return immediately with a job ID; process in a background worker (thread/executor). Provide status endpoints so the UI can poll or react to completion.
- Keep DB interactions short; use WAL mode if not already.
- Optional: increase Uvicorn/Gunicorn workers as defense-in-depth.

## Implementation Outline

### 1) Job Queue/Status Model
- Add a simple job status table (if arq/Redis is not used):
  - `ingest_jobs` table: `id` (uuid), `type` (tier0|tier1|promote), `status` (queued|running|done|error), `created_at`, `started_at`, `completed_at`, `summary` (JSON/text).
- If arq/Redis is available, use arq tasks instead; otherwise, thread pool + status table is sufficient.

### 2) API Changes
- Existing POST endpoints (`/api/ingest/run-tier0`, `/run-tier1`, `/promote`) should:
  - Generate a job ID, insert a “queued” record, submit the work to a background executor, and return `{job_id}` immediately.
  - Do not perform the work in the request thread.
- New endpoint: `/api/ingest/jobs/{job_id}` → returns status/summary.
- Optional: `/api/ingest/jobs/recent` → list recent jobs for UI display.

### 3) Background Execution
- In `ingest_tasks.py`, add functions to run Tier-0/Tier-1/Promote that accept a `job_id` and update job status:
  - Set status → running, `started_at`.
  - Perform existing logic (Dexscreener fetch, Helius enrichment, promotion) in the executor.
  - On completion, set status → done, `completed_at`, and store a summary (counts, credits used).
  - On error, set status → error with message.
- Use `concurrent.futures.ThreadPoolExecutor` (or arq/Redis if available) for background work.

### 4) UI Changes
- On Run Tier-0/Tier-1/Promote button click:
  - Call the endpoint, get `job_id`, show a toast: “Running in background; you can leave this page.”
  - Start polling `/api/ingest/jobs/{job_id}` every few seconds until done/error. (Lightweight polling; or use WebSocket if available.)
  - Show per-row “in progress” indicators as before while polling; clear when job completes; refresh data.
- If the user leaves and comes back, allow resuming polling using the last job ID (optional).

### 5) DB/SQLite Considerations
- Ensure SQLite is in WAL mode (if not already) to reduce write contention.
- Keep transactions short; bulk updates in small chunks.

### 6) Worker/Server Settings
- Optional: run Uvicorn/Gunicorn with >1 worker to mitigate blocking if any sync work remains.

## Acceptance
- Ingestion actions return immediately with a job ID; UI stays responsive.
- Jobs continue and finish even if the user navigates away.
- UI shows “running” indicators and a toast about background execution; refreshes on completion.
- No more page hangs during ingestion runs.
