'use client';

import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { initDebugMode, shouldLog } from '@/lib/debug';

interface AnalysisCompleteData {
  job_id: string;
  token_name: string;
  token_symbol: string;
  acronym: string;
  wallets_found: number;
  token_id: number;
}

interface AnalysisStartData {
  job_id: string;
  token_name: string;
  token_symbol: string;
}

interface WebSocketMessage {
  event: 'analysis_complete' | 'analysis_start';
  data: AnalysisCompleteData | AnalysisStartData;
}

// Singleton WebSocket connection to prevent duplicate notifications
let globalWs: WebSocket | null = null;
let connectionCount = 0;
let messageCallbacks: Set<
  (data: AnalysisCompleteData | AnalysisStartData, event: string) => void
> = new Set();
let lastProcessedJobId: string | null = null;
let lastProcessedTime = 0;

// Global message handler - only processes each message once
const globalMessageHandler = (event: MessageEvent) => {
  try {
    const message: WebSocketMessage = JSON.parse(event.data);
    if (shouldLog()) {
    }

    if (message.event === 'analysis_complete') {
      const data = message.data as AnalysisCompleteData;

      // Deduplicate: Skip if we just processed this job_id within last 2 seconds
      const now = Date.now();
      if (
        data.job_id === lastProcessedJobId &&
        now - lastProcessedTime < 2000
      ) {
        if (shouldLog()) {
        }
        return;
      }
      lastProcessedJobId = data.job_id;
      lastProcessedTime = now;

      // Show toast notification (only once, with ID to prevent duplicates)
      toast.success(`Analysis complete: ${data.token_name}`, {
        description: `Found ${data.wallets_found} early bidder wallets`,
        duration: 5000,
        id: `analysis-${data.job_id}` // Sonner will deduplicate based on this ID
      });

      // Show desktop notification ONLY if tab is not focused
      if (
        'Notification' in window &&
        Notification.permission === 'granted' &&
        document.hidden // Only show desktop notification if tab is hidden
      ) {
        const notification = new Notification('Analysis Complete ✓', {
          body: `${data.token_name} (${data.acronym})\n${data.wallets_found} wallets found`,
          icon: '/favicon.ico',
          tag: 'analysis-complete',
          requireInteraction: false,
          silent: true
        });

        // Auto-close after 3 seconds
        setTimeout(() => notification.close(), 3000);

        notification.onclick = () => {
          window.focus();
          notification.close();
        };
      }

      // Notify all registered callbacks
      messageCallbacks.forEach((cb) => cb(data, 'analysis_complete'));
    } else if (message.event === 'analysis_start') {
      const data = message.data as AnalysisStartData;

      // Show toast with unique ID to prevent duplicates
      toast.info(`Analysis started: ${data.token_name}`, {
        description: 'Processing early bidders...',
        duration: 3000,
        id: `analysis-start-${data.job_id}` // Deduplicate start notifications too
      });

      // Notify all registered callbacks
      messageCallbacks.forEach((cb) => cb(data, 'analysis_start'));
    }
  } catch (error) {
    if (shouldLog()) {
    }
  }
};

export function useAnalysisNotifications(
  onComplete?: (data: AnalysisCompleteData) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const callbackRef = useRef<
    | ((data: AnalysisCompleteData | AnalysisStartData, event: string) => void)
    | null
  >(null);

  useEffect(() => {
    let isSubscribed = true;
    connectionCount++;

    // Initialize debug mode from backend
    initDebugMode();

    // Create callback for this component instance
    const callback = (
      data: AnalysisCompleteData | AnalysisStartData,
      event: string
    ) => {
      if (event === 'analysis_complete' && onComplete) {
        onComplete(data as AnalysisCompleteData);
      }
    };

    callbackRef.current = callback;
    messageCallbacks.add(callback);

    const connect = () => {
      if (!isSubscribed) return;

      // Reuse existing global connection if available
      if (globalWs && globalWs.readyState === WebSocket.OPEN) {
        wsRef.current = globalWs;
        if (shouldLog()) {
        }
        return;
      }

      // Create new connection only if no global connection exists
      if (!globalWs || globalWs.readyState === WebSocket.CLOSED) {
        const ws = new WebSocket('ws://localhost:5003/ws');
        globalWs = ws;
        wsRef.current = ws;

        ws.onopen = () => {
          if (shouldLog()) {
          }
        };

        // Use the global message handler (only attached once)
        ws.onmessage = globalMessageHandler;

        ws.onerror = () => {
          if (shouldLog()) {
          }
        };

        ws.onclose = () => {
          if (shouldLog()) {
          }
          globalWs = null;
          wsRef.current = null;

          // Attempt to reconnect after 3 seconds
          if (connectionCount > 0) {
            if (shouldLog()) {
            }
            reconnectTimeoutRef.current = setTimeout(connect, 3000);
          }
        };
      }
    };

    // Initial connection
    connect();

    // Cleanup on unmount
    return () => {
      isSubscribed = false;
      connectionCount--;

      if (shouldLog()) {
      }

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }

      // Remove callback from the set
      if (callbackRef.current) {
        messageCallbacks.delete(callbackRef.current);
      }

      // Only close global connection if no more components are using it
      if (connectionCount === 0 && globalWs) {
        globalWs.close();
        globalWs = null;
      }

      wsRef.current = null;
    };
  }, [onComplete]);

  return wsRef.current;
}
