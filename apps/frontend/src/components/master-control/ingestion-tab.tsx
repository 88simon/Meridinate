'use client';

import { useEffect, useState } from 'react';
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
import { Loader2, RefreshCw, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { updateIngestSettings, IngestSettings, API_BASE_URL } from '@/lib/api';
import { NumericStepper } from './NumericStepper';
import { InfoTooltip } from './InfoTooltip';
import { fetchWithRetry, formatTimestamp } from './utils';

interface IngestionTabProps {
  bypassLimits?: boolean;
}

export function IngestionTab({ bypassLimits = false }: IngestionTabProps) {
  const [settings, setSettings] = useState<IngestSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/ingest/settings`, {
        cache: 'no-store'
      });
      const data = await res.json();
      setSettings(data);
    } catch (err) {
      const message =
        err instanceof Error && err.message.includes('timeout')
          ? 'Backend busy. Retried but still unavailable.'
          : 'Failed to load settings after retries';
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
      {/* Discovery Thresholds */}
      <div>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Discovery Thresholds
          <InfoTooltip>
            Minimum values for tokens to pass DexScreener discovery
          </InfoTooltip>
        </h4>
        <div className='grid grid-cols-2 gap-4'>
          <NumericStepper
            label='Min Market Cap ($)'
            value={settings.mc_min}
            onChange={(v) => updateSetting({ mc_min: v })}
            min={0}
            step={5000}
            tooltip='Minimum market cap to pass discovery'
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
            tooltip='Maximum token age for discovery'
            bypassLimits={bypassLimits}
          />
        </div>
      </div>

      {/* Discovery Scheduler */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Discovery Scheduler
          <InfoTooltip>Control how often discovery runs</InfoTooltip>
        </h4>
        <div className='grid grid-cols-2 gap-4'>
          <div className='space-y-2'>
            <Label className='text-xs'>Discovery Interval</Label>
            <Select
              value={String(
                settings.discovery_interval_minutes ??
                  settings.tier0_interval_minutes ??
                  60
              )}
              onValueChange={(v) =>
                updateSetting({ discovery_interval_minutes: parseInt(v, 10) })
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
        </div>
      </div>

      {/* Discovery Settings */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Discovery Settings
          <InfoTooltip>Control batch sizes for discovery</InfoTooltip>
        </h4>
        <div className='grid grid-cols-2 gap-4'>
          <NumericStepper
            label='Max Tokens per Run'
            value={
              (settings.discovery_max_per_run ??
                settings.tier0_max_tokens_per_run ??
                50) as number
            }
            onChange={(v) => updateSetting({ discovery_max_per_run: v })}
            min={1}
            step={10}
            tooltip='Max tokens per discovery run'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Auto-Promote Max'
            value={(settings.auto_promote_max_per_run ?? 5) as number}
            onChange={(v) => updateSetting({ auto_promote_max_per_run: v })}
            min={1}
            step={1}
            tooltip='Max tokens to auto-promote per run'
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
            value={(settings.performance_prime_threshold ?? 65) as number}
            onChange={(v) => updateSetting({ performance_prime_threshold: v })}
            min={50}
            max={100}
            step={5}
            tooltip='Score >= this = Prime bucket'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Monitor Threshold'
            value={(settings.performance_monitor_threshold ?? 40) as number}
            onChange={(v) =>
              updateSetting({ performance_monitor_threshold: v })
            }
            min={20}
            max={((settings.performance_prime_threshold ?? 65) as number) - 5}
            step={5}
            tooltip='Score >= this (but < Prime) = Monitor'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Control Cohort Quota'
            value={(settings.control_cohort_daily_quota ?? 5) as number}
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
            <span className='text-muted-foreground'>Last Discovery:</span>
            <span>
              {formatTimestamp(
                (settings.last_discovery_run_at ??
                  settings.last_tier0_run_at ??
                  null) as string | null
              )}
            </span>
          </div>
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Last Score Run:</span>
            <span>{formatTimestamp(settings.last_score_run_at ?? null)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
