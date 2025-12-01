'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Loader2,
  RefreshCw,
  AlertTriangle,
  Activity,
  Play
} from 'lucide-react';
import { toast } from 'sonner';
import {
  updateSwabSettings,
  triggerSwabCheck,
  triggerSwabPnlUpdate,
  reconcileAllPositions,
  SwabSettings,
  SwabStats,
  API_BASE_URL
} from '@/lib/api';
import { NumericStepper } from './NumericStepper';
import { InfoTooltip } from './InfoTooltip';
import { fetchWithRetry, formatTimestamp } from './utils';

interface SwabTabProps {
  bypassLimits?: boolean;
}

export function SwabTab({ bypassLimits = false }: SwabTabProps) {
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
      const [settingsRes, statsRes, schedulerRes] = await Promise.all([
        fetchWithRetry(`${API_BASE_URL}/api/swab/settings`, {
          cache: 'no-store'
        }),
        fetchWithRetry(`${API_BASE_URL}/api/swab/stats`, { cache: 'no-store' }),
        fetchWithRetry(`${API_BASE_URL}/api/swab/scheduler/status`, {
          cache: 'no-store'
        })
      ]);

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
          ? 'Backend busy. Retried but still unavailable.'
          : 'Failed to load SWAB data after retries';
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
