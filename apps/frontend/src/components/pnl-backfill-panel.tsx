'use client';

import { useEffect, useState, useCallback } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface BackfillState {
  running: boolean;
  status: string;
  wallets_total: number;
  wallets_processed: number;
  wallets_with_data: number;
  positions_updated: number;
  credits_used: number;
  progress_pct: number;
  estimated_remaining_seconds: number | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  min_token_count: number;
}

function formatCredits(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return n.toString();
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '—';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export function PnLBackfillPanel() {
  const [state, setState] = useState<BackfillState | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/wallets/pnl-backfill/status`);
      if (res.ok) setState(await res.json());
    } catch { /* silent */ }
  }, []);

  // Poll every 3 seconds when running. Skip ticks while tab hidden — backfill
  // continues server-side; we only need fresh data when the user is looking.
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      fetchStatus();
    }, state?.running ? 3000 : 30000);
    return () => clearInterval(interval);
  }, [fetchStatus, state?.running]);

  const startBackfill = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/wallets/pnl-backfill/start?min_tokens=5`, { method: 'POST' });
      if (res.ok) {
        toast.success('PnL & timestamp backfill started for wallets with 5+ tokens');
        fetchStatus();
      }
    } catch {
      toast.error('Failed to start backfill');
    } finally {
      setLoading(false);
    }
  };

  const stopBackfill = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/wallets/pnl-backfill/stop`, { method: 'POST' });
      if (res.ok) {
        toast.success('PnL backfill stopped');
        fetchStatus();
      }
    } catch {
      toast.error('Failed to stop backfill');
    } finally {
      setLoading(false);
    }
  };

  if (!state) return null;

  const isRunning = state.running;
  const isCompleted = state.status === 'completed';
  const hasRun = state.wallets_total > 0;

  return (
    <TooltipProvider delayDuration={200}>
      <div className={cn(
        'rounded-lg border p-3',
        isRunning && 'border-blue-500/30'
      )}>
        <div className='flex items-center justify-between mb-2'>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className='text-xs font-medium cursor-help border-b border-dotted border-muted-foreground/30'>
                PnL & Timestamp Backfill
              </span>
            </TooltipTrigger>
            <TooltipContent className='max-w-xs'>
              <p className='text-xs'>
                Computes real profit/loss and captures accurate buy/sell timestamps for hold time tracking.
                Reads actual swap transactions from the blockchain via Helius API.
                Only processes wallets appearing in 5+ of our analyzed tokens.
                Cost: ~21 credits per wallet-token pair.
              </p>
            </TooltipContent>
          </Tooltip>
          <div className='flex items-center gap-2'>
            {isRunning && (
              <span className='text-[10px] text-muted-foreground'>
                ~{formatDuration(state.estimated_remaining_seconds)} remaining
              </span>
            )}
            <Button
              variant={isRunning ? 'destructive' : 'outline'}
              size='sm'
              className='h-6 text-[10px]'
              onClick={isRunning ? stopBackfill : startBackfill}
              disabled={loading}
            >
              {loading ? '...' : isRunning ? 'Stop' : 'Start Backfill'}
            </Button>
          </div>
        </div>

        {/* Progress bar */}
        {hasRun && (
          <>
            <div className='h-2 w-full rounded-full bg-muted overflow-hidden mb-1.5'>
              <div
                className={cn(
                  'h-full rounded-full transition-all duration-500',
                  isCompleted ? 'bg-green-500' :
                  isRunning ? 'bg-blue-500' :
                  state.status === 'error' ? 'bg-red-500' :
                  'bg-muted-foreground/30'
                )}
                style={{ width: `${state.progress_pct}%` }}
              />
            </div>

            <div className='flex items-center justify-between text-[10px] text-muted-foreground'>
              <span>
                {state.wallets_processed}/{state.wallets_total} wallets
                ({state.progress_pct}%)
              </span>
              <span>
                {state.positions_updated} positions
                {' · '}
                {state.wallets_with_data} with data
                {' · '}
                {formatCredits(state.credits_used)} credits
              </span>
            </div>

            {state.status === 'completed' && (
              <div className='mt-1 text-[10px] text-green-400'>
                ✓ Completed — {state.wallets_with_data} wallets have real PnL + accurate timestamps
              </div>
            )}
            {state.status === 'error' && (
              <div className='mt-1 text-[10px] text-red-400'>
                ✗ Error: {state.error}
              </div>
            )}
            {state.status === 'stopped' && (
              <div className='mt-1 text-[10px] text-yellow-400'>
                Stopped — {state.wallets_processed}/{state.wallets_total} processed. Click Start to resume.
              </div>
            )}
          </>
        )}

        {!hasRun && !isRunning && (
          <div className='text-[10px] text-muted-foreground'>
            Click Start to compute real PnL + timestamps for {state.min_token_count}+ token wallets (~21 credits/pair)
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
