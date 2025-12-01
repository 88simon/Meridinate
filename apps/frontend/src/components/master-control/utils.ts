import { fetchWithTimeout } from '@/lib/api';

// Settings modal timeout - longer to handle slow responses during ingestion
export const SETTINGS_FETCH_TIMEOUT = 8000;
export const SETTINGS_MAX_RETRIES = 2;
export const SETTINGS_RETRY_DELAY = 1000;

/**
 * Fetch with retry logic for settings endpoints.
 * Retries on timeout/failure with exponential backoff.
 */
export async function fetchWithRetry(
  url: string,
  options: RequestInit = {},
  maxRetries: number = SETTINGS_MAX_RETRIES
): Promise<Response> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetchWithTimeout(
        url,
        options,
        SETTINGS_FETCH_TIMEOUT
      );
      if (response.ok) {
        return response;
      }
      // Non-OK response, try again
      lastError = new Error(`HTTP ${response.status}`);
    } catch (err) {
      lastError = err instanceof Error ? err : new Error('Unknown error');
    }

    // Wait before retrying (exponential backoff)
    if (attempt < maxRetries) {
      await new Promise((resolve) =>
        setTimeout(resolve, SETTINGS_RETRY_DELAY * Math.pow(2, attempt))
      );
    }
  }

  throw lastError || new Error('Failed after retries');
}

/**
 * Format timestamp for display
 */
export function formatTimestamp(ts: string | null): string {
  if (!ts) return 'Never';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

// Local storage key for banner preferences
export const BANNER_PREFS_KEY = 'meridinate_banner_prefs';

export interface BannerPrefs {
  showIngestBanner: boolean;
}

export const defaultBannerPrefs: BannerPrefs = {
  showIngestBanner: true
};

export function loadBannerPrefs(): BannerPrefs {
  if (typeof window === 'undefined') return defaultBannerPrefs;
  try {
    const stored = localStorage.getItem(BANNER_PREFS_KEY);
    return stored ? JSON.parse(stored) : defaultBannerPrefs;
  } catch {
    return defaultBannerPrefs;
  }
}

export function saveBannerPrefs(prefs: BannerPrefs): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(BANNER_PREFS_KEY, JSON.stringify(prefs));
}
