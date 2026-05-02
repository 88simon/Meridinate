'use client';

import { useEffect, useRef } from 'react';

/**
 * setInterval that:
 *   - Skips ticks while the tab is hidden (Page Visibility API)
 *   - Optionally fires immediately when the tab becomes visible again
 *   - Cleans up on unmount
 *
 * Without this, every polling component in the app keeps firing requests
 * (and triggering React re-renders) while the user is in another tab or
 * another app entirely — that's the dominant source of background CPU/GPU
 * drain that bleeds into other processes (games, trading terminals, etc.).
 *
 * Usage:
 *   useVisibleInterval(() => { fetchSomething(); }, 5000);
 *   useVisibleInterval(() => { fetchSomething(); }, 5000, { fireOnVisible: true });
 */
export function useVisibleInterval(
  callback: () => void | Promise<void>,
  intervalMs: number,
  options: { fireOnVisible?: boolean; enabled?: boolean } = {}
): void {
  const { fireOnVisible = true, enabled = true } = options;
  // Keep a ref to the latest callback so consumers don't have to memoize it.
  const cbRef = useRef(callback);
  cbRef.current = callback;

  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;

    const tick = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      try { void cbRef.current(); } catch { /* swallow — caller's problem */ }
    };

    const interval = setInterval(tick, intervalMs);

    // Re-fire immediately on tab becoming visible so the user sees fresh data
    // instead of stale state captured from when they switched away.
    let visHandler: (() => void) | null = null;
    if (fireOnVisible && typeof document !== 'undefined') {
      visHandler = () => {
        if (!document.hidden) tick();
      };
      document.addEventListener('visibilitychange', visHandler);
    }

    return () => {
      clearInterval(interval);
      if (visHandler && typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', visHandler);
      }
    };
  }, [intervalMs, enabled, fireOnVisible]);
}
