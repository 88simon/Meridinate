'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  getCreditStatsToday,
  getCreditTransactions,
  getLatestToken,
  CreditUsageStats,
  CreditTransaction,
  LatestToken
} from '@/lib/api';

export interface StatusBarData {
  tokensScanned: number;
  creditsUsedToday: number;
  latestAnalysis: LatestToken | null;
  recentCredits: CreditTransaction[];
  isLoading: boolean;
  lastUpdated: Date | null;
}

interface UseStatusBarDataOptions {
  /** Poll interval in milliseconds (default: 30000 = 30s) */
  pollInterval?: number;
  /** Number of tokens scanned (passed from parent for efficiency) */
  tokensScanned?: number;
  /** Whether to enable polling (default: true) */
  enablePolling?: boolean;
}

const DEFAULT_POLL_INTERVAL = 30000; // 30 seconds

/**
 * Hook for fetching and maintaining live status bar data.
 *
 * Features:
 * - Fetches credit stats, recent transactions, and latest token
 * - Polls at configurable interval (default 30s)
 * - Revalidates on focus/visibility change
 * - Listens to analysis_complete WebSocket events to trigger refresh
 */
export function useStatusBarData(options: UseStatusBarDataOptions = {}) {
  const {
    pollInterval = DEFAULT_POLL_INTERVAL,
    tokensScanned = 0,
    enablePolling = true
  } = options;

  const [creditStats, setCreditStats] = useState<CreditUsageStats | null>(null);
  const [recentCredits, setRecentCredits] = useState<CreditTransaction[]>([]);
  const [latestToken, setLatestToken] = useState<LatestToken | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const isMounted = useRef(true);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch all status bar data
  const fetchData = useCallback(async () => {
    try {
      const [stats, transactions, latest] = await Promise.all([
        getCreditStatsToday(),
        getCreditTransactions(5),
        getLatestToken()
      ]);

      if (isMounted.current) {
        setCreditStats(stats);
        setRecentCredits(transactions.transactions);
        setLatestToken(latest);
        setLastUpdated(new Date());
        setIsLoading(false);
      }
    } catch (error) {
      console.error('[StatusBar] Failed to fetch data:', error);
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, []);

  // Manual refresh function
  const refresh = useCallback(() => {
    fetchData();
  }, [fetchData]);

  // Initial fetch
  useEffect(() => {
    isMounted.current = true;
    fetchData();

    return () => {
      isMounted.current = false;
    };
  }, [fetchData]);

  // Polling
  useEffect(() => {
    if (!enablePolling) return;

    pollTimerRef.current = setInterval(fetchData, pollInterval);

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [fetchData, pollInterval, enablePolling]);

  // Visibility change revalidation
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Refresh when tab becomes visible
        fetchData();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [fetchData]);

  // Focus revalidation
  useEffect(() => {
    const handleFocus = () => {
      fetchData();
    };

    window.addEventListener('focus', handleFocus);

    return () => {
      window.removeEventListener('focus', handleFocus);
    };
  }, [fetchData]);

  return {
    tokensScanned,
    creditsUsedToday: creditStats?.total_credits ?? 0,
    latestAnalysis: latestToken,
    recentCredits,
    isLoading,
    lastUpdated,
    refresh,
    creditStats // Expose full stats for advanced usage
  };
}
