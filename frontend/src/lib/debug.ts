/**
 * Unified Debug Mode - Frontend Component
 *
 * This module syncs with the backend debug killswitch.
 * The backend controls debug mode via debug_config.py at the root level.
 *
 * Usage:
 *   import { shouldLog } from '@/lib/debug';
 *   if (shouldLog()) console.log('Debug info');
 */

import { API_BASE_URL } from './api';

let DEBUG_MODE = false;
let initialized = false;

/**
 * Initialize debug mode by fetching from backend
 */
export async function initDebugMode(): Promise<void> {
  if (initialized) return;

  try {
    const response = await fetch(`${API_BASE_URL}/api/debug-mode`);
    if (response.ok) {
      const data = await response.json();
      DEBUG_MODE = data.debug_mode;
      initialized = true;
    } else {
      // Default to production mode if backend unreachable
      DEBUG_MODE = false;
      initialized = true;
    }
  } catch (error) {
    // Default to production mode on error
    DEBUG_MODE = false;
    initialized = true;
  }
}

/**
 * Check if logging should be enabled
 * Returns true in development OR if backend debug mode is enabled
 */
export function shouldLog(): boolean {
  // Always log in development environment
  if (process.env.NODE_ENV === 'development') {
    return true;
  }

  // In production, respect backend killswitch
  return DEBUG_MODE;
}

/**
 * Get current debug mode status (for display purposes)
 */
export function isDebugMode(): boolean {
  return DEBUG_MODE;
}
