'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Loader2,
  RefreshCw,
  AlertTriangle,
  Zap,
  Bell
} from 'lucide-react';
import { toast } from 'sonner';
import {
  updateIngestSettings,
  updateSwabSettings,
  IngestSettings,
  SwabSettings,
  API_BASE_URL,
  fetchWithTimeout
} from '@/lib/api';
import { InfoTooltip } from './InfoTooltip';
import {
  SETTINGS_FETCH_TIMEOUT,
  BannerPrefs,
  defaultBannerPrefs,
  loadBannerPrefs,
  saveBannerPrefs
} from './utils';

export function SystemTab() {
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
