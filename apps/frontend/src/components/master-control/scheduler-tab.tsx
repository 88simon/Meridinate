'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import {
  Loader2,
  RefreshCw,
  AlertTriangle,
  Activity,
  Play,
  Clock,
  Zap
} from 'lucide-react';
import { toast } from 'sonner';
import {
  updateSwabSettings,
  triggerSwabCheck,
  triggerSwabPnlUpdate,
  reconcileAllPositions,
  updateIngestSettings,
  SwabSettings,
  SwabStats,
  IngestSettings,
  API_BASE_URL
} from '@/lib/api';
import { NumericStepper } from './NumericStepper';
import { InfoTooltip } from './InfoTooltip';
import { formatTimestamp } from './utils';

// Session storage keys for caching
const CACHE_KEY_INGEST = 'scheduler_ingest_settings';
const CACHE_KEY_SWAB = 'scheduler_swab_settings';
const CACHE_KEY_STATS = 'scheduler_swab_stats';
const CACHE_KEY_STATUS = 'scheduler_status';

// Shorter timeouts for faster feedback (4s timeout, 1 retry)
const FAST_FETCH_TIMEOUT = 4000;
const FAST_FETCH_RETRIES = 1;

interface SchedulerTabProps {
  bypassLimits?: boolean;
}

// Section loading skeleton
function SectionSkeleton({
  title,
  icon
}: {
  title: string;
  icon: React.ReactNode;
}) {
  return (
    <div className='animate-pulse'>
      <div className='mb-4 flex items-center gap-2 border-b pb-2'>
        {icon}
        <h3 className='text-sm font-semibold'>{title}</h3>
      </div>
      <div className='space-y-4'>
        <div className='bg-muted h-4 w-48 rounded' />
        <div className='grid grid-cols-2 gap-4'>
          <div className='bg-muted h-16 rounded-lg' />
          <div className='bg-muted h-16 rounded-lg' />
          <div className='bg-muted h-16 rounded-lg' />
          <div className='bg-muted h-16 rounded-lg' />
        </div>
      </div>
    </div>
  );
}

// Fast fetch with shorter timeout
async function fastFetch(url: string): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FAST_FETCH_TIMEOUT);

  let lastError: Error | null = null;
  for (let attempt = 0; attempt <= FAST_FETCH_RETRIES; attempt++) {
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        cache: 'no-store'
      });
      clearTimeout(timeoutId);
      return response;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt < FAST_FETCH_RETRIES) {
        await new Promise((r) => setTimeout(r, 500)); // Short backoff
      }
    }
  }
  clearTimeout(timeoutId);
  throw lastError;
}

// Cache helpers
function getFromCache<T>(key: string): T | null {
  try {
    const cached = sessionStorage.getItem(key);
    return cached ? JSON.parse(cached) : null;
  } catch {
    return null;
  }
}

function setInCache<T>(key: string, value: T): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore storage errors
  }
}

export function SchedulerTab({ bypassLimits = false }: SchedulerTabProps) {
  // Ingest settings state (for Discovery and MC Refresh)
  const [ingestSettings, setIngestSettings] = useState<IngestSettings | null>(
    () => getFromCache<IngestSettings>(CACHE_KEY_INGEST)
  );
  const [ingestLoading, setIngestLoading] = useState(!ingestSettings);
  const [ingestError, setIngestError] = useState<string | null>(null);

  // SWAB settings state (for Position Check)
  const [swabSettings, setSwabSettings] = useState<SwabSettings | null>(() =>
    getFromCache<SwabSettings>(CACHE_KEY_SWAB)
  );
  const [swabStats, setSwabStats] = useState<SwabStats | null>(() =>
    getFromCache<SwabStats>(CACHE_KEY_STATS)
  );
  const [schedulerStatus, setSchedulerStatus] = useState<{
    last_check_at: string | null;
    next_check_at: string | null;
  } | null>(() => getFromCache(CACHE_KEY_STATUS));
  const [swabLoading, setSwabLoading] = useState(!swabSettings);
  const [swabError, setSwabError] = useState<string | null>(null);

  // Manual action states
  const [runningCheck, setRunningCheck] = useState(false);
  const [runningPnl, setRunningPnl] = useState(false);
  const [runningReconcile, setRunningReconcile] = useState(false);
  const [reconcileMaxSigs, setReconcileMaxSigs] = useState(50);
  const [reconcileMaxPos, setReconcileMaxPos] = useState(50);

  // Track if component is mounted to avoid state updates after unmount
  const mountedRef = useRef(true);

  // Load Discovery section data
  const loadIngestData = useCallback(async (showLoader = true) => {
    if (showLoader) setIngestLoading(true);
    setIngestError(null);
    try {
      const response = await fastFetch(`${API_BASE_URL}/api/ingest/settings`);
      const data = await response.json();
      if (mountedRef.current) {
        setIngestSettings(data);
        setInCache(CACHE_KEY_INGEST, data);
      }
    } catch (err) {
      if (mountedRef.current) {
        const message =
          err instanceof Error && err.name === 'AbortError'
            ? 'Backend busy. Try again later.'
            : 'Failed to load discovery settings';
        setIngestError(message);
      }
    } finally {
      if (mountedRef.current) setIngestLoading(false);
    }
  }, []);

  // Load Health Check section data (SWAB settings, stats, scheduler status)
  const loadSwabData = useCallback(async (showLoader = true) => {
    if (showLoader) setSwabLoading(true);
    setSwabError(null);
    try {
      // Fetch all three in parallel, handle individual failures gracefully
      const [settingsRes, statsRes, statusRes] = await Promise.allSettled([
        fastFetch(`${API_BASE_URL}/api/swab/settings`),
        fastFetch(`${API_BASE_URL}/api/swab/stats`),
        fastFetch(`${API_BASE_URL}/api/swab/scheduler/status`)
      ]);

      if (mountedRef.current) {
        // Process settings
        if (settingsRes.status === 'fulfilled') {
          const settings = await settingsRes.value.json();
          setSwabSettings(settings);
          setInCache(CACHE_KEY_SWAB, settings);
        }
        // Process stats
        if (statsRes.status === 'fulfilled') {
          const stats = await statsRes.value.json();
          setSwabStats(stats);
          setInCache(CACHE_KEY_STATS, stats);
        }
        // Process scheduler status
        if (statusRes.status === 'fulfilled') {
          const status = await statusRes.value.json();
          setSchedulerStatus(status);
          setInCache(CACHE_KEY_STATUS, status);
        }

        // Only show error if all three failed
        const allFailed =
          settingsRes.status === 'rejected' &&
          statsRes.status === 'rejected' &&
          statusRes.status === 'rejected';
        if (allFailed) {
          setSwabError('Failed to load health check settings');
        }
      }
    } catch {
      if (mountedRef.current) {
        setSwabError('Failed to load health check settings');
      }
    } finally {
      if (mountedRef.current) setSwabLoading(false);
    }
  }, []);

  // Track initial cache state (only on mount)
  const initialCacheRef = useRef({
    hadIngest: getFromCache<IngestSettings>(CACHE_KEY_INGEST) !== null,
    hadSwab: getFromCache<SwabSettings>(CACHE_KEY_SWAB) !== null
  });

  // Initial load - parallel, independent
  useEffect(() => {
    mountedRef.current = true;

    // If we have cached data, show it and refresh in background (without loader)
    loadIngestData(!initialCacheRef.current.hadIngest);
    loadSwabData(!initialCacheRef.current.hadSwab);

    return () => {
      mountedRef.current = false;
    };
  }, [loadIngestData, loadSwabData]);

  const updateIngestSetting = async (updates: Partial<IngestSettings>) => {
    if (!ingestSettings) return;
    const newSettings = { ...ingestSettings, ...updates };
    setIngestSettings(newSettings);
    setInCache(CACHE_KEY_INGEST, newSettings);
    try {
      await updateIngestSettings(updates);
      toast.success('Setting saved');
    } catch {
      toast.error('Failed to save setting');
    }
  };

  const updateSwabSetting = async (updates: {
    auto_check_enabled?: boolean;
    check_interval_minutes?: number;
    daily_credit_budget?: number;
    stale_threshold_minutes?: number;
    min_token_count?: number;
  }) => {
    if (!swabSettings) return;
    const newSettings = { ...swabSettings, ...updates } as SwabSettings;
    setSwabSettings(newSettings);
    setInCache(CACHE_KEY_SWAB, newSettings);
    try {
      await updateSwabSettings(updates);
      toast.success('Setting saved');
    } catch {
      toast.error('Failed to save setting');
    }
  };

  const runCheck = async () => {
    setRunningCheck(true);
    try {
      const result = await triggerSwabCheck();
      toast.success(
        `Checked ${result.positions_checked} positions, ${result.sold} sells detected`
      );
      loadSwabData(false);
    } catch {
      toast.error('Check failed');
    } finally {
      setRunningCheck(false);
    }
  };

  const runPnlUpdate = async () => {
    setRunningPnl(true);
    try {
      const result = await triggerSwabPnlUpdate();
      toast.success(`Updated PnL for ${result.positions_updated} positions`);
    } catch {
      toast.error('PnL update failed');
    } finally {
      setRunningPnl(false);
    }
  };

  const runReconcile = async () => {
    setRunningReconcile(true);
    try {
      const result = await reconcileAllPositions({
        max_signatures: reconcileMaxSigs,
        max_positions: reconcileMaxPos
      });
      toast.success(
        `Reconciled ${result.positions_reconciled}/${result.positions_found} positions (${result.credits_used} credits)`
      );
      loadSwabData(false);
    } catch {
      toast.error('Reconciliation failed');
    } finally {
      setRunningReconcile(false);
    }
  };

  return (
    <div className='space-y-6'>
      {/* ================================================================== */}
      {/* SECTION 1: TOKEN DISCOVERY SCHEDULER */}
      {/* ================================================================== */}
      <div>
        {ingestLoading && !ingestSettings ? (
          <SectionSkeleton
            title='Token Discovery Scheduler'
            icon={<Zap className='h-4 w-4 text-yellow-500' />}
          />
        ) : ingestError && !ingestSettings ? (
          <div className='flex flex-col items-center justify-center gap-3 py-8'>
            <AlertTriangle className='h-6 w-6 text-yellow-500' />
            <p className='text-muted-foreground text-sm'>{ingestError}</p>
            <Button
              variant='outline'
              size='sm'
              onClick={() => loadIngestData()}
            >
              <RefreshCw className='mr-2 h-3 w-3' />
              Retry Discovery Settings
            </Button>
          </div>
        ) : (
          <>
            <div className='mb-4 flex items-center gap-2 border-b pb-2'>
              <Zap className='h-4 w-4 text-yellow-500' />
              <h3 className='text-sm font-semibold'>
                Token Discovery Scheduler
              </h3>
              <InfoTooltip>
                Periodically fetches new tokens from DexScreener that pass your
                threshold filters. Free API calls.
              </InfoTooltip>
              {ingestLoading && (
                <Loader2 className='text-muted-foreground ml-auto h-3 w-3 animate-spin' />
              )}
            </div>

            {ingestSettings && (
              <>
                {/* Discovery Thresholds */}
                <div className='mb-4'>
                  <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
                    Discovery Thresholds
                    <InfoTooltip>
                      Minimum values for tokens to pass DexScreener discovery
                    </InfoTooltip>
                  </h4>
                  <div className='grid grid-cols-2 gap-4'>
                    <NumericStepper
                      label='Min Market Cap ($)'
                      value={ingestSettings.mc_min}
                      onChange={(v) => updateIngestSetting({ mc_min: v })}
                      min={0}
                      step={5000}
                      tooltip='Minimum market cap to pass discovery'
                      bypassLimits={bypassLimits}
                    />
                    <NumericStepper
                      label='Min Volume ($)'
                      value={ingestSettings.volume_min}
                      onChange={(v) => updateIngestSetting({ volume_min: v })}
                      min={0}
                      step={1000}
                      tooltip='Minimum 24h volume'
                      bypassLimits={bypassLimits}
                    />
                    <NumericStepper
                      label='Min Liquidity ($)'
                      value={ingestSettings.liquidity_min}
                      onChange={(v) =>
                        updateIngestSetting({ liquidity_min: v })
                      }
                      min={0}
                      step={1000}
                      tooltip='Minimum liquidity'
                      bypassLimits={bypassLimits}
                    />
                    <NumericStepper
                      label='Max Age (hours)'
                      value={ingestSettings.age_max_hours}
                      onChange={(v) =>
                        updateIngestSetting({ age_max_hours: v })
                      }
                      min={1}
                      step={6}
                      tooltip='Maximum token age for discovery'
                      bypassLimits={bypassLimits}
                    />
                  </div>
                </div>

                {/* Discovery Scheduler Settings */}
                <div className='mb-4 border-t pt-4'>
                  <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
                    Scheduler Settings
                    <InfoTooltip>Control how often discovery runs</InfoTooltip>
                  </h4>
                  <div className='grid grid-cols-2 gap-4'>
                    <div className='space-y-2'>
                      <Label className='text-xs'>Discovery Interval</Label>
                      <Select
                        value={String(
                          ingestSettings.discovery_interval_minutes ??
                            ingestSettings.tier0_interval_minutes ??
                            60
                        )}
                        onValueChange={(v) =>
                          updateIngestSetting({
                            discovery_interval_minutes: parseInt(v, 10)
                          })
                        }
                      >
                        <SelectTrigger className='w-full'>
                          <SelectValue placeholder='Select interval' />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value='15'>Every 15 minutes</SelectItem>
                          <SelectItem value='30'>Every 30 minutes</SelectItem>
                          <SelectItem value='60'>Every 60 minutes</SelectItem>
                          <SelectItem value='120'>Every 2 hours</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className='text-muted-foreground text-xs'>
                        How often Discovery (DexScreener) runs
                      </p>
                    </div>
                    <NumericStepper
                      label='Max Tokens per Run'
                      value={
                        ingestSettings.discovery_max_per_run ??
                        ingestSettings.tier0_max_tokens_per_run ??
                        50
                      }
                      onChange={(v) =>
                        updateIngestSetting({ discovery_max_per_run: v })
                      }
                      min={1}
                      step={10}
                      tooltip='Max tokens per discovery run'
                      bypassLimits={bypassLimits}
                    />
                  </div>
                </div>

                {/* Auto-Promote Settings */}
                <div className='border-t pt-4'>
                  <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
                    Auto-Promote
                    <InfoTooltip>
                      Automatically promote discovered tokens to full analysis
                    </InfoTooltip>
                  </h4>
                  <div className='grid grid-cols-2 gap-4'>
                    <div className='flex items-center justify-between rounded-lg border p-3'>
                      <div>
                        <Label className='text-sm'>Enable Auto-Promote</Label>
                        <p className='text-muted-foreground text-xs'>
                          Auto-analyze top discovered tokens
                        </p>
                      </div>
                      <Switch
                        checked={ingestSettings.auto_promote_enabled ?? false}
                        onCheckedChange={(v) =>
                          updateIngestSetting({ auto_promote_enabled: v })
                        }
                      />
                    </div>
                    <NumericStepper
                      label='Auto-Promote Max'
                      value={ingestSettings.auto_promote_max_per_run ?? 5}
                      onChange={(v) =>
                        updateIngestSetting({ auto_promote_max_per_run: v })
                      }
                      min={1}
                      step={1}
                      tooltip='Max tokens to auto-promote per run'
                      bypassLimits={bypassLimits}
                    />
                  </div>
                  {ingestSettings.last_discovery_run_at && (
                    <p className='text-muted-foreground mt-2 text-xs'>
                      Last discovery:{' '}
                      {formatTimestamp(
                        ingestSettings.last_discovery_run_at ??
                          ingestSettings.last_tier0_run_at ??
                          null
                      )}
                    </p>
                  )}
                </div>
              </>
            )}
          </>
        )}
      </div>

      {/* ================================================================== */}
      {/* SECTION 2: TOKEN HEALTH CHECK SCHEDULER */}
      {/* ================================================================== */}
      <div className='border-t pt-6'>
        {swabLoading && !swabSettings ? (
          <SectionSkeleton
            title='Token Health Check Scheduler'
            icon={<Clock className='h-4 w-4 text-blue-500' />}
          />
        ) : swabError && !swabSettings ? (
          <div className='flex flex-col items-center justify-center gap-3 py-8'>
            <AlertTriangle className='h-6 w-6 text-yellow-500' />
            <p className='text-muted-foreground text-sm'>{swabError}</p>
            <Button variant='outline' size='sm' onClick={() => loadSwabData()}>
              <RefreshCw className='mr-2 h-3 w-3' />
              Retry Health Check Settings
            </Button>
          </div>
        ) : (
          <>
            <div className='mb-4 flex items-center gap-2 border-b pb-2'>
              <Clock className='h-4 w-4 text-blue-500' />
              <h3 className='text-sm font-semibold'>
                Token Health Check Scheduler
              </h3>
              <InfoTooltip>
                Keeps token data fresh via MC refresh and SWAB position checks.
                When both are enabled, DexScreener snapshots are shared to avoid
                duplicate fetches on overlapping tokens.
              </InfoTooltip>
              {swabLoading && (
                <Loader2 className='text-muted-foreground ml-auto h-3 w-3 animate-spin' />
              )}
            </div>

            {/* MC Refresh Settings */}
            {ingestSettings && (
              <div className='mb-4'>
                <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
                  MC Refresh
                  <InfoTooltip>
                    Controls how often token market caps are refreshed.
                    Fast-lane for high-MC or SWAB-exposed tokens; slow-lane for
                    others.
                  </InfoTooltip>
                </h4>
                <div className='mb-4 flex items-center justify-between rounded-lg border p-3'>
                  <div>
                    <Label className='text-sm'>Slow-Lane Refresh Enabled</Label>
                    <p className='text-muted-foreground text-xs'>
                      {ingestSettings.slow_lane_interval_minutes ?? 240}min
                      refresh for non-SWAB tokens below MC threshold
                    </p>
                  </div>
                  <Switch
                    checked={ingestSettings.slow_lane_enabled ?? true}
                    onCheckedChange={(v) =>
                      updateIngestSetting({ slow_lane_enabled: v })
                    }
                  />
                </div>
                <div className='grid grid-cols-2 gap-4'>
                  <NumericStepper
                    label='MC Threshold ($)'
                    value={
                      ingestSettings.tracking_mc_threshold ??
                      ingestSettings.fast_lane_mc_threshold ??
                      100000
                    }
                    onChange={(v) =>
                      updateIngestSetting({ tracking_mc_threshold: v })
                    }
                    min={0}
                    max={10000000}
                    step={10000}
                    tooltip={`Tokens >= this MC get fast-lane refresh (${ingestSettings.fast_lane_interval_minutes ?? 30}min). Below get slow-lane (${ingestSettings.slow_lane_interval_minutes ?? 240}min).`}
                    bypassLimits={bypassLimits}
                  />
                  <NumericStepper
                    label='Fast-Lane Interval (min)'
                    value={ingestSettings.fast_lane_interval_minutes ?? 30}
                    onChange={(v) =>
                      updateIngestSetting({ fast_lane_interval_minutes: v })
                    }
                    min={5}
                    max={240}
                    step={5}
                    tooltip='Refresh interval for SWAB-exposed or high-MC tokens'
                    bypassLimits={bypassLimits}
                  />
                  <NumericStepper
                    label='Slow-Lane Interval (min)'
                    value={ingestSettings.slow_lane_interval_minutes ?? 240}
                    onChange={(v) =>
                      updateIngestSetting({ slow_lane_interval_minutes: v })
                    }
                    min={15}
                    max={1440}
                    step={15}
                    tooltip='Refresh interval for low-MC tokens without SWAB positions'
                    bypassLimits={bypassLimits}
                  />
                  <NumericStepper
                    label='Stale Warning (hours)'
                    value={ingestSettings.stale_threshold_hours ?? 4}
                    onChange={(v) =>
                      updateIngestSetting({ stale_threshold_hours: v })
                    }
                    min={1}
                    max={24}
                    step={1}
                    tooltip='Show warning badge if last refresh exceeds this'
                    bypassLimits={bypassLimits}
                  />
                </div>
              </div>
            )}

            {/* Drop Conditions */}
            {ingestSettings && (
              <div className='mb-4 border-t pt-4'>
                <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
                  Drop Conditions
                  <InfoTooltip>
                    Tokens that meet these conditions are excluded from MC
                    refresh to save API credits.
                  </InfoTooltip>
                </h4>
                <div className='space-y-3'>
                  <div className='flex items-center justify-between rounded-lg border p-3'>
                    <div>
                      <Label className='text-sm'>
                        Drop if MC Below Threshold
                      </Label>
                      <p className='text-muted-foreground text-xs'>
                        Stop refreshing tokens with MC below the tracking
                        threshold
                      </p>
                    </div>
                    <Switch
                      checked={
                        ingestSettings.drop_if_mc_below_threshold ?? false
                      }
                      onCheckedChange={(v) =>
                        updateIngestSetting({ drop_if_mc_below_threshold: v })
                      }
                    />
                  </div>
                  <div className='flex items-center justify-between rounded-lg border p-3'>
                    <div>
                      <Label className='text-sm'>
                        Drop if No SWAB Positions
                      </Label>
                      <p className='text-muted-foreground text-xs'>
                        Stop refreshing tokens with no open SWAB positions
                      </p>
                    </div>
                    <Switch
                      checked={
                        ingestSettings.drop_if_no_swab_positions ?? false
                      }
                      onCheckedChange={(v) =>
                        updateIngestSetting({ drop_if_no_swab_positions: v })
                      }
                    />
                  </div>
                  <div className='flex items-center justify-between rounded-lg border p-3'>
                    <div>
                      <Label className='text-sm'>Drop Condition Mode</Label>
                      <p className='text-muted-foreground text-xs'>
                        AND = both conditions must be true; OR = either
                        condition
                      </p>
                    </div>
                    <Select
                      value={ingestSettings.drop_condition_mode ?? 'AND'}
                      onValueChange={(v) =>
                        updateIngestSetting({
                          drop_condition_mode: v as 'AND' | 'OR'
                        })
                      }
                    >
                      <SelectTrigger className='w-24'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='AND'>AND</SelectItem>
                        <SelectItem value='OR'>OR</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            )}

            {/* SWAB Position Check Settings */}
            {swabSettings && (
              <div className='border-t pt-4'>
                <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
                  SWAB Position Check
                  <InfoTooltip>
                    Smart Wallet Archive Builder: tracks MTEW positions, detects
                    buys/sells, computes PnL. Uses Helius credits.
                  </InfoTooltip>
                </h4>
                <div className='mb-4 flex items-center justify-between rounded-lg border p-3'>
                  <div>
                    <Label className='text-sm'>Auto-Check Enabled</Label>
                    <p className='text-muted-foreground text-xs'>
                      Automatically check positions for sells
                    </p>
                  </div>
                  <Switch
                    checked={swabSettings.auto_check_enabled}
                    onCheckedChange={(v) =>
                      updateSwabSetting({ auto_check_enabled: v })
                    }
                  />
                </div>
                <div className='grid grid-cols-2 gap-4'>
                  <NumericStepper
                    label='Check Interval (min)'
                    value={swabSettings.check_interval_minutes}
                    onChange={(v) =>
                      updateSwabSetting({ check_interval_minutes: v })
                    }
                    min={5}
                    max={1440}
                    step={5}
                    tooltip='How often to check for position changes (5-1440 min)'
                    bypassLimits={bypassLimits}
                  />
                  <NumericStepper
                    label='Daily Credit Budget'
                    value={swabSettings.daily_credit_budget}
                    onChange={(v) =>
                      updateSwabSetting({ daily_credit_budget: v })
                    }
                    min={0}
                    max={100000}
                    step={500}
                    tooltip='Max credits for auto-checks per day (0-100k)'
                    bypassLimits={bypassLimits}
                  />
                  <NumericStepper
                    label='Stale Threshold (min)'
                    value={swabSettings.stale_threshold_minutes}
                    onChange={(v) =>
                      updateSwabSetting({ stale_threshold_minutes: v })
                    }
                    min={5}
                    max={1440}
                    step={30}
                    tooltip='Consider position stale after this time (5-1440 min)'
                    bypassLimits={bypassLimits}
                  />
                  <NumericStepper
                    label='Min Token Count'
                    value={swabSettings.min_token_count}
                    onChange={(v) => updateSwabSetting({ min_token_count: v })}
                    min={1}
                    max={50}
                    step={1}
                    tooltip='Only track wallets appearing in N+ tokens (1-50)'
                    bypassLimits={bypassLimits}
                  />
                </div>

                {/* SWAB Status */}
                {swabStats && (
                  <div className='mt-4'>
                    <h4 className='text-muted-foreground mb-2 text-xs font-semibold uppercase'>
                      SWAB Status
                    </h4>
                    <div className='bg-muted/30 grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border p-4 text-xs'>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>
                          Total Positions:
                        </span>
                        <span>{swabStats.total_positions}</span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>
                          Still Holding:
                        </span>
                        <span>{swabStats.holding}</span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Sold:</span>
                        <span>{swabStats.sold}</span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>
                          Credits Today:
                        </span>
                        <span>{swabStats.credits_used_today}</span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>
                          Last Check:
                        </span>
                        <span>
                          {formatTimestamp(
                            schedulerStatus?.last_check_at ?? null
                          )}
                        </span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>
                          Next Check:
                        </span>
                        <span>
                          {formatTimestamp(
                            schedulerStatus?.next_check_at ?? null
                          )}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Manual Actions */}
                <div className='mt-4 border-t pt-4'>
                  <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>
                    Manual Actions
                  </h4>
                  <div className='flex gap-2'>
                    <Button
                      variant='outline'
                      size='sm'
                      onClick={runCheck}
                      disabled={runningCheck}
                    >
                      {runningCheck ? (
                        <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                      ) : (
                        <Activity className='mr-1 h-3 w-3' />
                      )}
                      Check Positions
                    </Button>
                    <Button
                      variant='outline'
                      size='sm'
                      onClick={runPnlUpdate}
                      disabled={runningPnl}
                    >
                      {runningPnl ? (
                        <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                      ) : (
                        <RefreshCw className='mr-1 h-3 w-3' />
                      )}
                      Update PnL (Free)
                    </Button>
                  </div>
                </div>

                {/* Reconciliation */}
                <div className='mt-4 border-t pt-4'>
                  <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
                    Reconciliation
                    <InfoTooltip>
                      Fix positions where sells were missed. Scans recent
                      transactions to find actual exit prices.
                    </InfoTooltip>
                  </h4>
                  <div className='mb-4 flex items-start gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3'>
                    <AlertTriangle className='mt-0.5 h-4 w-4 text-yellow-500' />
                    <p className='text-xs text-yellow-200'>
                      Reconciliation uses Helius credits. Each position checked
                      costs ~1 credit.
                    </p>
                  </div>
                  <div className='mb-4 grid grid-cols-2 gap-4'>
                    <NumericStepper
                      label='Max Signatures'
                      value={reconcileMaxSigs}
                      onChange={setReconcileMaxSigs}
                      min={10}
                      step={10}
                      tooltip='Transaction signatures to scan per position'
                    />
                    <NumericStepper
                      label='Max Positions'
                      value={reconcileMaxPos}
                      onChange={setReconcileMaxPos}
                      min={1}
                      step={10}
                      tooltip='Positions to reconcile per run'
                    />
                  </div>
                  <Button
                    variant='default'
                    size='sm'
                    onClick={runReconcile}
                    disabled={runningReconcile}
                  >
                    {runningReconcile ? (
                      <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                    ) : (
                      <Play className='mr-1 h-3 w-3' />
                    )}
                    Run Reconciliation
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
