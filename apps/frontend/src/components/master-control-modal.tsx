'use client';

import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import {
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Info,
  Loader2,
  Trash2,
  RefreshCw,
  Plus,
  Webhook,
  Bell,
  Settings2,
  Zap,
  Activity,
  AlertTriangle,
  Play
} from 'lucide-react';
import { toast } from 'sonner';
import {
  getIngestSettings,
  updateIngestSettings,
  IngestSettings,
  getSolscanSettings,
  updateSolscanSettings,
  SolscanSettings,
  getSwabSettings,
  updateSwabSettings,
  getSwabStats,
  getSwabSchedulerStatus,
  triggerSwabCheck,
  triggerSwabPnlUpdate,
  reconcileAllPositions,
  SwabSettings,
  SwabStats,
  API_BASE_URL,
  fetchWithTimeout
} from '@/lib/api';

// Settings modal timeout - shorter than default to fail fast during ingestion
const SETTINGS_FETCH_TIMEOUT = 3000;

interface ApiSettings {
  transactionLimit: number;
  minUsdFilter: number;
  walletCount: number;
  apiRateDelay: number;
  maxCreditsPerAnalysis: number;
  maxRetries: number;
  bypassLimits?: boolean;
}

interface MasterControlModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  apiSettings: ApiSettings;
  setApiSettings: (settings: ApiSettings) => void;
  defaultApiSettings: ApiSettings;
  children: React.ReactNode;
}

interface WebhookInfo {
  webhookID: string;
  webhookURL: string;
  accountAddresses?: string[];
  webhookType?: string;
}

// Local storage key for banner preferences
const BANNER_PREFS_KEY = 'meridinate_banner_prefs';

interface BannerPrefs {
  showIngestBanner: boolean;
}

const defaultBannerPrefs: BannerPrefs = {
  showIngestBanner: true
};

function loadBannerPrefs(): BannerPrefs {
  if (typeof window === 'undefined') return defaultBannerPrefs;
  try {
    const stored = localStorage.getItem(BANNER_PREFS_KEY);
    return stored ? JSON.parse(stored) : defaultBannerPrefs;
  } catch {
    return defaultBannerPrefs;
  }
}

function saveBannerPrefs(prefs: BannerPrefs) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(BANNER_PREFS_KEY, JSON.stringify(prefs));
}

// Helper component for info tooltips
function InfoTooltip({ children }: { children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className='text-muted-foreground ml-1 inline h-3 w-3 cursor-help' />
      </TooltipTrigger>
      <TooltipContent side='right' className='max-w-[250px] text-xs'>
        {children}
      </TooltipContent>
    </Tooltip>
  );
}

// Numeric input with stepper buttons
function NumericStepper({
  label,
  value,
  onChange,
  onReset,
  min,
  max,
  step,
  tooltip,
  bypassLimits = false
}: {
  label: string;
  value: number;
  onChange: (val: number) => void;
  onReset?: () => void;
  min: number;
  max?: number;
  step: number;
  tooltip?: string;
  bypassLimits?: boolean;
}) {
  // When bypassLimits is true, only enforce min >= 0
  const effectiveMin = bypassLimits ? 0 : min;
  const effectiveMax = bypassLimits ? undefined : max;
  return (
    <div className='space-y-1'>
      <Label className='flex items-center text-xs'>
        {label}
        {tooltip && <InfoTooltip>{tooltip}</InfoTooltip>}
      </Label>
      <div className='flex items-center gap-1'>
        <Button
          variant='outline'
          size='icon'
          className='h-7 w-7'
          onClick={() => onChange(Math.max(effectiveMin, value - step))}
        >
          <ChevronLeft className='h-3 w-3' />
        </Button>
        <Input
          type='number'
          value={value}
          onChange={(e) => {
            const v = parseInt(e.target.value) || effectiveMin;
            onChange(
              effectiveMax
                ? Math.min(effectiveMax, Math.max(effectiveMin, v))
                : Math.max(effectiveMin, v)
            );
          }}
          className='h-7 text-center text-xs [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'
        />
        <Button
          variant='outline'
          size='icon'
          className='h-7 w-7'
          onClick={() =>
            onChange(
              effectiveMax ? Math.min(effectiveMax, value + step) : value + step
            )
          }
        >
          <ChevronRight className='h-3 w-3' />
        </Button>
        {onReset && (
          <Button
            variant='ghost'
            size='icon'
            className='h-7 w-7'
            onClick={onReset}
            title='Reset to default'
          >
            <RotateCcw className='h-3 w-3' />
          </Button>
        )}
      </div>
    </div>
  );
}

// Format timestamp helper
function formatTimestamp(ts: string | null) {
  if (!ts) return 'Never';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

// ============================================================================
// Scanning Tab (Manual Scan + Solscan/Action Wheel)
// ============================================================================
function ScanningTab({
  apiSettings,
  setApiSettings,
  defaultApiSettings
}: {
  apiSettings: ApiSettings;
  setApiSettings: (s: ApiSettings) => void;
  defaultApiSettings: ApiSettings;
}) {
  const [solscanSettings, setSolscanSettings] =
    useState<SolscanSettings | null>(null);
  const [loadingSolscan, setLoadingSolscan] = useState(true);
  const [solscanError, setSolscanError] = useState<string | null>(null);

  const loadSolscanSettings = async () => {
    setLoadingSolscan(true);
    setSolscanError(null);
    try {
      const res = await fetchWithTimeout(
        `${API_BASE_URL}/api/solscan-settings`,
        { cache: 'no-store' },
        SETTINGS_FETCH_TIMEOUT
      );
      if (!res.ok) throw new Error('Failed to fetch');
      const data = await res.json();
      setSolscanSettings(data);
    } catch (err) {
      const message =
        err instanceof Error && err.message.includes('timeout')
          ? 'Backend busy. Retry shortly.'
          : 'Failed to load';
      setSolscanError(message);
    } finally {
      setLoadingSolscan(false);
    }
  };

  useEffect(() => {
    loadSolscanSettings();
  }, []);

  const updateSolscan = async (updates: Partial<SolscanSettings>) => {
    if (!solscanSettings) return;
    const newSettings = { ...solscanSettings, ...updates };
    setSolscanSettings(newSettings);
    try {
      await updateSolscanSettings(updates);
      toast.success('Solscan settings saved');
    } catch {
      toast.error('Failed to save Solscan settings');
    }
  };

  const bypassLimits = apiSettings.bypassLimits ?? false;

  return (
    <div className='space-y-6'>
      {/* Bypass Limits Toggle */}
      <div className='bg-muted/50 flex items-center justify-between rounded-lg p-3'>
        <div className='space-y-0.5'>
          <p className='text-sm font-medium'>Bypass All Limits</p>
          <p className='text-muted-foreground text-xs'>
            Remove all slider caps (UI and backend validation)
          </p>
        </div>
        <Switch
          checked={bypassLimits}
          onCheckedChange={(v) =>
            setApiSettings({ ...apiSettings, bypassLimits: v })
          }
        />
      </div>

      {/* Manual Scan Settings */}
      <div>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Manual Scan Settings
          <InfoTooltip>
            Controls for manual token analysis: wallet limits, transaction
            depth, and filtering.
          </InfoTooltip>
        </h4>
        <div className='grid grid-cols-2 gap-4'>
          <NumericStepper
            label='Transaction Limit'
            value={apiSettings.transactionLimit}
            onChange={(v) =>
              setApiSettings({ ...apiSettings, transactionLimit: v })
            }
            onReset={() =>
              setApiSettings({
                ...apiSettings,
                transactionLimit: defaultApiSettings.transactionLimit
              })
            }
            min={100}
            max={20000}
            step={500}
            tooltip='Maximum transactions to scan per wallet for early buyer detection (100-20k)'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Min USD Filter ($)'
            value={apiSettings.minUsdFilter}
            onChange={(v) =>
              setApiSettings({ ...apiSettings, minUsdFilter: v })
            }
            onReset={() =>
              setApiSettings({
                ...apiSettings,
                minUsdFilter: defaultApiSettings.minUsdFilter
              })
            }
            min={10}
            max={500}
            step={10}
            tooltip='Minimum USD value to consider a wallet as an early buyer'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Wallet Count'
            value={apiSettings.walletCount}
            onChange={(v) => setApiSettings({ ...apiSettings, walletCount: v })}
            onReset={() =>
              setApiSettings({
                ...apiSettings,
                walletCount: defaultApiSettings.walletCount
              })
            }
            min={5}
            step={5}
            tooltip='Number of early buyer wallets to track per token'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Max Credits/Analysis'
            value={apiSettings.maxCreditsPerAnalysis}
            onChange={(v) =>
              setApiSettings({ ...apiSettings, maxCreditsPerAnalysis: v })
            }
            onReset={() =>
              setApiSettings({
                ...apiSettings,
                maxCreditsPerAnalysis: defaultApiSettings.maxCreditsPerAnalysis
              })
            }
            min={100}
            step={100}
            tooltip='Maximum Helius API credits to spend per token analysis'
            bypassLimits={bypassLimits}
          />
        </div>

        {/* Advanced Settings */}
        <details className='mt-4'>
          <summary className='text-muted-foreground hover:text-foreground cursor-pointer text-xs font-medium'>
            Advanced Settings
          </summary>
          <div className='mt-2 grid grid-cols-2 gap-4'>
            <div className='space-y-1'>
              <Label className='text-muted-foreground text-xs'>
                API Rate Delay (ms)
              </Label>
              <Input
                type='number'
                value={apiSettings.apiRateDelay}
                onChange={(e) =>
                  setApiSettings({
                    ...apiSettings,
                    apiRateDelay: parseInt(e.target.value) || 0
                  })
                }
                className='h-7 text-xs'
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-muted-foreground text-xs'>
                Max Retries
              </Label>
              <Input
                type='number'
                value={apiSettings.maxRetries}
                onChange={(e) =>
                  setApiSettings({
                    ...apiSettings,
                    maxRetries: parseInt(e.target.value) || 0
                  })
                }
                className='h-7 text-xs'
              />
            </div>
          </div>
        </details>
      </div>

      {/* Solscan / Action Wheel Settings */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Solscan / Action Wheel
          <InfoTooltip>
            URL parameters for action wheel Solscan links. Changes sync to
            action_wheel_settings.ini.
          </InfoTooltip>
        </h4>

        {loadingSolscan ? (
          <div className='flex items-center justify-center py-4'>
            <Loader2 className='h-4 w-4 animate-spin' />
          </div>
        ) : solscanError ? (
          <div className='flex items-center justify-center gap-2 py-4'>
            <span className='text-muted-foreground text-xs'>
              {solscanError}
            </span>
            <Button
              variant='ghost'
              size='sm'
              className='h-6 px-2'
              onClick={loadSolscanSettings}
            >
              <RefreshCw className='h-3 w-3' />
            </Button>
          </div>
        ) : solscanSettings ? (
          <div className='grid grid-cols-2 gap-4'>
            <div className='space-y-1'>
              <Label className='text-xs'>Activity Type</Label>
              <select
                value={solscanSettings.activity_type}
                onChange={(e) =>
                  updateSolscan({ activity_type: e.target.value })
                }
                className='border-input bg-background flex h-7 w-full rounded-md border px-2 text-xs'
              >
                <option value='ACTIVITY_SPL_TRANSFER'>Transfer</option>
                <option value='ACTIVITY_SPL_MINT'>Mint</option>
                <option value='ACTIVITY_SPL_BURN'>Burn</option>
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-xs'>Page Size</Label>
              <select
                value={solscanSettings.page_size}
                onChange={(e) => updateSolscan({ page_size: e.target.value })}
                className='border-input bg-background flex h-7 w-full rounded-md border px-2 text-xs'
              >
                <option value='10'>10</option>
                <option value='20'>20</option>
                <option value='40'>40</option>
                <option value='100'>100</option>
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-xs'>Min Value ($)</Label>
              <Input
                type='number'
                value={solscanSettings.value}
                onChange={(e) => updateSolscan({ value: e.target.value })}
                className='h-7 text-xs'
              />
            </div>
            <div className='flex items-center gap-4'>
              <div className='flex items-center gap-2'>
                <Switch
                  checked={solscanSettings.exclude_amount_zero === 'true'}
                  onCheckedChange={(v) =>
                    updateSolscan({ exclude_amount_zero: v ? 'true' : 'false' })
                  }
                />
                <Label className='text-xs'>Exclude Zero</Label>
              </div>
              <div className='flex items-center gap-2'>
                <Switch
                  checked={solscanSettings.remove_spam === 'true'}
                  onCheckedChange={(v) =>
                    updateSolscan({ remove_spam: v ? 'true' : 'false' })
                  }
                />
                <Label className='text-xs'>Remove Spam</Label>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ============================================================================
// Ingestion Tab (TIP Settings)
// ============================================================================
function IngestionTab({ bypassLimits = false }: { bypassLimits?: boolean }) {
  const [settings, setSettings] = useState<IngestSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `${API_BASE_URL}/api/ingest/settings`,
        { cache: 'no-store' },
        SETTINGS_FETCH_TIMEOUT
      );
      if (!res.ok) throw new Error('Failed to fetch');
      const data = await res.json();
      setSettings(data);
    } catch (err) {
      const message =
        err instanceof Error && err.message.includes('timeout')
          ? 'Backend busy (ingestion running). Try again shortly.'
          : 'Failed to load settings';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const updateSetting = async (updates: Partial<IngestSettings>) => {
    if (!settings) return;
    const newSettings = { ...settings, ...updates };
    setSettings(newSettings);
    try {
      await updateIngestSettings(updates);
      toast.success('Setting saved');
    } catch {
      toast.error('Failed to save setting');
    }
  };

  if (loading) {
    return (
      <div className='flex items-center justify-center py-8'>
        <Loader2 className='h-5 w-5 animate-spin' />
      </div>
    );
  }

  if (error || !settings) {
    return (
      <div className='flex flex-col items-center justify-center gap-3 py-8'>
        <AlertTriangle className='h-8 w-8 text-yellow-500' />
        <p className='text-muted-foreground text-sm'>
          {error || 'Failed to load ingest settings'}
        </p>
        <Button variant='outline' size='sm' onClick={loadSettings}>
          <RefreshCw className='mr-2 h-3 w-3' />
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className='space-y-6'>
      {/* Thresholds */}
      <div>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Tier-0 Thresholds
          <InfoTooltip>
            Minimum values for tokens to pass DexScreener ingestion
          </InfoTooltip>
        </h4>
        <div className='grid grid-cols-2 gap-4'>
          <NumericStepper
            label='Min Market Cap ($)'
            value={settings.mc_min}
            onChange={(v) => updateSetting({ mc_min: v })}
            min={0}
            step={5000}
            tooltip='Minimum market cap to pass Tier-0'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Min Volume ($)'
            value={settings.volume_min}
            onChange={(v) => updateSetting({ volume_min: v })}
            min={0}
            step={1000}
            tooltip='Minimum 24h volume'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Min Liquidity ($)'
            value={settings.liquidity_min}
            onChange={(v) => updateSetting({ liquidity_min: v })}
            min={0}
            step={1000}
            tooltip='Minimum liquidity'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Max Age (hours)'
            value={settings.age_max_hours}
            onChange={(v) => updateSetting({ age_max_hours: v })}
            min={1}
            step={6}
            tooltip='Maximum token age for ingestion'
            bypassLimits={bypassLimits}
          />
        </div>
      </div>

      {/* Batch/Budget Settings */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Batch & Budget Settings
          <InfoTooltip>Control batch sizes and credit limits</InfoTooltip>
        </h4>
        <div className='grid grid-cols-2 gap-4'>
          <NumericStepper
            label='Tier-0 Max Tokens'
            value={settings.tier0_max_tokens_per_run}
            onChange={(v) => updateSetting({ tier0_max_tokens_per_run: v })}
            min={1}
            step={10}
            tooltip='Max tokens per Tier-0 run'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Tier-1 Batch Size'
            value={settings.tier1_batch_size}
            onChange={(v) => updateSetting({ tier1_batch_size: v })}
            min={1}
            step={5}
            tooltip='Tokens to enrich per Tier-1 run'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Tier-1 Credit Budget'
            value={settings.tier1_credit_budget_per_run}
            onChange={(v) => updateSetting({ tier1_credit_budget_per_run: v })}
            min={10}
            step={50}
            tooltip='Max credits per Tier-1 run'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Auto-Promote Max'
            value={settings.auto_promote_max_per_run}
            onChange={(v) => updateSetting({ auto_promote_max_per_run: v })}
            min={1}
            step={1}
            tooltip='Max tokens to auto-promote per run'
            bypassLimits={bypassLimits}
          />
        </div>
      </div>

      {/* Hot Refresh Settings */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Hot Refresh
          <InfoTooltip>
            Periodically refresh MC/volume for recent tokens
          </InfoTooltip>
        </h4>
        <div className='mb-4 flex items-center justify-between rounded-lg border p-3'>
          <div>
            <Label className='text-sm'>Enable Hot Refresh</Label>
            <p className='text-muted-foreground text-xs'>
              Refresh MC/volume for recent ingested tokens
            </p>
          </div>
          <Switch
            checked={settings.hot_refresh_enabled}
            onCheckedChange={(v) => updateSetting({ hot_refresh_enabled: v })}
          />
        </div>
        <div className='grid grid-cols-2 gap-4'>
          <NumericStepper
            label='Hot Refresh Age (hours)'
            value={settings.hot_refresh_age_hours}
            onChange={(v) => updateSetting({ hot_refresh_age_hours: v })}
            min={1}
            step={6}
            tooltip='Max age for hot tokens'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Hot Refresh Max Tokens'
            value={settings.hot_refresh_max_tokens}
            onChange={(v) => updateSetting({ hot_refresh_max_tokens: v })}
            min={10}
            step={50}
            tooltip='Max tokens per hot refresh run'
            bypassLimits={bypassLimits}
          />
        </div>
      </div>

      {/* Performance Scoring Settings */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Performance Scoring
          <InfoTooltip>
            Score tokens during hot refresh and categorize into buckets
          </InfoTooltip>
        </h4>
        <div className='mb-4 flex items-center justify-between rounded-lg border p-3'>
          <div>
            <Label className='text-sm'>Enable Scoring</Label>
            <p className='text-muted-foreground text-xs'>
              Score tokens during hot refresh (Prime/Monitor/Cull)
            </p>
          </div>
          <Switch
            checked={settings.score_enabled ?? false}
            onCheckedChange={(v) => updateSetting({ score_enabled: v })}
          />
        </div>
        <div className='grid grid-cols-2 gap-4'>
          <NumericStepper
            label='Prime Threshold'
            value={settings.performance_prime_threshold ?? 65}
            onChange={(v) => updateSetting({ performance_prime_threshold: v })}
            min={50}
            max={100}
            step={5}
            tooltip='Score ≥ this = Prime bucket'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Monitor Threshold'
            value={settings.performance_monitor_threshold ?? 40}
            onChange={(v) =>
              updateSetting({ performance_monitor_threshold: v })
            }
            min={20}
            max={(settings.performance_prime_threshold ?? 65) - 5}
            step={5}
            tooltip='Score ≥ this (but < Prime) = Monitor'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Control Cohort Quota'
            value={settings.control_cohort_daily_quota ?? 5}
            onChange={(v) => updateSetting({ control_cohort_daily_quota: v })}
            min={0}
            max={20}
            step={1}
            tooltip='Low-score tokens tracked daily for validation'
            bypassLimits={bypassLimits}
          />
        </div>
        {settings.last_score_run_at && (
          <p className='text-muted-foreground mt-2 text-xs'>
            Last scored: {new Date(settings.last_score_run_at).toLocaleString()}
          </p>
        )}
      </div>

      {/* Scheduler Status */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>
          Scheduler Status
        </h4>
        <div className='bg-muted/30 space-y-2 rounded-lg border p-4 text-xs'>
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Last Tier-0:</span>
            <span>{formatTimestamp(settings.last_tier0_run_at)}</span>
          </div>
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Last Tier-1:</span>
            <span>{formatTimestamp(settings.last_tier1_run_at)}</span>
          </div>
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Last Tier-1 Credits:</span>
            <span>{settings.last_tier1_credits_used}</span>
          </div>
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Last Hot Refresh:</span>
            <span>{formatTimestamp(settings.last_hot_refresh_at)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// SWAB Tab (Settings, Status, Actions, Reconciliation)
// ============================================================================
function SwabTab({ bypassLimits = false }: { bypassLimits?: boolean }) {
  const [settings, setSettings] = useState<SwabSettings | null>(null);
  const [stats, setStats] = useState<SwabStats | null>(null);
  const [schedulerStatus, setSchedulerStatus] = useState<{
    last_check_at: string | null;
    next_check_at: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningCheck, setRunningCheck] = useState(false);
  const [runningPnl, setRunningPnl] = useState(false);
  const [runningReconcile, setRunningReconcile] = useState(false);
  const [reconcileMaxSigs, setReconcileMaxSigs] = useState(50);
  const [reconcileMaxPos, setReconcileMaxPos] = useState(50);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch with timeouts to prevent hanging during ingestion
      const [settingsRes, statsRes, schedulerRes] = await Promise.all([
        fetchWithTimeout(
          `${API_BASE_URL}/api/swab/settings`,
          { cache: 'no-store' },
          SETTINGS_FETCH_TIMEOUT
        ),
        fetchWithTimeout(
          `${API_BASE_URL}/api/swab/stats`,
          { cache: 'no-store' },
          SETTINGS_FETCH_TIMEOUT
        ),
        fetchWithTimeout(
          `${API_BASE_URL}/api/swab/scheduler/status`,
          { cache: 'no-store' },
          SETTINGS_FETCH_TIMEOUT
        )
      ]);

      if (!settingsRes.ok || !statsRes.ok || !schedulerRes.ok) {
        throw new Error('Failed to fetch');
      }

      const [s, st, sc] = await Promise.all([
        settingsRes.json(),
        statsRes.json(),
        schedulerRes.json()
      ]);
      setSettings(s);
      setStats(st);
      setSchedulerStatus(sc);
    } catch (err) {
      const message =
        err instanceof Error && err.message.includes('timeout')
          ? 'Backend busy (ingestion running). Try again shortly.'
          : 'Failed to load SWAB data';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const updateSetting = async (updates: {
    auto_check_enabled?: boolean;
    check_interval_minutes?: number;
    daily_credit_budget?: number;
    stale_threshold_minutes?: number;
    min_token_count?: number;
  }) => {
    if (!settings) return;
    const newSettings = { ...settings, ...updates } as SwabSettings;
    setSettings(newSettings);
    try {
      await updateSwabSettings(updates);
      toast.success('SWAB setting saved');
    } catch (err) {
      console.error('SWAB settings update error:', err);
      toast.error('Failed to save');
    }
  };

  const runCheck = async () => {
    setRunningCheck(true);
    try {
      const result = await triggerSwabCheck();
      toast.success(
        `Checked ${result.positions_checked} positions, ${result.sold} sells detected`
      );
      loadData();
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
      loadData();
    } catch {
      toast.error('Reconciliation failed');
    } finally {
      setRunningReconcile(false);
    }
  };

  if (loading) {
    return (
      <div className='flex items-center justify-center py-8'>
        <Loader2 className='h-5 w-5 animate-spin' />
      </div>
    );
  }

  if (error) {
    return (
      <div className='flex flex-col items-center justify-center gap-3 py-8'>
        <AlertTriangle className='h-8 w-8 text-yellow-500' />
        <p className='text-muted-foreground text-sm'>{error}</p>
        <Button variant='outline' size='sm' onClick={loadData}>
          <RefreshCw className='mr-2 h-3 w-3' />
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className='space-y-6'>
      {/* SWAB Settings */}
      <div>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          SWAB Settings
          <InfoTooltip>
            Smart Wallet Archive Builder: tracks MTEW positions, detects
            buys/sells, computes PnL.
          </InfoTooltip>
        </h4>
        {settings && (
          <div className='space-y-4'>
            <div className='flex items-center justify-between rounded-lg border p-3'>
              <div>
                <Label className='text-sm'>Auto-Check Enabled</Label>
                <p className='text-muted-foreground text-xs'>
                  Automatically check positions for sells
                </p>
              </div>
              <Switch
                checked={settings.auto_check_enabled}
                onCheckedChange={(v) =>
                  updateSetting({ auto_check_enabled: v })
                }
              />
            </div>
            <div className='grid grid-cols-2 gap-4'>
              <NumericStepper
                label='Check Interval (min)'
                value={settings.check_interval_minutes}
                onChange={(v) => updateSetting({ check_interval_minutes: v })}
                min={5}
                max={1440}
                step={5}
                tooltip='How often to check for position changes (5-1440 min)'
                bypassLimits={bypassLimits}
              />
              <NumericStepper
                label='Daily Credit Budget'
                value={settings.daily_credit_budget}
                onChange={(v) => updateSetting({ daily_credit_budget: v })}
                min={0}
                max={100000}
                step={500}
                tooltip='Max credits for auto-checks per day (0-100k)'
                bypassLimits={bypassLimits}
              />
              <NumericStepper
                label='Stale Threshold (min)'
                value={settings.stale_threshold_minutes}
                onChange={(v) => updateSetting({ stale_threshold_minutes: v })}
                min={5}
                max={1440}
                step={30}
                tooltip='Consider position stale after this time (5-1440 min)'
                bypassLimits={bypassLimits}
              />
              <NumericStepper
                label='Min Token Count'
                value={settings.min_token_count}
                onChange={(v) => updateSetting({ min_token_count: v })}
                min={1}
                max={50}
                step={1}
                tooltip='Only track wallets appearing in N+ tokens (1-50)'
                bypassLimits={bypassLimits}
              />
            </div>
          </div>
        )}
      </div>

      {/* SWAB Status */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>
          SWAB Status
        </h4>
        {stats && (
          <div className='bg-muted/30 grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border p-4 text-xs'>
            <div className='flex justify-between'>
              <span className='text-muted-foreground'>Total Positions:</span>
              <span>{stats.total_positions}</span>
            </div>
            <div className='flex justify-between'>
              <span className='text-muted-foreground'>Still Holding:</span>
              <span>{stats.holding}</span>
            </div>
            <div className='flex justify-between'>
              <span className='text-muted-foreground'>Sold:</span>
              <span>{stats.sold}</span>
            </div>
            <div className='flex justify-between'>
              <span className='text-muted-foreground'>Credits Today:</span>
              <span>{stats.credits_used_today}</span>
            </div>
            <div className='flex justify-between'>
              <span className='text-muted-foreground'>Last Check:</span>
              <span>
                {formatTimestamp(schedulerStatus?.last_check_at ?? null)}
              </span>
            </div>
            <div className='flex justify-between'>
              <span className='text-muted-foreground'>Next Check:</span>
              <span>
                {formatTimestamp(schedulerStatus?.next_check_at ?? null)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* SWAB Actions */}
      <div className='border-t pt-4'>
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

      {/* SWAB Reconciliation */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Reconciliation
          <InfoTooltip>
            Fix positions where sells were missed. Scans recent transactions to
            find actual exit prices.
          </InfoTooltip>
        </h4>
        <div className='mb-4 flex items-start gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3'>
          <AlertTriangle className='mt-0.5 h-4 w-4 text-yellow-500' />
          <p className='text-xs text-yellow-200'>
            Reconciliation uses Helius credits. Each position checked costs ~1
            credit.
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
  );
}

// ============================================================================
// Webhooks Tab
// ============================================================================
function WebhooksTab() {
  const [webhooks, setWebhooks] = useState<WebhookInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchWebhooks = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `${API_BASE_URL}/webhooks/list`,
        { cache: 'no-store' },
        SETTINGS_FETCH_TIMEOUT
      );
      if (res.ok) {
        const data = await res.json();
        setWebhooks(data.webhooks || []);
      } else {
        throw new Error('Failed to fetch');
      }
    } catch (err) {
      const message =
        err instanceof Error && err.message.includes('timeout')
          ? 'Backend busy (ingestion running). Try again shortly.'
          : 'Failed to load webhooks';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWebhooks();
  }, []);

  const createSwabWebhook = async () => {
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE_URL}/webhooks/create-swab`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (res.ok) {
        toast.success('SWAB webhook creation queued');
        setTimeout(fetchWebhooks, 2000);
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Failed to create webhook');
      }
    } catch {
      toast.error('Failed to create webhook');
    } finally {
      setCreating(false);
    }
  };

  const deleteWebhook = async (webhookId: string) => {
    setDeletingId(webhookId);
    try {
      const res = await fetch(`${API_BASE_URL}/webhooks/${webhookId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        toast.success('Webhook deletion queued');
        setWebhooks((prev) => prev.filter((w) => w.webhookID !== webhookId));
      } else {
        toast.error('Failed to delete webhook');
      }
    } catch {
      toast.error('Failed to delete webhook');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className='space-y-4'>
      <div className='flex items-center justify-between'>
        <h4 className='text-muted-foreground flex items-center text-xs font-semibold uppercase'>
          Helius Webhooks
          <InfoTooltip>
            Webhooks for real-time SWAB tracking. Captures accurate exit prices
            when MTEW wallets sell.
          </InfoTooltip>
        </h4>
        <div className='flex gap-2'>
          <Button
            variant='outline'
            size='sm'
            onClick={fetchWebhooks}
            disabled={loading}
          >
            <RefreshCw
              className={`mr-1 h-3 w-3 ${loading ? 'animate-spin' : ''}`}
            />
            Refresh
          </Button>
          <Button
            variant='default'
            size='sm'
            onClick={createSwabWebhook}
            disabled={creating}
          >
            {creating ? (
              <Loader2 className='mr-1 h-3 w-3 animate-spin' />
            ) : (
              <Plus className='mr-1 h-3 w-3' />
            )}
            Create SWAB Webhook
          </Button>
        </div>
      </div>

      {loading ? (
        <div className='flex items-center justify-center py-8'>
          <Loader2 className='h-5 w-5 animate-spin' />
        </div>
      ) : error ? (
        <div className='flex flex-col items-center justify-center gap-3 py-8'>
          <AlertTriangle className='h-8 w-8 text-yellow-500' />
          <p className='text-muted-foreground text-sm'>{error}</p>
          <Button variant='outline' size='sm' onClick={fetchWebhooks}>
            <RefreshCw className='mr-2 h-3 w-3' />
            Retry
          </Button>
        </div>
      ) : webhooks.length === 0 ? (
        <div className='bg-muted/50 rounded-lg border border-dashed p-6 text-center'>
          <Webhook className='text-muted-foreground mx-auto mb-2 h-8 w-8' />
          <p className='text-muted-foreground text-sm'>
            No webhooks configured
          </p>
          <p className='text-muted-foreground mt-1 text-xs'>
            Create a SWAB webhook to track MTEW wallet sells in real-time
          </p>
        </div>
      ) : (
        <div className='space-y-2'>
          {webhooks.map((webhook) => (
            <div
              key={webhook.webhookID}
              className='bg-muted/30 flex items-center justify-between rounded-lg border p-3'
            >
              <div className='min-w-0 flex-1'>
                <div className='flex items-center gap-2'>
                  <Badge variant='secondary' className='text-xs'>
                    {webhook.webhookType || 'enhanced'}
                  </Badge>
                  <code className='text-muted-foreground truncate text-xs'>
                    {webhook.webhookID}
                  </code>
                </div>
                <p className='text-muted-foreground mt-1 truncate text-xs'>
                  {webhook.webhookURL}
                </p>
                {webhook.accountAddresses && (
                  <p className='text-muted-foreground text-xs'>
                    Monitoring {webhook.accountAddresses.length} wallets
                  </p>
                )}
              </div>
              <Button
                variant='ghost'
                size='icon'
                className='text-destructive hover:text-destructive h-8 w-8'
                onClick={() => deleteWebhook(webhook.webhookID)}
                disabled={deletingId === webhook.webhookID}
              >
                {deletingId === webhook.webhookID ? (
                  <Loader2 className='h-4 w-4 animate-spin' />
                ) : (
                  <Trash2 className='h-4 w-4' />
                )}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// System Tab (Feature Flags, Alerts/UI)
// ============================================================================
function SystemTab() {
  const [ingestSettings, setIngestSettings] = useState<IngestSettings | null>(
    null
  );
  const [swabSettings, setSwabSettings] = useState<SwabSettings | null>(null);
  const [bannerPrefs, setBannerPrefs] =
    useState<BannerPrefs>(defaultBannerPrefs);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    setBannerPrefs(loadBannerPrefs());
    try {
      const [ingestRes, swabRes] = await Promise.all([
        fetchWithTimeout(
          `${API_BASE_URL}/api/ingest/settings`,
          { cache: 'no-store' },
          SETTINGS_FETCH_TIMEOUT
        ),
        fetchWithTimeout(
          `${API_BASE_URL}/api/swab/settings`,
          { cache: 'no-store' },
          SETTINGS_FETCH_TIMEOUT
        )
      ]);

      if (!ingestRes.ok || !swabRes.ok) {
        throw new Error('Failed to fetch');
      }

      const [ingest, swab] = await Promise.all([
        ingestRes.json(),
        swabRes.json()
      ]);
      setIngestSettings(ingest);
      setSwabSettings(swab);
    } catch (err) {
      const message =
        err instanceof Error && err.message.includes('timeout')
          ? 'Backend busy (ingestion running). Try again shortly.'
          : 'Failed to load settings';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const toggleIngestFlag = async (
    flag: keyof IngestSettings,
    value: boolean
  ) => {
    if (!ingestSettings) return;
    const updates = { [flag]: value };
    setIngestSettings({ ...ingestSettings, ...updates });
    try {
      await updateIngestSettings(updates);
      toast.success(`${String(flag)} ${value ? 'enabled' : 'disabled'}`);
    } catch {
      toast.error('Failed to update');
      setIngestSettings({ ...ingestSettings, [flag]: !value });
    }
  };

  const toggleSwabFlag = async (flag: keyof SwabSettings, value: boolean) => {
    if (!swabSettings) return;
    const updates = { [flag]: value } as Partial<SwabSettings>;
    setSwabSettings({ ...swabSettings, ...updates } as SwabSettings);
    try {
      await updateSwabSettings(updates);
      toast.success(`${String(flag)} ${value ? 'enabled' : 'disabled'}`);
    } catch {
      toast.error('Failed to update');
    }
  };

  const updateBannerPref = (key: keyof BannerPrefs, value: boolean) => {
    const newPrefs = { ...bannerPrefs, [key]: value };
    setBannerPrefs(newPrefs);
    saveBannerPrefs(newPrefs);
    toast.success('Preference saved');
  };

  if (loading) {
    return (
      <div className='flex items-center justify-center py-8'>
        <Loader2 className='h-5 w-5 animate-spin' />
      </div>
    );
  }

  if (error) {
    return (
      <div className='flex flex-col items-center justify-center gap-3 py-8'>
        <AlertTriangle className='h-8 w-8 text-yellow-500' />
        <p className='text-muted-foreground text-sm'>{error}</p>
        <Button variant='outline' size='sm' onClick={loadData}>
          <RefreshCw className='mr-2 h-3 w-3' />
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className='space-y-6'>
      {/* Feature Flags */}
      <div>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Feature Flags
          <InfoTooltip>
            Enable/disable scheduler jobs and automation
          </InfoTooltip>
        </h4>
        <div className='space-y-2'>
          {ingestSettings && (
            <>
              <div className='flex items-center justify-between rounded-lg border p-3'>
                <div>
                  <Label className='flex items-center text-sm'>
                    <Zap className='mr-2 h-4 w-4 text-yellow-500' />
                    Tier-0 Ingestion
                  </Label>
                  <p className='text-muted-foreground text-xs'>
                    Hourly DexScreener fetch (free)
                  </p>
                </div>
                <Switch
                  checked={ingestSettings.ingest_enabled}
                  onCheckedChange={(v) => toggleIngestFlag('ingest_enabled', v)}
                />
              </div>
              <div className='flex items-center justify-between rounded-lg border p-3'>
                <div>
                  <Label className='flex items-center text-sm'>
                    <Zap className='mr-2 h-4 w-4 text-blue-500' />
                    Tier-1 Enrichment
                  </Label>
                  <p className='text-muted-foreground text-xs'>
                    Helius enrichment (budgeted)
                  </p>
                </div>
                <Switch
                  checked={ingestSettings.enrich_enabled}
                  onCheckedChange={(v) => toggleIngestFlag('enrich_enabled', v)}
                />
              </div>
              <div className='flex items-center justify-between rounded-lg border p-3'>
                <div>
                  <Label className='flex items-center text-sm'>
                    <Zap className='mr-2 h-4 w-4 text-green-500' />
                    Auto-Promotion
                  </Label>
                  <p className='text-muted-foreground text-xs'>
                    Promote enriched tokens to analysis
                  </p>
                </div>
                <Switch
                  checked={ingestSettings.auto_promote_enabled}
                  onCheckedChange={(v) =>
                    toggleIngestFlag('auto_promote_enabled', v)
                  }
                />
              </div>
              <div className='flex items-center justify-between rounded-lg border p-3'>
                <div>
                  <Label className='flex items-center text-sm'>
                    <Zap className='mr-2 h-4 w-4 text-orange-500' />
                    Hot Refresh
                  </Label>
                  <p className='text-muted-foreground text-xs'>
                    Refresh MC/volume for recent tokens
                  </p>
                </div>
                <Switch
                  checked={ingestSettings.hot_refresh_enabled}
                  onCheckedChange={(v) =>
                    toggleIngestFlag('hot_refresh_enabled', v)
                  }
                />
              </div>
            </>
          )}
          {swabSettings && (
            <div className='flex items-center justify-between rounded-lg border p-3'>
              <div>
                <Label className='flex items-center text-sm'>
                  <Zap className='mr-2 h-4 w-4 text-purple-500' />
                  SWAB Auto-Check
                </Label>
                <p className='text-muted-foreground text-xs'>
                  Periodically check positions for sells
                </p>
              </div>
              <Switch
                checked={swabSettings.auto_check_enabled}
                onCheckedChange={(v) => toggleSwabFlag('auto_check_enabled', v)}
              />
            </div>
          )}
        </div>
      </div>

      {/* Alerts & UI */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          UI Preferences
          <InfoTooltip>Control banners and notifications</InfoTooltip>
        </h4>
        <div className='flex items-center justify-between rounded-lg border p-3'>
          <div>
            <Label className='flex items-center text-sm'>
              <Bell className='mr-2 h-4 w-4' />
              Ingest Banner
            </Label>
            <p className='text-muted-foreground text-xs'>
              Show banner when pre-analyzed tokens await promotion
            </p>
          </div>
          <Switch
            checked={bannerPrefs.showIngestBanner}
            onCheckedChange={(v) => updateBannerPref('showIngestBanner', v)}
          />
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Settings Modal
// ============================================================================
export function MasterControlModal({
  open,
  onOpenChange,
  apiSettings,
  setApiSettings,
  defaultApiSettings,
  children
}: MasterControlModalProps) {
  return (
    <TooltipProvider>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogTrigger asChild>{children}</DialogTrigger>
        <DialogContent className='max-h-[85vh] w-full max-w-2xl overflow-hidden'>
          <DialogHeader>
            <DialogTitle className='flex items-center gap-2'>
              <Settings2 className='h-5 w-5' />
              Settings
            </DialogTitle>
            <DialogDescription>
              Controls for scanning, ingestion, and tracking
            </DialogDescription>
          </DialogHeader>

          <Tabs defaultValue='scanning' className='flex-1'>
            <TabsList className='grid w-full grid-cols-5'>
              <TabsTrigger value='scanning' className='text-xs'>
                Scanning
              </TabsTrigger>
              <TabsTrigger value='ingestion' className='text-xs'>
                Ingestion
              </TabsTrigger>
              <TabsTrigger value='swab' className='text-xs'>
                SWAB
              </TabsTrigger>
              <TabsTrigger value='webhooks' className='text-xs'>
                Webhooks
              </TabsTrigger>
              <TabsTrigger value='system' className='text-xs'>
                System
              </TabsTrigger>
            </TabsList>

            <div className='mt-4 h-[55vh] overflow-y-auto pr-2'>
              <TabsContent value='scanning'>
                <ScanningTab
                  apiSettings={apiSettings}
                  setApiSettings={setApiSettings}
                  defaultApiSettings={defaultApiSettings}
                />
              </TabsContent>

              <TabsContent value='ingestion'>
                <IngestionTab
                  bypassLimits={apiSettings.bypassLimits ?? false}
                />
              </TabsContent>

              <TabsContent value='swab'>
                <SwabTab bypassLimits={apiSettings.bypassLimits ?? false} />
              </TabsContent>

              <TabsContent value='webhooks'>
                <WebhooksTab />
              </TabsContent>

              <TabsContent value='system'>
                <SystemTab />
              </TabsContent>
            </div>
          </Tabs>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  );
}
