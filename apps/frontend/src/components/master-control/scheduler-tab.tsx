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
  Clock,
  Zap
} from 'lucide-react';
import { toast } from 'sonner';
import {
  updateSwabSettings,
  updateIngestSettings,
  SwabSettings,
  SwabStats,
  IngestSettings,
  API_BASE_URL
} from '@/lib/api';
import { NumericStepper } from './NumericStepper';
import { InfoTooltip } from './InfoTooltip';
import { formatTimestamp } from './utils';

// Session storage keys
const CACHE_KEY_INGEST = 'scheduler_ingest_settings';
const CACHE_KEY_SWAB = 'scheduler_swab_settings';
const CACHE_KEY_STATS = 'scheduler_swab_stats';
const CACHE_KEY_STATUS = 'scheduler_status';

const FAST_FETCH_TIMEOUT = 4000;
const FAST_FETCH_RETRIES = 1;

interface SchedulerTabProps {
  bypassLimits?: boolean;
}

function SectionSkeleton({ title, icon }: { title: string; icon: React.ReactNode }) {
  return (
    <div className='animate-pulse'>
      <div className='mb-4 flex items-center gap-2 border-b pb-2'>
        {icon}
        <h3 className='text-sm font-semibold'>{title}</h3>
      </div>
      <div className='space-y-4'>
        <div className='bg-muted h-4 w-48 rounded' />
        <div className='grid grid-cols-3 gap-4'>
          <div className='bg-muted h-16 rounded-lg' />
          <div className='bg-muted h-16 rounded-lg' />
          <div className='bg-muted h-16 rounded-lg' />
        </div>
      </div>
    </div>
  );
}

async function fastFetch(url: string): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FAST_FETCH_TIMEOUT);
  let lastError: Error | null = null;
  for (let attempt = 0; attempt <= FAST_FETCH_RETRIES; attempt++) {
    try {
      const response = await fetch(url, { signal: controller.signal, cache: 'no-store' });
      clearTimeout(timeoutId);
      return response;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt < FAST_FETCH_RETRIES) await new Promise((r) => setTimeout(r, 500));
    }
  }
  clearTimeout(timeoutId);
  throw lastError;
}

function getFromCache<T>(key: string): T | null {
  try { const c = sessionStorage.getItem(key); return c ? JSON.parse(c) : null; } catch { return null; }
}
function setInCache<T>(key: string, value: T): void {
  try { sessionStorage.setItem(key, JSON.stringify(value)); } catch {}
}

// ============================================================================
// Credit Estimate Helpers
// ============================================================================

function CreditEstimate({ text }: { text: string }) {
  return (
    <p className='text-[10px] text-amber-400/80 mt-2 flex items-center gap-1'>
      <Zap className='h-3 w-3' />
      {text}
    </p>
  );
}

function estimateDiscoveryCredits(settings: IngestSettings): string {
  const maxTokens = settings.discovery_max_per_run ?? settings.tier0_max_tokens_per_run ?? 50;
  const walletCount = 100; // from api_settings
  // Each token analysis: ~30-80 credits (getSignaturesForAddress + parsing)
  const perToken = 50; // avg
  const perRun = maxTokens * perToken;
  const interval = settings.discovery_interval_minutes ?? settings.tier0_interval_minutes ?? 60;
  const runsPerDay = Math.floor(1440 / interval);
  return `~${perRun.toLocaleString()} credits/run × ${runsPerDay} runs/day = ~${(perRun * runsPerDay).toLocaleString()} credits/day`;
}

function estimateRealtimeCredits(_settings: IngestSettings): string {
  return 'Detection is free (WebSocket). Follow-up tracking uses DexScreener (free). Zero Helius credits.';
}

function estimatePositionCredits(settings: SwabSettings, stats: SwabStats | null): string {
  const positions = stats?.holding ?? 0;
  const creditsPerCheck = positions * 10; // ~10 credits per position check
  const interval = settings.check_interval_minutes;
  const checksPerDay = Math.floor(1440 / interval);
  const daily = creditsPerCheck * checksPerDay;
  const budget = settings.daily_credit_budget;
  return `~${creditsPerCheck.toLocaleString()} credits/check (${positions} positions × 10) × ${checksPerDay}/day = ~${daily.toLocaleString()} credits/day (budget: ${budget.toLocaleString()})`;
}

// ============================================================================
// Main Component
// ============================================================================

export function SchedulerTab({ bypassLimits = false }: SchedulerTabProps) {
  const [ingestSettings, setIngestSettings] = useState<IngestSettings | null>(
    () => getFromCache<IngestSettings>(CACHE_KEY_INGEST)
  );
  const [ingestLoading, setIngestLoading] = useState(!ingestSettings);
  const [ingestError, setIngestError] = useState<string | null>(null);

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

  const mountedRef = useRef(true);

  const loadIngestData = useCallback(async (showLoader = true) => {
    if (showLoader) setIngestLoading(true);
    setIngestError(null);
    try {
      const response = await fastFetch(`${API_BASE_URL}/api/ingest/settings`);
      const data = await response.json();
      if (mountedRef.current) { setIngestSettings(data); setInCache(CACHE_KEY_INGEST, data); }
    } catch {
      if (mountedRef.current) setIngestError('Failed to load discovery settings');
    } finally {
      if (mountedRef.current) setIngestLoading(false);
    }
  }, []);

  const loadSwabData = useCallback(async (showLoader = true) => {
    if (showLoader) setSwabLoading(true);
    setSwabError(null);
    try {
      const [settingsRes, statsRes, statusRes] = await Promise.allSettled([
        fastFetch(`${API_BASE_URL}/api/swab/settings`),
        fastFetch(`${API_BASE_URL}/api/swab/stats`),
        fastFetch(`${API_BASE_URL}/api/swab/scheduler/status`)
      ]);
      if (mountedRef.current) {
        if (settingsRes.status === 'fulfilled') { const s = await settingsRes.value.json(); setSwabSettings(s); setInCache(CACHE_KEY_SWAB, s); }
        if (statsRes.status === 'fulfilled') { const s = await statsRes.value.json(); setSwabStats(s); setInCache(CACHE_KEY_STATS, s); }
        if (statusRes.status === 'fulfilled') { const s = await statusRes.value.json(); setSchedulerStatus(s); setInCache(CACHE_KEY_STATUS, s); }
        if (settingsRes.status === 'rejected' && statsRes.status === 'rejected' && statusRes.status === 'rejected') {
          setSwabError('Failed to load position tracker settings');
        }
      }
    } catch {
      if (mountedRef.current) setSwabError('Failed to load position tracker settings');
    } finally {
      if (mountedRef.current) setSwabLoading(false);
    }
  }, []);

  const initialCacheRef = useRef({
    hadIngest: getFromCache<IngestSettings>(CACHE_KEY_INGEST) !== null,
    hadSwab: getFromCache<SwabSettings>(CACHE_KEY_SWAB) !== null
  });

  useEffect(() => {
    mountedRef.current = true;
    loadIngestData(!initialCacheRef.current.hadIngest);
    loadSwabData(!initialCacheRef.current.hadSwab);
    return () => { mountedRef.current = false; };
  }, [loadIngestData, loadSwabData]);

  const updateIngestSetting = async (updates: Partial<IngestSettings>) => {
    if (!ingestSettings) return;
    const newSettings = { ...ingestSettings, ...updates };
    setIngestSettings(newSettings);
    setInCache(CACHE_KEY_INGEST, newSettings);
    try {
      await updateIngestSettings(updates);
      window.dispatchEvent(new Event('meridinate:settings-changed'));
      toast.success('Setting saved');
    } catch { toast.error('Failed to save setting'); }
  };

  const updateSwabSetting = async (updates: Partial<SwabSettings>) => {
    if (!swabSettings) return;
    const newSettings = { ...swabSettings, ...updates } as SwabSettings;
    setSwabSettings(newSettings);
    setInCache(CACHE_KEY_SWAB, newSettings);
    try {
      await updateSwabSettings(updates);
      window.dispatchEvent(new Event('meridinate:settings-changed'));
      toast.success('Setting saved');
    } catch { toast.error('Failed to save setting'); }
  };

  return (
    <div className='space-y-6'>
      {/* ================================================================== */}
      {/* SECTION 1: TOKEN DISCOVERY */}
      {/* ================================================================== */}
      <div>
        {ingestLoading && !ingestSettings ? (
          <SectionSkeleton title='Auto-Scan Pipeline' icon={<Zap className='h-4 w-4 text-yellow-500' />} />
        ) : ingestError && !ingestSettings ? (
          <div className='flex flex-col items-center justify-center gap-3 py-8'>
            <AlertTriangle className='h-6 w-6 text-yellow-500' />
            <p className='text-muted-foreground text-sm'>{ingestError}</p>
            <Button variant='outline' size='sm' onClick={() => loadIngestData()}>
              <RefreshCw className='mr-2 h-3 w-3' /> Retry
            </Button>
          </div>
        ) : ingestSettings && (
          <>
            {/* Header with enable toggle */}
            <div className='mb-4 flex items-center justify-between border-b pb-2'>
              <div className='flex items-center gap-2'>
                <Zap className='h-4 w-4 text-yellow-500' />
                <h3 className='text-sm font-semibold'>Auto-Scan Pipeline</h3>
                <InfoTooltip>
                  Discovers tokens from DexScreener (free) and analyzes via Helius (credits).
                </InfoTooltip>
              </div>
              <div className='flex items-center gap-2'>
                {ingestLoading && <Loader2 className='text-muted-foreground h-3 w-3 animate-spin' />}
                <Switch
                  checked={ingestSettings.discovery_enabled ?? ingestSettings.ingest_enabled ?? false}
                  onCheckedChange={(v) => {
                    updateIngestSetting({ discovery_enabled: v, ingest_enabled: v });
                  }}
                />
              </div>
            </div>

            {/* Scan Thresholds + Interval — 3-col grid */}
            <div className='mb-4'>
              <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>
                Scan Thresholds & Interval
              </h4>
              <div className='grid grid-cols-3 gap-4'>
                <NumericStepper label='Min Market Cap ($)' value={ingestSettings.mc_min} onChange={(v) => updateIngestSetting({ mc_min: v })} min={0} step={5000} tooltip='Minimum market cap to pass scan filter' bypassLimits={bypassLimits} />
                <NumericStepper label='Min Volume ($)' value={ingestSettings.volume_min} onChange={(v) => updateIngestSetting({ volume_min: v })} min={0} step={1000} tooltip='Minimum 24h volume' bypassLimits={bypassLimits} />
                <NumericStepper label='Min Liquidity ($)' value={ingestSettings.liquidity_min} onChange={(v) => updateIngestSetting({ liquidity_min: v })} min={0} step={1000} tooltip='Minimum liquidity' bypassLimits={bypassLimits} />
                <NumericStepper label='Max Age (hours)' value={ingestSettings.age_max_hours} onChange={(v) => updateIngestSetting({ age_max_hours: v })} min={1} step={6} tooltip='Maximum token age for discovery' bypassLimits={bypassLimits} />
                <div className='space-y-2'>
                  <Label className='text-xs'>Scan Interval</Label>
                  <Select
                    value={String(ingestSettings.discovery_interval_minutes ?? ingestSettings.tier0_interval_minutes ?? 60)}
                    onValueChange={(v) => updateIngestSetting({ discovery_interval_minutes: parseInt(v, 10) })}
                  >
                    <SelectTrigger className='w-full'><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value='5'>Every 5 min</SelectItem>
                      <SelectItem value='10'>Every 10 min</SelectItem>
                      <SelectItem value='15'>Every 15 min</SelectItem>
                      <SelectItem value='30'>Every 30 min</SelectItem>
                      <SelectItem value='60'>Every 60 min</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <NumericStepper label='Max Tokens/Run' value={ingestSettings.discovery_max_per_run ?? ingestSettings.tier0_max_tokens_per_run ?? 50} onChange={(v) => updateIngestSetting({ discovery_max_per_run: v })} min={1} step={10} tooltip='Max tokens to scan per run' bypassLimits={bypassLimits} />
              </div>
              <CreditEstimate text={estimateDiscoveryCredits(ingestSettings)} />
            </div>

            {/* Pipeline Filters */}
            <div className='mb-4 border-t pt-4'>
              <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>Pipeline Filters</h4>

              {/* Launchpads */}
              <div className='mb-3'>
                <Label className='mb-2 block text-xs'>Launchpads</Label>
                <div className='grid grid-cols-4 gap-1.5'>
                  {[
                    { id: 'pumpswap', label: 'Pump.fun' },
                    { id: 'raydium', label: 'Raydium' },
                    { id: 'orca', label: 'Orca' },
                    { id: 'meteora', label: 'Meteora' },
                    { id: 'moonshot', label: 'Moonshot' },
                    { id: 'believe', label: 'Believe' },
                    { id: 'launchlab', label: 'LaunchLab' },
                    { id: 'boop', label: 'Boop' },
                  ].map(({ id, label }) => {
                    const included = (ingestSettings.launchpad_include ?? []) as string[];
                    const isChecked = included.length === 0 || included.includes(id);
                    return (
                      <label key={id} className={`flex cursor-pointer items-center gap-1.5 rounded border px-2 py-1 text-[11px] transition-colors ${isChecked ? 'border-primary/30 bg-primary/5 text-foreground' : 'border-muted bg-muted/30 text-muted-foreground line-through'}`}>
                        <input type='checkbox' className='h-3 w-3 rounded' checked={isChecked}
                          onChange={(e) => {
                            let newInclude: string[];
                            if (included.length === 0) {
                              newInclude = ['pumpswap', 'raydium', 'orca', 'meteora', 'moonshot', 'believe', 'launchlab', 'boop'].filter((x) => x !== id);
                            } else if (e.target.checked) {
                              newInclude = [...included, id];
                            } else {
                              newInclude = included.filter((x) => x !== id);
                            }
                            if (newInclude.length >= 8) newInclude = [];
                            updateIngestSetting({ launchpad_include: newInclude });
                          }}
                        />
                        {label}
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Text filters — 3 col */}
              <div className='mb-3 grid grid-cols-3 gap-4'>
                <div className='space-y-1'>
                  <Label className='text-xs'>Quote Token</Label>
                  <input type='text' className='bg-background h-8 w-full rounded-md border px-2 text-xs' placeholder='SOL, USDC, ...'
                    value={(ingestSettings.quote_token_include ?? []).join(', ')}
                    onChange={(e) => updateIngestSetting({ quote_token_include: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                  />
                </div>
                <div className='space-y-1'>
                  <Label className='text-xs'>Address Suffix</Label>
                  <input type='text' className='bg-background h-8 w-full rounded-md border px-2 text-xs' placeholder='bonk, pump, ...'
                    value={(ingestSettings.address_suffix_include ?? []).join(', ')}
                    onChange={(e) => updateIngestSetting({ address_suffix_include: e.target.value.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean) })}
                  />
                </div>
                <div className='flex items-center justify-between rounded-lg border p-2'>
                  <Label className='text-xs'>Require Socials</Label>
                  <Switch checked={ingestSettings.require_socials ?? false} onCheckedChange={(v) => updateIngestSetting({ require_socials: v })} />
                </div>
              </div>

              {/* Transaction + keyword filters — 3 col */}
              <div className='mb-3 grid grid-cols-3 gap-4'>
                <NumericStepper label='Min Buys (24h)' value={ingestSettings.buys_24h_min ?? 0} onChange={(v) => updateIngestSetting({ buys_24h_min: v || null })} min={0} step={10} tooltip='Minimum buy transactions in 24h' bypassLimits={bypassLimits} />
                <NumericStepper label='Min Net Buys (24h)' value={ingestSettings.net_buys_24h_min ?? 0} onChange={(v) => updateIngestSetting({ net_buys_24h_min: v || null })} min={0} step={5} tooltip='Min net buys (buys minus sells)' bypassLimits={bypassLimits} />
                <NumericStepper label='Min TXs (24h)' value={ingestSettings.txs_24h_min ?? 0} onChange={(v) => updateIngestSetting({ txs_24h_min: v || null })} min={0} step={10} tooltip='Minimum total transactions in 24h' bypassLimits={bypassLimits} />
              </div>
              <div className='grid grid-cols-3 gap-4'>
                <NumericStepper label='Min 1h Price Change (%)' value={ingestSettings.price_change_h1_min ?? 0} onChange={(v) => updateIngestSetting({ price_change_h1_min: v || null })} min={-100} step={5} tooltip='Minimum 1-hour price change %' bypassLimits={bypassLimits} />
                <div className='space-y-1'>
                  <Label className='text-xs'>Keyword Include</Label>
                  <input type='text' className='bg-background h-8 w-full rounded-md border px-2 text-xs' placeholder='pepe, doge, ...'
                    value={(ingestSettings.keyword_include ?? []).join(', ')}
                    onChange={(e) => updateIngestSetting({ keyword_include: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                  />
                </div>
                <div className='space-y-1'>
                  <Label className='text-xs'>Keyword Exclude</Label>
                  <input type='text' className='bg-background h-8 w-full rounded-md border px-2 text-xs' placeholder='scam, rug, ...'
                    value={(ingestSettings.keyword_exclude ?? []).join(', ')}
                    onChange={(e) => updateIngestSetting({ keyword_exclude: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                  />
                </div>
              </div>
            </div>

            {/* CLOBr Enrichment */}
            <div className='mb-4 border-t pt-4'>
              <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>
                CLOBr Enrichment
              </h4>
              <p className='text-muted-foreground mb-3 text-[10px]'>
                Enrich tokens with CLOBr liquidity scores and market depth during MC tracking. Tokens below the warning threshold are flagged.
              </p>
              <div className='grid grid-cols-3 gap-4'>
                <div className='flex items-center justify-between rounded-lg border p-2'>
                  <Label className='text-xs'>Enable CLOBr Enrichment</Label>
                  <Switch
                    checked={ingestSettings.clobr_enabled ?? false}
                    onCheckedChange={(v) => updateIngestSetting({ clobr_enabled: v })}
                  />
                </div>
                <NumericStepper
                  label='Warning Threshold'
                  value={ingestSettings.clobr_min_score ?? 50}
                  onChange={(v) => updateIngestSetting({ clobr_min_score: v })}
                  min={0}
                  max={100}
                  step={5}
                  tooltip='CLOBr warning threshold (0-100). Tokens below this are flagged with weak liquidity in the UI.'
                  bypassLimits={bypassLimits}
                  disabled={!(ingestSettings.clobr_enabled ?? false)}
                />
              </div>
            </div>

            {/* Real-Time Detection + Follow-Up — side by side */}
            <div className='border-t pt-4'>
              <div className='grid grid-cols-2 gap-6'>
                <div>
                  <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>Real-Time Detection</h4>
                  <div className='space-y-3'>
                    <NumericStepper label='Watch Window (sec)' value={ingestSettings.realtime_watch_window_seconds ?? 300} onChange={(v) => updateIngestSetting({ realtime_watch_window_seconds: v })} min={60} max={600} step={30} tooltip='How long to monitor each new token after creation' bypassLimits={bypassLimits} />
                    <NumericStepper label='Min MC at Close ($)' value={ingestSettings.realtime_mc_min_at_close ?? 5000} onChange={(v) => updateIngestSetting({ realtime_mc_min_at_close: v })} min={0} max={1000000} step={1000} tooltip='Min market cap at watch window close for HIGH CONVICTION' bypassLimits={bypassLimits} />
                  </div>
                  <CreditEstimate text={estimateRealtimeCredits(ingestSettings)} />
                </div>
                <div>
                  <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>Follow-Up Tracking</h4>
                  <div className='space-y-3'>
                    <NumericStepper label='Max Duration (min)' value={ingestSettings.followup_max_duration_minutes ?? 120} onChange={(v) => updateIngestSetting({ followup_max_duration_minutes: v })} min={30} max={480} step={15} tooltip='Max time to track after watch window closes' bypassLimits={bypassLimits} />
                    <NumericStepper label='Check Interval (sec)' value={ingestSettings.followup_check_interval_seconds ?? 120} onChange={(v) => updateIngestSetting({ followup_check_interval_seconds: v })} min={30} max={600} step={15} tooltip='DexScreener check frequency (free, 60 calls/min limit)' bypassLimits={bypassLimits} />
                  </div>
                </div>
              </div>
            </div>

            {/* Last Scan Info */}
            {ingestSettings.last_discovery_run_at && (
              <p className='text-muted-foreground border-t pt-3 text-xs'>
                Last scan: {formatTimestamp(ingestSettings.last_discovery_run_at ?? ingestSettings.last_tier0_run_at ?? null)}
              </p>
            )}
          </>
        )}
      </div>

      {/* ================================================================== */}
      {/* SECTION 2: POSITION TRACKER */}
      {/* ================================================================== */}
      <div className='border-t pt-6'>
        {swabLoading && !swabSettings ? (
          <SectionSkeleton title='Position Tracker' icon={<Clock className='h-4 w-4 text-blue-500' />} />
        ) : swabError && !swabSettings ? (
          <div className='flex flex-col items-center justify-center gap-3 py-8'>
            <AlertTriangle className='h-6 w-6 text-yellow-500' />
            <p className='text-muted-foreground text-sm'>{swabError}</p>
            <Button variant='outline' size='sm' onClick={() => loadSwabData()}>
              <RefreshCw className='mr-2 h-3 w-3' /> Retry
            </Button>
          </div>
        ) : swabSettings && (
          <>
            {/* Header with enable toggle */}
            <div className='mb-4 flex items-center justify-between border-b pb-2'>
              <div className='flex items-center gap-2'>
                <Clock className='h-4 w-4 text-blue-500' />
                <h3 className='text-sm font-semibold'>Position Tracker</h3>
                <InfoTooltip>
                  Monitors wallet positions, detects buys/sells, computes real PnL. Uses Helius credits.
                </InfoTooltip>
              </div>
              <div className='flex items-center gap-2'>
                {swabLoading && <Loader2 className='text-muted-foreground h-3 w-3 animate-spin' />}
                <Switch
                  checked={swabSettings.auto_check_enabled}
                  onCheckedChange={(v) => updateSwabSetting({ auto_check_enabled: v })}
                />
              </div>
            </div>

            <div className='grid grid-cols-3 gap-4'>
              <NumericStepper label='Check Interval (min)' value={swabSettings.check_interval_minutes} onChange={(v) => updateSwabSetting({ check_interval_minutes: v })} min={5} max={1440} step={5} tooltip='How often to check for position changes' bypassLimits={bypassLimits} />
              <NumericStepper label='Daily Credit Budget' value={swabSettings.daily_credit_budget} onChange={(v) => updateSwabSetting({ daily_credit_budget: v })} min={0} max={10000000} step={10000} tooltip='Max Helius credits for position checks per day' bypassLimits={bypassLimits} />
              <NumericStepper label='Min Token Count' value={swabSettings.min_token_count} onChange={(v) => updateSwabSetting({ min_token_count: v })} min={1} max={50} step={1} tooltip='Only track wallets in N+ tokens' bypassLimits={bypassLimits} />
            </div>

            {/* Status + Credit Estimate */}
            {swabStats && (
              <div className='mt-3 bg-muted/30 grid grid-cols-3 gap-x-6 gap-y-1.5 rounded-lg border p-3 text-xs'>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>Positions:</span>
                  <span>{swabStats.total_positions} ({swabStats.holding} holding)</span>
                </div>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>Credits Today:</span>
                  <span>{swabStats.credits_used_today}</span>
                </div>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>Next Check:</span>
                  <span>{formatTimestamp(schedulerStatus?.next_check_at ?? null)}</span>
                </div>
              </div>
            )}
            <CreditEstimate text={estimatePositionCredits(swabSettings, swabStats)} />
          </>
        )}
      </div>
    </div>
  );
}
