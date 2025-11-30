# SWAB Check Progress & Background Safety – Implementation Guide

## Goal
Give users clear feedback when a SWAB “Check” is running: show per-row indicators while wallets are being processed and inform users they can leave the page while the check runs server-side.

## Current Context
- Frontend SWAB tab: `apps/frontend/src/components/swab/swab-tab.tsx` (Check button triggers `/api/swab/check`).
- Backend check endpoint: `/api/swab/check` in `apps/backend/src/meridinate/routers/swab.py` runs the position check synchronously and returns a summary.
- The request runs on the backend; the browser leaving the page does not cancel the backend work once the request is sent.

## Requirements
1) **Per-row progress indicator**: While a Check is running, show a visual marker (spinner/badge) next to rows being checked.
2) **Background-safe notice**: After starting a Check, notify the user that the check continues even if they leave the page.
3) **Modular UI**: Keep changes isolated to SWAB components; no impact on other pages.

## Suggested Implementation (Minimal Impact)
### Frontend
- In `swab-tab.tsx`:
  - Add state `checking` (boolean) and `checkingAddresses` (Set<string>).
  - On Check click:
    - Set `checking=true`.
    - Set `checkingAddresses` to the current positions’ wallet addresses (visible or all positions loaded).
    - Fire the fetch to `/api/swab/check` (existing endpoint).
    - Show a toast: “Position check is running in the background; you can leave this page.”
    - On completion (success or error), set `checking=false` and clear `checkingAddresses`; refresh data.
  - In the table rows, if `checkingAddresses` includes the row’s wallet, render a small spinner/badge (e.g., “Checking…” with a subtle animation).
  - Disable the Check button while `checking` is true (or show a loading state).

### Backend (optional enhancement)
- Keep `/api/swab/check` as-is (synchronous). The request already completes server-side even if the user navigates away after sending it.
- If desired, extend the response with `wallet_addresses_checked` (list) so the frontend can scope the indicator to actual wallets processed; otherwise, using the current positions list is acceptable for UX feedback.

## UX Notes
- The toast should appear immediately after the Check is triggered.
- The per-row indicator can be cleared when the request resolves; no need for streaming updates.
- Make the spinner/badge unobtrusive to avoid disrupting table layout.

## Acceptance
- Clicking Check shows immediate per-row “checking” indicators and a toast that it runs in the background.
- Navigation away during the check is safe; the backend completes the work.
- Indicators clear and data refresh after the check finishes.
