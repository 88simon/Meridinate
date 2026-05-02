'use client';

import { useEffect } from 'react';

/**
 * Toggles `data-tab-hidden="true"` on <html> when the tab is hidden.
 *
 * Paired with a global CSS rule in globals.css that pauses all CSS
 * animations + transitions while that attribute is present. Result: when
 * the user switches to another app (game, trading terminal), Meridinate
 * stops driving the GPU on `animate-pulse` status badges, spinners,
 * skeleton shimmer, etc. — all of which were running indefinitely.
 *
 * No props, no children, no DOM output. Mount once near the layout root.
 */
export function TabVisibilityWatcher(): null {
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    const sync = () => {
      if (document.hidden) {
        root.dataset.tabHidden = 'true';
      } else {
        delete root.dataset.tabHidden;
      }
    };
    sync(); // initial state
    document.addEventListener('visibilitychange', sync);
    return () => {
      document.removeEventListener('visibilitychange', sync);
      delete root.dataset.tabHidden;
    };
  }, []);
  return null;
}
