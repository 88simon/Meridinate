'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  getCreditStatsToday,
  getOperationLog,
  getLatestToken,
  CreditUsageStats,
  AggregatedOperation,
  LatestToken,
  OperationLogEntry,
  API_BASE_URL
} from '@/lib/api';

export interface StatusBarData {
  tokensScanned: number;
  tokensScannedToday: number;
  creditsUsedToday: number;
  latestAnalysis: LatestToken | null;
  recentOperations: AggregatedOperation[];
  isLoading: boolean;
  lastUpdated: Date | null;
}

interface UseStatusBarDataOptions {
  /** Poll interval in milliseconds (default: 30000 = 30s) */
  pollInterval?: number;
  /** Whether to enable polling (default: true) */
  enablePolling?: boolean;
}

const DEFAULT_POLL_INTERVAL = 30000; // 30 seconds

/**
 * Hook for fetching and maintaining live status bar data.
 *
 * Features:
 * - Fetches credit stats, aggregated operations, and latest token
 * - Polls at configurable interval (default 30s)
 * - Revalidates on focus/visibility change
 */
export function useStatusBarData(options: UseStatusBarDataOptions = {}) {
  const {
    pollInterval = DEFAULT_POLL_INTERVAL,
    enablePolling = true
  } = options;

  const [tokensScanned, setTokensScanned] = useState(0);
  const [tokensScannedToday, setTokensScannedToday] = useState(0);
  const [creditStats, setCreditStats] = useState<CreditUsageStats | null>(null);
  const [recentOperations, setRecentOperations] = useState<
    AggregatedOperation[]
  >([]);
  const [latestToken, setLatestToken] = useState<LatestToken | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const isMounted = useRef(true);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Convert persisted OperationLogEntry to AggregatedOperation format
  const toAggregatedOperation = (
    entry: OperationLogEntry
  ): AggregatedOperation => ({
    operation: entry.operation,
    label: entry.label,
    credits: entry.credits,
    timestamp: entry.timestamp,
    transaction_count: entry.call_count
  });

  // Fetch all status bar data
  const fetchData = useCallback(async () => {
    try {
      const [stats, operationLog, latest, statusBar] = await Promise.all([
        getCreditStatsToday(),
        getOperationLog(30), // Fetch last 30 persisted operations
        getLatestToken(),
        fetch(`${API_BASE_URL}/api/stats/status-bar`).then(r => r.ok ? r.json() : null).catch(() => null),
      ]);

      if (isMounted.current) {
        setCreditStats(stats);
        // Convert OperationLogEntry[] to AggregatedOperation[] for compatibility
        setRecentOperations(operationLog.operations.map(toAggregatedOperation));
        setLatestToken(latest);
        if (statusBar?.polling) {
          setTokensScanned(statusBar.polling.total_tokens ?? 0);
          setTokensScannedToday(statusBar.polling.tokens_scanned_today ?? 0);
        }
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

  // Debounced focus/visibility revalidation — both events fire together on tab switch,
  // so we debounce to a single fetch instead of triggering 6 API calls (3 × 2 events).
  const revalidateTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const debouncedRevalidate = () => {
      if (revalidateTimerRef.current) {
        clearTimeout(revalidateTimerRef.current);
      }
      revalidateTimerRef.current = setTimeout(() => {
        fetchData();
        revalidateTimerRef.current = null;
      }, 300);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        debouncedRevalidate();
      }
    };

    const handleFocus = () => {
      debouncedRevalidate();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleFocus);
    // Revalidate when background jobs complete (credits changed)
    window.addEventListener('meridinate:scan-complete', debouncedRevalidate);
    window.addEventListener('meridinate:mc-refresh-complete', debouncedRevalidate);
    window.addEventListener('meridinate:position-check-complete', debouncedRevalidate);
    window.addEventListener('meridinate:settings-changed', debouncedRevalidate);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
      window.removeEventListener('meridinate:scan-complete', debouncedRevalidate);
      window.removeEventListener('meridinate:mc-refresh-complete', debouncedRevalidate);
      window.removeEventListener('meridinate:position-check-complete', debouncedRevalidate);
      window.removeEventListener('meridinate:settings-changed', debouncedRevalidate);
      if (revalidateTimerRef.current) {
        clearTimeout(revalidateTimerRef.current);
      }
    };
  }, [fetchData]);

  return {
    tokensScanned,
    tokensScannedToday,
    creditsUsedToday: creditStats?.total_credits ?? 0,
    latestAnalysis: latestToken,
    recentOperations,
    isLoading,
    lastUpdated,
    refresh,
    creditStats // Expose full stats for advanced usage
  };
}
