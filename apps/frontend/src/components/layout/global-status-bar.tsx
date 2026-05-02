'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { API_BASE_URL } from '@/lib/api';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

// ============================================================================
// Types
// ============================================================================

interface TimerInfo {
  name: string;
  enabled: boolean;
  next_run_at: string | null;
  interval_minutes: number;
  is_running: boolean;
  paused: boolean;
}

interface JobCreditInfo {
  today: number;
  last_run: number;
  last_run_at: string | null;
  last_run_context: Record<string, unknown> | null;
}

interface StatusBarData {
  timers: Record<string, TimerInfo>;
  polling: {
    total_active: number;
    tiers: {
      fresh: number;
      maturing: number;
      aging: number;
      old: number;
      retired: number;
    };
    tier_intervals: Record<string, string>;
    verdicts: {
      wins: number;
      losses: number;
      pending: number;
    };
  };
  positions: {
    total_tracked: number;
    still_holding: number;
    exited: number;
    win_rate: number;
    avg_return: number | null;
  };
  credits: {
    used_today: number;
    position_daily_budget: number;
    by_job: {
      auto_scan: JobCreditInfo;
      mc_tracker: JobCreditInfo;
      position_check: JobCreditInfo;
    };
  };
  settings: {
    discovery_interval_minutes: number;
    mc_check_interval_minutes: number;
    position_check_interval_minutes: number;
  };
  followup: {
    running: boolean;
    active_tracking: number;
    total_tracked: number;
    total_completed: number;
    dex_calls_per_minute: number;
    rate_limited: boolean;
  };
  realtime: {
    running: boolean;
    total_detected: number;
    total_rejected: number;
    total_high_conviction: number;
    feed_size: number;
  };
  clobr?: {
    enabled: boolean;
    min_score: number;
    has_key: boolean;
    calls_today: number;
  };
}

// ============================================================================
// Helpers
// ============================================================================

function formatCountdown(nextRunAt: string | null): string {
  if (!nextRunAt) return '—';
  const diff = Math.max(0, Math.floor((new Date(nextRunAt).getTime() - Date.now()) / 1000));
  if (diff <= 0) return 'now';
  const m = Math.floor(diff / 60);
  const s = diff % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatCredits(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return n.toString();
}

function formatLastRun(isoStr: string | null): string {
  if (!isoStr) return 'never';
  const d = new Date(isoStr);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) {
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function isJobSuccess(job: JobCreditInfo): boolean | null {
  if (!job.last_run_at) return null; // never ran
  return !job.last_run_context?.error;
}

function LastRunIndicator({ job }: { job: JobCreditInfo }) {
  const success = isJobSuccess(job);
  if (success === null) {
    return (
      <span className='text-muted-foreground/50 text-[10px]'>No runs yet</span>
    );
  }
  return (
    <span className={cn('text-[10px]', success ? 'text-muted-foreground/60' : 'text-red-400')}>
      {success ? '✓' : '✗'} Last: {formatLastRun(job.last_run_at)} ({formatCredits(job.last_run)} cr)
    </span>
  );
}

// ============================================================================
// Component
// ============================================================================

export function GlobalStatusBar() {
  const [data, setData] = useState<StatusBarData | null>(null);
  const [countdowns, setCountdowns] = useState<{
    discovery: string;
    mc: string;
    position: string;
  }>({
    discovery: '—',
    mc: '—',
    position: '—'
  });
  const dataRef = useRef<StatusBarData | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/stats/status-bar`);
      if (!res.ok) return;
      const json: StatusBarData = await res.json();
      setData(json);
      dataRef.current = json;
    } catch {
      // Silently fail — status bar is non-critical
    }
  }, []);

  // Initial fetch + polling every 30s. Skip ticks while tab is hidden so the
  // status bar doesn't keep poking the backend while the user is in another app.
  useEffect(() => {
    fetchData();
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      fetchData();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Tick countdowns every second. The 1s tick was the single biggest source of
  // background CPU/GPU drain — fires constantly even when the user is in another
  // app. Skip when hidden; visibility handler below re-syncs on focus.
  useEffect(() => {
    const tick = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      const d = dataRef.current;
      if (!d) return;

      // Find discovery timer (tier0 job)
      const discoveryJob = Object.entries(d.timers).find(
        ([id]) => id.includes('tier0') || id.includes('discovery')
      )?.[1];

      // Find MC tracker timer
      const mcJob = Object.entries(d.timers).find(
        ([id]) => id.includes('mc_tracker') || id.includes('hot_refresh')
      )?.[1];

      // Find position check timer
      const positionJob = Object.entries(d.timers).find(
        ([id]) => id.includes('position_check') || id.includes('swab')
      )?.[1];

      const formatTimer = (job: TimerInfo | undefined) => {
        if (!job) return '—';
        if (job.paused) return 'PAUSED';
        if (job.is_running) return 'running';
        return formatCountdown(job.next_run_at);
      };

      setCountdowns({
        discovery: formatTimer(discoveryJob),
        mc: formatTimer(mcJob),
        position: formatTimer(positionJob),
      });
    };

    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, []);

  // Revalidate on tab focus or settings change
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') fetchData();
    };
    const handleRefresh = () => fetchData();

    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('meridinate:settings-changed', handleRefresh);
    window.addEventListener('meridinate:scan-complete', handleRefresh);
    window.addEventListener('meridinate:mc-refresh-complete', handleRefresh);
    window.addEventListener('meridinate:position-check-complete', handleRefresh);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('meridinate:settings-changed', handleRefresh);
      window.removeEventListener('meridinate:scan-complete', handleRefresh);
      window.removeEventListener('meridinate:mc-refresh-complete', handleRefresh);
      window.removeEventListener('meridinate:position-check-complete', handleRefresh);
    };
  }, [fetchData]);

  const [discoveryRunning, setDiscoveryRunning] = useState(false);
  const [scanProgress, setScanProgress] = useState<{
    running: boolean; current: number; total: number; credits_used: number; current_token: string | null;
  } | null>(null);

  const scanStartedAtRef = useRef<number>(0);
  const runDiscoveryNow = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (discoveryRunning) return;
    setDiscoveryRunning(true);
    scanStartedAtRef.current = Date.now();
    try {
      await fetch(`${API_BASE_URL}/api/ingest/run-scan`, { method: 'POST' });
      toast.success('Auto-scan triggered');
    } catch { toast.error('Failed to trigger discovery'); setDiscoveryRunning(false); }
  }, [discoveryRunning]);

  // Poll scan progress every 2s while a scan is running
  const scanDoneRef = useRef(false);
  // Reset done flag when a new scan starts
  useEffect(() => {
    if (discoveryRunning) scanDoneRef.current = false;
  }, [discoveryRunning]);

  const scanActive = (discoveryRunning || countdowns.discovery === 'running') && !scanDoneRef.current;
  useEffect(() => {
    if (!scanActive) {
      if (scanProgress) {
        setScanProgress(null);
        fetchData();
      }
      return;
    }

    const pollProgress = async () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      try {
        const res = await fetch(`${API_BASE_URL}/api/ingest/scan-progress`);
        if (res.ok) {
          const prog = await res.json();
          if (prog.running) {
            setScanProgress(prog);
          } else {
            const elapsed = Date.now() - scanStartedAtRef.current;
            if (discoveryRunning && elapsed < 5000) {
              return;
            }
            // Mark scan as done so timer's stale 'running' state doesn't re-trigger
            scanDoneRef.current = true;
            setScanProgress(null);
            setDiscoveryRunning(false);
            fetchData();
          }
        }
      } catch { /* silent */ }
    };

    pollProgress();
    const interval = setInterval(pollProgress, 2000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanActive]);

  const togglePipeline = useCallback(async (jobId: string) => {
    // Determine if currently paused from data
    const timers = dataRef.current?.timers || {};
    const timer = Object.entries(timers).find(([id]) => id === jobId)?.[1];
    const isPaused = timer?.paused;
    const action = isPaused ? 'resume' : 'pause';
    try {
      await fetch(`${API_BASE_URL}/api/wallet-shadow/pipeline/${jobId}/${action}`, { method: 'POST' });
      toast.success(`${timer?.name || jobId}: ${isPaused ? 'Resumed' : 'Paused'}`);
      fetchData();
    } catch { toast.error('Failed to toggle pipeline'); }
  }, [fetchData]);

  if (!data) return null;

  const { polling, positions, credits, settings, realtime, followup, clobr } = data;

  return (
    <TooltipProvider delayDuration={200}>
      <div className='flex items-center gap-3 text-xs'>
        {/* Next Token Discovery */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className='flex flex-col cursor-pointer' onClick={() => togglePipeline('ingest_tier0')}>
              <div className='flex items-center gap-1.5'>
                <span
                  className={cn(
                    'h-2 w-2 rounded-full',
                    countdowns.discovery === 'PAUSED'
                      ? 'bg-yellow-400'
                      : countdowns.discovery === 'running'
                      ? 'bg-blue-400 animate-pulse'
                      : 'bg-blue-500'
                  )}
                />
                <span className='text-muted-foreground'>Next Token Discovery</span>
                <span className={cn('font-mono font-medium', countdowns.discovery === 'PAUSED' && 'text-yellow-400')}>{countdowns.discovery}</span>
                {scanProgress?.running ? (
                  <span className='ml-0.5 flex items-center gap-1.5'>
                    <span className='flex h-1.5 w-16 overflow-hidden rounded-full bg-muted'>
                      <span
                        className='bg-blue-400 transition-all duration-300 rounded-full'
                        style={{ width: scanProgress.total > 0 ? `${Math.round((scanProgress.current / scanProgress.total) * 100)}%` : '0%' }}
                      />
                    </span>
                    <span className='text-[10px] font-mono text-blue-400'>
                      {scanProgress.current}/{scanProgress.total}
                    </span>
                    <span className='text-muted-foreground/60 text-[10px]'>({formatCredits(scanProgress.credits_used)} cr)</span>
                  </span>
                ) : (
                  <>
                    <button
                      onClick={runDiscoveryNow}
                      disabled={discoveryRunning || countdowns.discovery === 'running'}
                      title='Run discovery now'
                      className={cn(
                        'ml-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors',
                        discoveryRunning || countdowns.discovery === 'running'
                          ? 'bg-blue-500/20 text-blue-400 cursor-wait'
                          : 'bg-blue-500/10 text-blue-400 hover:bg-blue-500/30 hover:text-blue-300'
                      )}
                    >
                      {discoveryRunning ? 'Starting...' : 'Run Now'}
                    </button>
                    <span className='text-muted-foreground/60'>({formatCredits(credits.by_job.auto_scan.last_run)} cr)</span>
                  </>
                )}
              </div>
              <div className='ml-3.5'>
                <LastRunIndicator job={credits.by_job.auto_scan} />
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent side='bottom' className='max-w-xs'>
            <div className='space-y-1.5 text-xs'>
              <p>
                Scans DexScreener for newly migrated tokens matching your pipeline
                filters. Runs every {settings.discovery_interval_minutes} minutes.
              </p>
              <div className='border-t border-border pt-1.5 text-muted-foreground'>
                <span>Last run: {formatCredits(credits.by_job.auto_scan.last_run)} credits</span>
                <span className='mx-2'>·</span>
                <span>Today: {formatCredits(credits.by_job.auto_scan.today)} credits</span>
              </div>
            </div>
          </TooltipContent>
        </Tooltip>

        {/* Real-Time WebSocket indicator */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className='flex items-center gap-1.5 cursor-help'>
              <span className={cn(
                'h-2 w-2 rounded-full',
                realtime?.running ? 'bg-emerald-400 animate-pulse' : 'bg-muted-foreground/30'
              )} />
              <span className='text-muted-foreground text-[10px]'>
                {realtime?.running
                  ? `⚡ Live: ${realtime.total_detected} detected · ${realtime.total_high_conviction} high`
                  : '⚡ Real-Time: OFF'}
              </span>
            </div>
          </TooltipTrigger>
          <TooltipContent side='bottom' className='max-w-xs'>
            <div className='space-y-1 text-xs'>
              <p>
                {realtime?.running
                  ? 'Helius Enhanced WebSocket is streaming PumpFun token creation events in real-time. Toggle on the Token Pipeline page.'
                  : 'Real-time detection is paused. Start it from the Token Pipeline page to detect new tokens instantly.'}
              </p>
              {realtime?.running && (
                <div className='border-t border-border pt-1 text-muted-foreground'>
                  <span>{realtime.total_detected} detected</span>
                  <span className='mx-1'>·</span>
                  <span className='text-green-400'>{realtime.total_high_conviction} high conviction</span>
                  <span className='mx-1'>·</span>
                  <span className='text-red-400'>{realtime.total_rejected} rejected</span>
                </div>
              )}
            </div>
          </TooltipContent>
        </Tooltip>

        {/* Follow-up tracker + rate limit */}
        {followup?.active_tracking > 0 && (
          <>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className='flex items-center gap-1.5 cursor-help'>
                  <span className={cn(
                    'text-[10px]',
                    followup.rate_limited ? 'text-red-400 animate-pulse' :
                    followup.dex_calls_per_minute > 40 ? 'text-amber-400' :
                    'text-muted-foreground'
                  )}>
                    📈 {followup.active_tracking} tracking
                    {followup.rate_limited && ' ⚠️ RATE LIMITED'}
                    {!followup.rate_limited && followup.dex_calls_per_minute > 40 && ` (${followup.dex_calls_per_minute}/min)`}
                  </span>
                </div>
              </TooltipTrigger>
              <TooltipContent side='bottom' className='max-w-xs'>
                <div className='space-y-1 text-xs'>
                  <p className='font-medium'>Follow-Up Trajectory Tracker</p>
                  <p className='text-muted-foreground'>
                    Monitoring MC trajectory for {followup.active_tracking} tokens via DexScreener (free).
                    {followup.total_completed > 0 && ` ${followup.total_completed} completed.`}
                  </p>
                  <div className='border-t border-border pt-1 text-muted-foreground'>
                    <span>DexScreener calls: {followup.dex_calls_per_minute}/min</span>
                    <span className='mx-1'>·</span>
                    <span>Limit: 60/min</span>
                  </div>
                  {followup.rate_limited && (
                    <p className='text-red-400 font-medium'>
                      Rate limited! Reduce check interval or number of tracked tokens.
                    </p>
                  )}
                </div>
              </TooltipContent>
            </Tooltip>
          </>
        )}

        {/* CLOBr enrichment status */}
        {clobr?.enabled && clobr.has_key && (
          <Tooltip>
            <TooltipTrigger asChild>
              <div className='flex items-center gap-1 cursor-help'>
                <span className='h-1.5 w-1.5 rounded-full bg-emerald-400' />
                <span className='text-muted-foreground text-[10px]'>
                  CLOBr: ON · {clobr.calls_today} calls today
                </span>
              </div>
            </TooltipTrigger>
            <TooltipContent side='bottom' className='max-w-xs'>
              <div className='space-y-1 text-xs'>
                <p>
                  CLOBr enrichment fetches liquidity scores and support/resistance
                  data during MC tracking. Warning threshold: {clobr.min_score}. Calls today: {clobr.calls_today}.
                </p>
              </div>
            </TooltipContent>
          </Tooltip>
        )}

        <span className='text-muted-foreground/40'>|</span>

        {/* Next Token Price & Verdict Check */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className='flex flex-col cursor-pointer' onClick={() => togglePipeline('ingest_hot_refresh')}>
              <div className='flex items-center gap-1.5'>
                <span
                  className={cn(
                    'h-2 w-2 rounded-full',
                    countdowns.mc === 'PAUSED'
                      ? 'bg-yellow-400'
                      : countdowns.mc === 'running'
                      ? 'bg-green-400 animate-pulse'
                      : 'bg-green-500'
                  )}
                />
                <span className='text-muted-foreground'>
                  Next Token Price & Verdict Check
                </span>
                <span className={cn('font-mono font-medium', countdowns.mc === 'PAUSED' && 'text-yellow-400')}>{countdowns.mc}</span>
                <span className='text-muted-foreground/60'>({formatCredits(credits.by_job.mc_tracker.last_run)} cr)</span>
              </div>
              <div className='ml-3.5'>
                <LastRunIndicator job={credits.by_job.mc_tracker} />
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent side='bottom' className='max-w-xs'>
            <div className='space-y-1.5 text-xs'>
              <p>
                Polls current market cap for all active tokens via DexScreener
                (free). Computes win/loss verdicts and updates ATH estimates. Runs
                every {settings.mc_check_interval_minutes} minutes.
              </p>
              <div className='border-t border-border pt-1.5 text-muted-foreground'>
                <span>Last run: {formatCredits(credits.by_job.mc_tracker.last_run)} credits</span>
                <span className='mx-2'>·</span>
                <span>Today: {formatCredits(credits.by_job.mc_tracker.today)} credits</span>
              </div>
            </div>
          </TooltipContent>
        </Tooltip>

        <span className='text-muted-foreground/40'>|</span>

        {/* Next Wallet Position Check */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className='flex flex-col cursor-pointer' onClick={() => togglePipeline('swab_position_check')}>
              <div className='flex items-center gap-1.5'>
                <span
                  className={cn(
                    'h-2 w-2 rounded-full',
                    countdowns.position === 'PAUSED'
                      ? 'bg-yellow-400'
                      : countdowns.position === 'running'
                      ? 'bg-amber-400 animate-pulse'
                      : 'bg-amber-500'
                  )}
                />
                <span className='text-muted-foreground'>
                  Next Wallet Position Check
                </span>
                <span className={cn('font-mono font-medium', countdowns.position === 'PAUSED' && 'text-yellow-400')}>{countdowns.position}</span>
                <span className='text-muted-foreground/60'>({formatCredits(credits.by_job.position_check.last_run)} cr)</span>
              </div>
              <div className='ml-3.5'>
                <LastRunIndicator job={credits.by_job.position_check} />
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent side='bottom' className='max-w-xs'>
            <div className='space-y-2 text-xs'>
              <p>
                Checks if tracked wallets still hold their tokens via Helius
                balance lookup. Detects buys/sells and calculates PnL.
              </p>
              <p className='text-muted-foreground'>
                Runs every {settings.position_check_interval_minutes} minutes.
                ~10 Helius credits per position check.
                Last run: {formatCredits(credits.by_job.position_check.last_run)} credits · Today: {formatCredits(credits.by_job.position_check.today)} credits.
              </p>
              <div className='border-t border-border pt-1.5 space-y-1'>
                <div className='flex justify-between gap-4'>
                  <span>{positions.total_tracked} Tracked</span>
                  <span>{positions.still_holding} Holding</span>
                  <span>{positions.exited} Exited</span>
                </div>
                <div className='flex justify-between gap-4'>
                  <span className='text-green-400'>
                    {positions.win_rate}% Win Rate
                  </span>
                  <span className='text-blue-400'>
                    {positions.avg_return
                      ? `${positions.avg_return}x Avg Return`
                      : '— Avg Return'}
                  </span>
                </div>
              </div>
            </div>
          </TooltipContent>
        </Tooltip>

        <span className='text-muted-foreground/40'>|</span>

        {/* Tokens Being Polled */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className='flex items-center gap-1.5 cursor-help'>
              <span className='text-muted-foreground'>
                {polling.total_active} Tokens Being Polled
              </span>
            </div>
          </TooltipTrigger>
          <TooltipContent side='bottom' className='max-w-xs'>
            <div className='space-y-2 text-xs'>
              <p className='font-medium'>
                Token Price Polling — {polling.total_active} active
              </p>
              <div className='space-y-1'>
                <div className='flex justify-between gap-4'>
                  <span className='text-yellow-400'>
                    ⚡ {polling.tiers.fresh} Fresh ({'<'}6h)
                  </span>
                  <span className='text-muted-foreground'>
                    {polling.tier_intervals.fresh}
                  </span>
                </div>
                <div className='flex justify-between gap-4'>
                  <span className='text-blue-400'>
                    ◆ {polling.tiers.maturing} Maturing (6h-3d)
                  </span>
                  <span className='text-muted-foreground'>
                    {polling.tier_intervals.maturing}
                  </span>
                </div>
                <div className='flex justify-between gap-4'>
                  <span className='text-purple-400'>
                    ◇ {polling.tiers.aging} Aging (3-7d)
                  </span>
                  <span className='text-muted-foreground'>
                    {polling.tier_intervals.aging}
                  </span>
                </div>
                <div className='flex justify-between gap-4'>
                  <span className='text-muted-foreground'>
                    ○ {polling.tiers.old} Old (7d+)
                  </span>
                  <span className='text-muted-foreground'>
                    {polling.tier_intervals.old}
                  </span>
                </div>
              </div>
              <div className='border-t border-border pt-1.5 flex justify-between'>
                <span className='text-green-400'>
                  {polling.verdicts.wins} Verified Wins
                </span>
                <span className='text-red-400'>
                  {polling.verdicts.losses} Verified Losses
                </span>
              </div>
              <div className='flex justify-between text-muted-foreground'>
                <span>{polling.verdicts.pending} Pending</span>
                <span>{polling.tiers.retired} Retired (polling stopped)</span>
              </div>
            </div>
          </TooltipContent>
        </Tooltip>

        <span className='text-muted-foreground/40'>|</span>

        {/* Helius Credits Today */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className='flex items-center gap-1.5 cursor-help'>
              <span className='text-muted-foreground'>
                {formatCredits(credits.used_today)} /{' '}
                {formatCredits(credits.position_daily_budget)} Helius Credits
                Today
              </span>
            </div>
          </TooltipTrigger>
          <TooltipContent side='bottom' className='max-w-xs'>
            <div className='space-y-2 text-xs'>
              <p>
                Helius API credits consumed today vs your daily budget for position
                tracking. Adjust budget in Wallet Position Tracker settings.
                Resets at midnight UTC.
              </p>
              <div className='border-t border-border pt-1.5 space-y-1'>
                <div className='flex justify-between gap-4'>
                  <span>Token Discovery</span>
                  <span className='text-muted-foreground'>{formatCredits(credits.by_job.auto_scan.today)}</span>
                </div>
                <div className='flex justify-between gap-4'>
                  <span>Price & Verdict Check</span>
                  <span className='text-muted-foreground'>{formatCredits(credits.by_job.mc_tracker.today)}</span>
                </div>
                <div className='flex justify-between gap-4'>
                  <span>Wallet Position Check</span>
                  <span className='text-muted-foreground'>{formatCredits(credits.by_job.position_check.today)}</span>
                </div>
                <div className='flex justify-between gap-4 border-t border-border pt-1'>
                  <span>Other (manual ops)</span>
                  <span className='text-muted-foreground'>
                    {formatCredits(
                      credits.used_today -
                      credits.by_job.auto_scan.today -
                      credits.by_job.mc_tracker.today -
                      credits.by_job.position_check.today
                    )}
                  </span>
                </div>
              </div>
            </div>
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}
