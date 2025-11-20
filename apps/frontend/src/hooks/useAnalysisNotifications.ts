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

// singleton websocket connection to prevent duplicate notifications across components
const MAX_RECONNECT_ATTEMPTS = 5;
const HIDDEN_TAB_CLOSE_DELAY = 30000; // close connection after 30s of tab being hidden
const RECONNECT_BASE_DELAY = 3000;
const MAX_RECONNECT_DELAY = 30000;

let globalWs: WebSocket | null = null;
let connectionCount = 0;
let reconnectAttempts = 0;
let lastErrorNotifiedAt = 0;
let hasShownFailureToast = false;
let messageCallbacks: Set<
  (data: AnalysisCompleteData | AnalysisStartData, event: string) => void
> = new Set();
let lastProcessedJobId: string | null = null;
let lastProcessedTime = 0;
let visibilityChangeTimer: NodeJS.Timeout | null = null;
let reconnectTimer: NodeJS.Timeout | null = null;

// global message handler - only processes each message once
const globalMessageHandler = (event: MessageEvent) => {
  try {
    const message: WebSocketMessage = JSON.parse(event.data);

    if (message.event === 'analysis_complete') {
      const data = message.data as AnalysisCompleteData;

      // deduplicate: skip if we just processed this job_id within last 2 seconds
      const now = Date.now();
      if (
        data.job_id === lastProcessedJobId &&
        now - lastProcessedTime < 2000
      ) {
        return;
      }
      lastProcessedJobId = data.job_id;
      lastProcessedTime = now;

      // show toast notification (only once, with ID to prevent duplicates)
      toast.success(`analysis complete: ${data.token_name}`, {
        description: `found ${data.wallets_found} early bidder wallets`,
        duration: 5000,
        id: `analysis-${data.job_id}`
      });

      // show desktop notification only if tab is not focused
      if (
        'Notification' in window &&
        Notification.permission === 'granted' &&
        document.hidden
      ) {
        const notification = new Notification('analysis complete', {
          body: `${data.token_name} (${data.acronym})\n${data.wallets_found} wallets found`,
          icon: '/favicon.ico',
          tag: 'analysis-complete',
          requireInteraction: false,
          silent: true
        });

        setTimeout(() => notification.close(), 3000);

        notification.onclick = () => {
          window.focus();
          notification.close();
        };
      }

      // notify all registered callbacks
      messageCallbacks.forEach((cb) => cb(data, 'analysis_complete'));
    } else if (message.event === 'analysis_start') {
      const data = message.data as AnalysisStartData;

      toast.info(`analysis started: ${data.token_name}`, {
        description: 'processing early bidders...',
        duration: 3000,
        id: `analysis-start-${data.job_id}`
      });

      messageCallbacks.forEach((cb) => cb(data, 'analysis_start'));
    }
  } catch (error) {
    if (shouldLog()) {
      console.error('[ws] message parse error:', error);
    }
  }
};

// close global websocket and clean up
const closeGlobalWebSocket = () => {
  if (globalWs) {
    if (shouldLog()) {
      console.log('[ws] closing global connection');
    }
    globalWs.close();
    globalWs = null;
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
};

// handle page visibility changes
const handleVisibilityChange = () => {
  if (document.hidden) {
    // tab became hidden - schedule connection close after delay
    if (shouldLog()) {
      console.log('[ws] tab hidden, scheduling connection close in 30s');
    }

    if (visibilityChangeTimer) {
      clearTimeout(visibilityChangeTimer);
    }

    visibilityChangeTimer = setTimeout(() => {
      if (document.hidden && globalWs) {
        if (shouldLog()) {
          console.log(
            '[ws] closing connection due to prolonged tab inactivity'
          );
        }
        closeGlobalWebSocket();
      }
    }, HIDDEN_TAB_CLOSE_DELAY);
  } else {
    // tab became visible - cancel close timer and reconnect if needed
    if (visibilityChangeTimer) {
      clearTimeout(visibilityChangeTimer);
      visibilityChangeTimer = null;
    }

    if (shouldLog()) {
      console.log('[ws] tab visible, resetting reconnect attempts');
    }

    // reset reconnect attempts when tab becomes active again
    reconnectAttempts = 0;
    hasShownFailureToast = false;

    // reconnect if we have active consumers but no connection
    if (
      connectionCount > 0 &&
      (!globalWs || globalWs.readyState === WebSocket.CLOSED)
    ) {
      if (shouldLog()) {
        console.log('[ws] reconnecting due to tab visibility');
      }
      // give the tab a moment to settle before reconnecting
      setTimeout(() => {
        if (!document.hidden) {
          connectWebSocket();
        }
      }, 500);
    }
  }
};

// establish websocket connection
const connectWebSocket = () => {
  // don't connect if tab is hidden
  if (document.hidden) {
    if (shouldLog()) {
      console.log('[ws] skipping connection - tab is hidden');
    }
    return;
  }

  // stop trying after too many failures
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    if (!hasShownFailureToast) {
      hasShownFailureToast = true;
      toast.error('real-time notifications disabled (websocket not available)');
    }
    return;
  }

  // reuse existing connection if available
  if (
    globalWs &&
    (globalWs.readyState === WebSocket.OPEN ||
      globalWs.readyState === WebSocket.CONNECTING)
  ) {
    if (shouldLog()) {
      console.log('[ws] reusing existing connection');
    }
    return;
  }

  // create new connection
  if (!globalWs || globalWs.readyState === WebSocket.CLOSED) {
    try {
      const ws = new WebSocket('ws://localhost:5003/ws');
      globalWs = ws;

      ws.onopen = () => {
        if (shouldLog()) {
          console.log('[ws] connected');
        }
        reconnectAttempts = 0;
        hasShownFailureToast = false;
      };

      ws.onmessage = globalMessageHandler;

      ws.onerror = (event) => {
        const now = Date.now();
        if (now - lastErrorNotifiedAt > 5000) {
          const errorMessage =
            (event as unknown as ErrorEvent)?.message || 'websocket error';
          if (errorMessage.toLowerCase().includes('insufficient resources')) {
            if (shouldLog()) {
              console.warn(
                '[ws] insufficient resources - too many concurrent connections'
              );
            }
          }
          lastErrorNotifiedAt = now;
        }
      };

      ws.onclose = () => {
        if (shouldLog()) {
          console.log('[ws] connection closed');
        }
        globalWs = null;

        // only attempt reconnect if:
        // 1. we have active consumers
        // 2. tab is visible
        // 3. haven't exceeded max attempts
        if (
          connectionCount > 0 &&
          !document.hidden &&
          reconnectAttempts < MAX_RECONNECT_ATTEMPTS
        ) {
          reconnectAttempts++;
          const delay = Math.min(
            RECONNECT_BASE_DELAY * reconnectAttempts,
            MAX_RECONNECT_DELAY
          );

          if (shouldLog()) {
            console.log(
              `[ws] reconnecting in ${delay}ms (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`
            );
          }

          reconnectTimer = setTimeout(() => {
            if (!document.hidden) {
              connectWebSocket();
            }
          }, delay);
        }
      };
    } catch (error) {
      if (shouldLog()) {
        console.error('[ws] connection error:', error);
      }
    }
  }
};

// global page visibility listener (only attached once)
let visibilityListenerAttached = false;
const attachVisibilityListener = () => {
  if (!visibilityListenerAttached && typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange);
    visibilityListenerAttached = true;
    if (shouldLog()) {
      console.log('[ws] page visibility listener attached');
    }
  }
};

export function useAnalysisNotifications(
  onComplete?: (data: AnalysisCompleteData) => void
) {
  const callbackRef = useRef<
    | ((data: AnalysisCompleteData | AnalysisStartData, event: string) => void)
    | null
  >(null);

  useEffect(() => {
    connectionCount++;

    if (shouldLog()) {
      console.log(`[ws] consumer registered, total: ${connectionCount}`);
    }

    // initialize debug mode from backend
    initDebugMode();

    // attach global visibility listener
    attachVisibilityListener();

    // create callback for this component instance
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

    // initial connection (only if tab is visible)
    connectWebSocket();

    // cleanup on unmount
    return () => {
      connectionCount--;

      if (shouldLog()) {
        console.log(
          `[ws] consumer unregistered, remaining: ${connectionCount}`
        );
      }

      // remove callback from the set
      if (callbackRef.current) {
        messageCallbacks.delete(callbackRef.current);
      }

      // only close global connection if no more components are using it
      if (connectionCount === 0) {
        if (shouldLog()) {
          console.log('[ws] last consumer removed, closing connection');
        }
        closeGlobalWebSocket();

        // clean up visibility timer
        if (visibilityChangeTimer) {
          clearTimeout(visibilityChangeTimer);
          visibilityChangeTimer = null;
        }
      }
    };
  }, [onComplete]);

  return globalWs;
}
